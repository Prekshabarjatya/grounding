"""Self-check, no models needed: uv run test_grounding.py"""
import os, tempfile
os.environ["GROUNDING_HOME"] = tempfile.mkdtemp()
os.environ.pop("GROUNDING_LAMP", None)
import agents, mobile, report
import grounding as g

con = g.db()
assert g.update_session(con, idle=0, now=1000) == 0
assert g.update_session(con, idle=10, now=1000 + 95 * 60) == 95      # still working
assert g.update_session(con, idle=6 * 60, now=1000 + 100 * 60) == 0  # 6 min away = break, reset
assert con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1  # the 94-min stretch was logged

# router: rested → no mission; fatigued once → mission; already nudged → quiet
assert agents.router({"minutes": 10}) == {"route": "rested"}
assert agents.router({"minutes": g.FATIGUE_MIN}) == {"route": "mission"}
assert agents.router({"minutes": g.FATIGUE_MIN, "nudged": True}) == {"route": "already_nudged"}
assert agents.router({"minutes": 0, "force": True}) == {"route": "mission"}

assert g.lamp("break") == "no lamp configured"
assert isinstance(g.idle_seconds(), int)

body = (b"--X\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"leaf.jpg\"\r\n"
        b"Content-Type: image/jpeg\r\n\r\n\xff\xd8JPEGDATA\r\n--X--\r\n")
assert mobile.parse_upload("multipart/form-data; boundary=X", body) == ("leaf.jpg", b"\xff\xd8JPEGDATA")

assert report.build(7).stat().st_size > 500  # empty-week PDF still renders
print("ok")
