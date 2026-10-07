"""Desktop dashboard: uv run streamlit run app.py   (also starts the phone app server)"""
import base64, html, io, json, os, threading
from datetime import datetime
from pathlib import Path

import segno
import streamlit as st

import agents, mobile, report
import grounding as g

st.set_page_config(page_title="Grounding", page_icon="🌱", layout="centered")


@st.cache_resource
def phone_server():
    port = int(os.environ.get("GROUNDING_PHONE_PORT", mobile.PORT))
    try:
        srv = mobile.ThreadingHTTPServer(("0.0.0.0", port), mobile.Phone)
    except OSError:
        return port  # already running (e.g. `grounding.py phone`)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return port


st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..600;1,9..144,300..500&family=Instrument+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--moss:#3E6B48;--ink:#1F2A20;--mute:#7A7F6E;--paper:#F3EFE6;--card:#FBF8F1;--line:#1F2A2014;--clay:#B5643C}
html,body,[class*="st-"],p,li,label,button,input,textarea{font-family:"Instrument Sans",system-ui,sans-serif}
.stApp{background:radial-gradient(1200px 600px at 85% -10%,#DCE6D2 0%,transparent 60%),
  radial-gradient(900px 500px at -10% 110%,#EBDDC8 0%,transparent 55%),var(--paper)}
.block-container{padding-top:3.5rem;max-width:760px}
header[data-testid="stHeader"]{background:transparent}
h1,h2,h3,.serif{font-family:"Fraunces",Georgia,serif!important;font-weight:400!important;letter-spacing:-.02em;color:var(--ink)}
.eyebrow{font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--mute);font-weight:600}
.hero{font-family:"Fraunces",serif;font-size:clamp(2.6rem,7vw,4.2rem);line-height:1;margin:.35rem 0 .6rem;color:var(--ink);font-weight:300}
.hero em{color:var(--moss);font-style:italic}
.sub{color:var(--mute);font-size:.95rem;margin-bottom:1.6rem}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--moss);margin-right:8px;
  box-shadow:0 0 0 4px #3E6B4822;vertical-align:middle}
[role="tablist"]{gap:4px!important;background:#E9E3D599;padding:5px;border-radius:999px;border:1px solid var(--line);width:fit-content;flex-wrap:wrap;border-bottom:1px solid var(--line)!important}
[role="tablist"]>*:not([role="tab"]){display:none!important}
[data-testid="stTab"]{border-radius:999px!important;padding:7px 16px!important;font-size:.86rem;color:var(--mute);border:0!important;cursor:pointer}
[data-testid="stTab"][aria-selected="true"]{background:var(--card);color:var(--ink);box-shadow:0 1px 3px #0000001a}
[data-testid="stTab"]:after,[data-testid="stTab"]:before{display:none!important}
.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:26px 28px;margin:14px 0;
  box-shadow:0 1px 0 #fff inset,0 18px 40px -28px #1F2A2040}
.ringwrap{display:flex;align-items:center;gap:28px;flex-wrap:wrap}
.ringnum,.stMarkdown .ringnum{font-family:"Fraunces",serif;font-size:2.6rem;line-height:1;color:var(--ink)}
.ringnum small{font-size:1rem;color:var(--mute);margin-left:4px}
.state{font-family:"Fraunces",serif;font-style:italic;font-size:1.35rem;color:var(--ink);margin:.2rem 0}
.quote,.stMarkdown .quote{font-family:"Fraunces",serif!important;font-size:1.55rem!important;line-height:1.4;font-weight:300;color:var(--ink);margin:.6rem 0 0}
.quote:before{content:"“";display:block;font-size:4rem!important;line-height:.55!important;font-family:Fraunces,serif;color:var(--moss);margin:14px 0 6px}
.done{color:var(--moss);font-size:.8rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase}
.stButton button,.stDownloadButton button{border-radius:999px;padding:.55rem 1.4rem;font-weight:500;border:1px solid var(--line)}
.stButton button[kind="primary"]{background:var(--ink);border-color:var(--ink);color:var(--paper)}
.stButton button[kind="primary"]:hover{background:var(--moss);border-color:var(--moss)}
[data-testid="stFileUploaderDropzone"]{background:var(--card);border:1.5px dashed #3E6B4855;border-radius:18px}
[data-testid="stMetric"]{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 18px}
[data-testid="stMetricValue"]{font-family:"Fraunces",serif;font-weight:400}
.polaroid{background:#fff;padding:10px 10px 16px;border-radius:4px;box-shadow:0 14px 30px -18px #1F2A2066,0 1px 2px #0001;margin:10px 0 26px}
.polaroid img{width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:2px;display:block;filter:saturate(.92) contrast(1.02)}
.polaroid .when{font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin:12px 4px 4px}
.polaroid p,.stMarkdown .polaroid p{font-family:"Fraunces",serif;font-size:1rem;line-height:1.5;color:var(--ink);margin:0 4px;font-weight:300}
.tilt-0{transform:rotate(-1.2deg)}.tilt-1{transform:rotate(.9deg)}
.empty{text-align:center;padding:48px 10px;color:var(--mute)}
.empty .serif{font-size:1.6rem;color:var(--ink);font-style:italic}
code{background:#E9E3D5!important;color:var(--ink)!important}
</style>""", unsafe_allow_html=True)


def ring(mins, limit):
    pct = min(mins / limit, 1)
    color = "#B5643C" if pct >= 1 else "#3E6B48"
    c = 2 * 3.14159 * 52
    return (f"<svg width='132' height='132' viewBox='0 0 132 132' role='img' aria-label='{mins} of {limit} minutes'>"
            f"<circle cx='66' cy='66' r='52' fill='none' stroke='#1F2A2012' stroke-width='9'/>"
            f"<circle cx='66' cy='66' r='52' fill='none' stroke='{color}' stroke-width='9' stroke-linecap='round' "
            f"stroke-dasharray='{c * pct:.1f} {c:.1f}' transform='rotate(-90 66 66)'/>"
            f"<text x='66' y='74' text-anchor='middle' font-family='Fraunces,serif' font-size='26' fill='#1F2A20'>"
            f"{int(pct * 100)}%</text></svg>")


@st.cache_data(max_entries=200)
def thumb(path):
    """Small JPEG for the journal grid (full photos can be several MB)."""
    from PIL import Image
    im = Image.open(path)
    im.thumbnail((700, 900))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


port = phone_server()
st.markdown("<div class='eyebrow'><span class='dot'></span>Grounding · runs only on this machine</div>"
            "<div class='hero'>Close the laptop.<br><em>Go touch grass.</em></div>"
            "<div class='sub'>Your screen habits and photos never leave this computer.</div>",
            unsafe_allow_html=True)

status, journal, rep, phone, setup = st.tabs(["Today", "Journal", "Report", "Phone", "Settings"])

with status:
    s = g.status()
    left = max(s["threshold"] - s["screen_minutes"], 0)
    mood = "Time to step away." if s["fatigued"] else ("Fresh and focused." if s["screen_minutes"] < 30
                                                        else f"{left} minutes until your next nudge.")
    st.markdown(f"""<div class='card'><div class='ringwrap'>{ring(s['screen_minutes'], s['threshold'])}
      <div><div class='eyebrow'>On screen since your last break</div>
      <div class='ringnum'>{s['screen_minutes']}<small>min</small></div>
      <div class='state'>{mood}</div>
      <div class='sub' style='margin:0'>{s['journal_count']} moments journaled so far</div></div></div></div>""",
                unsafe_allow_html=True)
    m = s["mission"]
    body = (f"<p class='quote'>{html.escape(m['text'])}</p>" + ("<div class='done' style='margin-top:12px'>✓ completed</div>"
                                                               if m["done"] else "")) if m else \
        "<p class='quote' style='color:#7A7F6E'>No mission yet. Ask for one when you're ready.</p>"
    st.markdown(f"<div class='card'><div class='eyebrow'>Your mission</div>{body}</div>", unsafe_allow_html=True)
    if st.button("Give me a new mission", type="primary"):
        with st.spinner("Finding something to do outside…"):
            try:
                agents.run_mission(force=True)
                st.rerun()
            except RuntimeError as e:
                st.error(e)

with journal:
    up = st.file_uploader("Back from outside? Add your photo", type=["jpg", "jpeg", "png", "webp"])
    if up and st.button("Write my journal entry", type="primary"):
        with st.spinner("Writing your entry…"):
            try:
                st.success(agents.run_reflect(up.getvalue(), up.name)["entry"])
            except RuntimeError as e:
                st.error(e)
    rows = g.db().execute("SELECT * FROM journal ORDER BY id DESC LIMIT 30").fetchall()
    if not rows:
        st.markdown("<div class='empty'><div class='serif'>Nothing here yet.</div>"
                    "Your first moment outside will appear here as a polaroid.</div>", unsafe_allow_html=True)
    cols = st.columns(2, gap="large")
    for i, r in enumerate(rows):
        photo = g.HOME / "photos" / r["photo"]
        img = f"<img src='data:image/jpeg;base64,{thumb(photo)}' alt='Photo from {r['at']}'>" if photo.exists() else ""
        cols[i % 2].markdown(
            f"<div class='polaroid tilt-{i % 2}'>{img}<div class='when'>"
            f"{datetime.fromisoformat(r['at']):%a %d %b · %H:%M}</div><p>{html.escape(r['entry'])}</p></div>",
            unsafe_allow_html=True)

with rep:
    days = st.select_slider("Period", [7, 14, 30], 7, format_func=lambda d: f"Last {d} days")
    s = report.stats(days)
    c1, c2, c3 = st.columns(3)
    c1.metric("Missions", s["missions"])
    c2.metric("Completed", s["done"])
    c3.metric("Longest stretch", f"{s['longest_session_min']} min")
    path = report.build(days)
    st.download_button("Download PDF", path.read_bytes(), path.name, "application/pdf", type="primary")

with phone:
    st.markdown("<div class='card' style='text-align:center'><div class='eyebrow'>Phone app</div>"
                "<div class='state' style='font-size:1.5rem;margin:10px 0 4px'>Scan with your phone camera.</div>"
                "<div class='sub' style='margin:0'>Same Wi-Fi. Then Share → Add to Home Screen.</div></div>",
                unsafe_allow_html=True)
    buf = io.BytesIO()
    segno.make(mobile.phone_url(port)).save(buf, kind="png", scale=8, border=2, dark="#1F2A20", light="#FBF8F1")
    _, mid_col, _ = st.columns([1, 1.2, 1])
    mid_col.image(buf.getvalue(), use_container_width=True)
    if st.button("Unpair all phones"):
        g.set_kv(g.db(), "phone_token", None)
        st.rerun()

with setup:
    txt = st.text_area("What do you enjoy? Missions are built from this (one per line)", "\n".join(g.interests()))
    if st.button("Save", type="primary"):
        (g.HOME / "interests.json").write_text(
            json.dumps([l.strip() for l in txt.splitlines() if l.strip()], indent=2))
        st.success("Saved")
    if os.environ.get("GROUNDING_LAMP"):
        st.markdown("<div class='eyebrow' style='margin-top:24px'>Desk lamp</div>", unsafe_allow_html=True)
        a, b = st.columns(2)
        if a.button("Green (break)"):
            st.info(g.lamp("break"))
        if b.button("Warm (focus)"):
            st.info(g.lamp("focus"))
