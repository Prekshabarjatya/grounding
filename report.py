"""Printable PDF of your offline achievements."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fpdf import FPDF

import grounding as g

FONTS = ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]


def stats(days=7):
    con = g.db()
    since = datetime.now() - timedelta(days=days)
    iso = since.isoformat(timespec="seconds")
    missions = con.execute("SELECT COUNT(*), COALESCE(SUM(done),0) FROM missions WHERE at>=?", (iso,)).fetchone()
    sess = con.execute("SELECT start,end FROM sessions WHERE start>=?", (since.timestamp(),)).fetchall()
    longest = max(((e - s) / 60 for s, e in sess), default=0)
    entries = con.execute("SELECT * FROM journal WHERE at>=? ORDER BY at", (iso,)).fetchall()
    return {"since": since, "missions": missions[0], "done": missions[1], "entries": entries,
            "screen_sessions": len(sess), "longest_session_min": int(longest)}


def build(days=7, out=None):
    s = stats(days)
    pdf = FPDF()
    font = next((f for f in FONTS if Path(f).exists()), None)
    if font:
        pdf.add_font("u", fname=font)
        face, clean = "u", str
    else:  # core fonts are latin-1 only
        face = "helvetica"
        clean = lambda t: t.encode("latin-1", "replace").decode("latin-1")  # noqa: E731
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()
    pdf.set_font(face, size=24)
    pdf.cell(0, 12, clean("Grounding — Offline Achievements"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(face, size=11)
    pdf.set_text_color(100, 110, 100)
    pdf.cell(0, 7, clean(f"{s['since']:%d %b} – {datetime.now():%d %b %Y}  ·  generated on this machine"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_text_color(30, 40, 30)
    pdf.set_font(face, size=13)
    rate = f"{100 * s['done'] // s['missions']}%" if s["missions"] else "-"
    for label, val in [("Missions given", s["missions"]), ("Missions completed", f"{s['done']} ({rate})"),
                       ("Journal entries", len(s["entries"])),
                       ("Longest screen stretch", f"{s['longest_session_min']} min")]:
        pdf.cell(80, 9, label)
        pdf.cell(0, 9, str(val), new_x="LMARGIN", new_y="NEXT")
    for e in s["entries"]:
        pdf.ln(6)
        if pdf.get_y() > 170:
            pdf.add_page()
        pdf.set_font(face, size=14)
        pdf.cell(0, 9, f"{datetime.fromisoformat(e['at']):%a %d %b, %H:%M}", new_x="LMARGIN", new_y="NEXT")
        if e["mission"]:
            pdf.set_font(face, size=10)
            pdf.set_text_color(100, 110, 100)
            pdf.multi_cell(0, 5, clean("Mission: " + e["mission"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 40, 30)
        try:
            pdf.image(str(g.HOME / "photos" / e["photo"]), w=90)
        except Exception:  # unreadable/HEIC photo: keep the entry, skip the picture
            pass
        pdf.set_font(face, size=11)
        pdf.multi_cell(0, 6, clean(e["entry"]), new_x="LMARGIN", new_y="NEXT")
    if not s["entries"]:
        pdf.ln(8)
        pdf.cell(0, 8, "No journal entries yet. Go outside.")
    out = Path(out or g.HOME / f"grounding-report-{datetime.now():%Y-%m-%d}.pdf")
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    print(build(int(sys.argv[1]) if len(sys.argv) > 1 else 7))
