#!/usr/bin/env python3
"""Grounding — local-first digital-detox agent. Core: storage, fatigue signal, Ollama, lamp.

  uv run grounding.py watch            nudge you with a mission when you've been on screen too long
  uv run grounding.py mission          generate an offline mission now
  uv run grounding.py reflect PHOTO    turn a photo from outside into a journal entry
  uv run grounding.py status           screen time + current mission as JSON
  uv run grounding.py report [DAYS]    weekly PDF of offline achievements
  uv run grounding.py bench PHOTO      local vs cloud vision latency
  uv run grounding.py phone [PORT]     phone app server (open the QR from the dashboard)
  uv run streamlit run app.py          desktop dashboard
"""
import ctypes, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

HOME = Path(os.environ.get("GROUNDING_HOME", Path.home() / ".grounding"))
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
TEXT_MODEL = os.environ.get("GROUNDING_TEXT_MODEL", "llama3.2:3b")
VISION_MODEL = os.environ.get("GROUNDING_VISION_MODEL", "moondream")
FATIGUE_MIN = int(os.environ.get("GROUNDING_FATIGUE_MIN", "90"))  # continuous screen time before a nudge
BREAK_IDLE_SEC = 5 * 60  # this much keyboard/mouse idle counts as a real break

HOME.mkdir(parents=True, exist_ok=True)
(HOME / "photos").mkdir(exist_ok=True)


def db():
    con = sqlite3.connect(HOME / "grounding.db", timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript("""
      CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
      CREATE TABLE IF NOT EXISTS missions(id INTEGER PRIMARY KEY, at TEXT, text TEXT, done INTEGER DEFAULT 0);
      CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY, at TEXT, mission TEXT, photo TEXT, entry TEXT);
      CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, start REAL, end REAL);
    """)
    return con


def kv(con, k, default=None):
    r = con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def set_kv(con, k, v):
    con.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, json.dumps(v)))
    con.commit()


# ---------- fatigue signal ----------

def idle_seconds():
    """Seconds since last keyboard/mouse input on macOS, Windows, Linux (X11 or GNOME).
    Falls back to the age of your shell history when the desktop gives no idle time."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=5).stdout
            return next(int(l.split()[-1]) // 1_000_000_000 for l in out.splitlines() if "HIDIdleTime" in l)
        if sys.platform == "win32":
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO))
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
            return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) // 1000
        if shutil.which("xprintidle"):
            return int(subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=5).stdout) // 1000
        if shutil.which("gdbus"):
            out = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
                                  "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                                  "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
                                 capture_output=True, text=True, timeout=5).stdout  # "(uint64 12345,)"
            if "uint64" in out:
                return int(out.split()[1].rstrip(",)")) // 1000
    except (OSError, ValueError, StopIteration, AttributeError, subprocess.SubprocessError):
        pass
    hist = [p for p in (Path.home() / ".zsh_history", Path.home() / ".bash_history") if p.exists()]
    return int(time.time() - max(p.stat().st_mtime for p in hist)) if hist else 0


def update_session(con, idle, now=None):
    """Track continuous screen time. Returns minutes on screen since the last real break."""
    now = now or time.time()
    start = kv(con, "active_since")
    if start is None or idle >= BREAK_IDLE_SEC:
        if start is not None and now - idle - start >= 60:
            con.execute("INSERT INTO sessions(start,end) VALUES(?,?)", (start, now - idle))
        start = now
        set_kv(con, "active_since", start)
    return int((now - start) // 60)


def take_break(con):
    """Mark a break now (a mission was completed)."""
    now = time.time()
    start = kv(con, "active_since")
    if start is not None and now - start >= 60:
        con.execute("INSERT INTO sessions(start,end) VALUES(?,?)", (start, now))
    set_kv(con, "active_since", now)


def status():
    con = db()
    mins = update_session(con, idle_seconds())
    m = con.execute("SELECT * FROM missions ORDER BY id DESC LIMIT 1").fetchone()
    return {"screen_minutes": mins, "fatigued": mins >= FATIGUE_MIN, "threshold": FATIGUE_MIN,
            "mission": dict(m) if m else None,
            "journal_count": con.execute("SELECT COUNT(*) FROM journal").fetchone()[0]}


# ---------- local models ----------

def ollama(model, prompt, images=None, timeout=180):
    body = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.8}}
    if images:
        body["images"] = images
    req = urllib.request.Request(f"{OLLAMA}/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["response"].strip()
    except OSError as e:
        raise RuntimeError(f"Ollama not reachable at {OLLAMA} ({e}). Run `ollama serve` and "
                           f"`ollama pull {model}`.") from e


def interests():
    f = HOME / "interests.json"
    if not f.exists():
        f.write_text(json.dumps(["walking", "photography", "coffee", "trees", "birds"], indent=2))
    return json.loads(f.read_text())


def save_photo(data, name):
    ext = Path(name).suffix.lower()
    dest = HOME / "photos" / f"{datetime.now():%Y%m%d-%H%M%S}{ext if ext in ('.jpg', '.jpeg', '.png', '.webp') else '.jpg'}"
    dest.write_bytes(data)
    return dest


# ---------- smart lamp ----------
# GROUNDING_LAMP = homeassistant | wled | webhook   (unset = no lamp)
COLORS = {"break": [40, 200, 80], "focus": [255, 180, 110]}  # green = step away, warm = back to work


def lamp(state):
    """Set the desk lamp: 'break' (green) or 'focus' (warm). Returns a message, never raises."""
    kind = os.environ.get("GROUNDING_LAMP", "")
    rgb = COLORS[state]
    try:
        if kind == "homeassistant":
            url = os.environ["HA_URL"].rstrip("/") + "/api/services/light/turn_on"
            body = {"entity_id": os.environ["HA_LIGHT"], "rgb_color": rgb}
            headers = {"Authorization": f"Bearer {os.environ['HA_TOKEN']}"}
        elif kind == "wled":
            url = os.environ["WLED_URL"].rstrip("/") + "/json/state"
            body, headers = {"on": True, "seg": [{"col": [rgb]}]}, {}
        elif kind == "webhook":
            url, body, headers = os.environ["GROUNDING_LAMP_WEBHOOK"], {"state": state, "rgb": rgb}, {}
        else:
            return "no lamp configured"
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
        urllib.request.urlopen(req, timeout=5).close()
        return f"lamp → {state}"
    except (OSError, KeyError) as e:
        return f"lamp failed: {e}"


def notify(text):
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f"display notification {json.dumps(text)} with title \"Time to touch grass 🌱\""])
    elif sys.platform.startswith("linux") and shutil.which("notify-send"):
        subprocess.run(["notify-send", "Time to touch grass 🌱", text])
    elif sys.platform == "win32":
        ps = ("[void][Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
              "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
              f"$n.Visible=$true;$n.ShowBalloonTip(10000,'Time to touch grass',{json.dumps(text)},'Info');sleep 11")
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
    print(text)


def watch(poll=60):
    import agents
    nudged = False
    while True:
        try:
            out = agents.run_mission(force=False, nudged=nudged)
            nudged = out["route"] in ("mission", "already_nudged")
        except RuntimeError as e:
            print(e, file=sys.stderr)
        time.sleep(poll)


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "watch":
        watch()
    elif cmd == "mission":
        import agents
        print(agents.run_mission(force=True)["mission"])
    elif cmd == "reflect" and args:
        import agents
        print(agents.run_reflect(Path(args[0]).read_bytes(), args[0])["entry"])
    elif cmd == "status":
        print(json.dumps(status(), indent=2))
    elif cmd == "report":
        import report
        print(report.build(int(args[0]) if args else 7))
    elif cmd == "bench" and args:
        import bench
        print(json.dumps(bench.run(Path(args[0])), indent=2))
    elif cmd == "phone":
        import mobile
        mobile.serve(int(args[0]) if args else 8766)
    else:
        print(__doc__)
