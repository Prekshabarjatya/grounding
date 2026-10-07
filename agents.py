"""LangGraph agents.

mission graph:  sense → router ─┬─ (rested / already nudged) → END
                                └─ (fatigued or asked) → generate → act (lamp + notify) → END
reflect graph:  see (vision model) → write (journal agent) → save (DB, journal.md, lamp back) → END
"""
import base64
from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, StateGraph

import grounding as g


class MissionState(TypedDict, total=False):
    force: bool
    nudged: bool
    minutes: int
    route: str
    mission: str
    lamp: str


def sense(s):
    return {"minutes": g.update_session(g.db(), g.idle_seconds())}


def router(s):
    if s.get("force"):
        return {"route": "mission"}
    if s["minutes"] < g.FATIGUE_MIN:
        return {"route": "rested"}
    return {"route": "already_nudged" if s.get("nudged") else "mission"}


def generate(s):
    con = g.db()
    hour = datetime.now().hour
    when = "night" if hour >= 20 or hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    recent = [r["text"] for r in con.execute("SELECT text FROM missions ORDER BY id DESC LIMIT 5")]
    prompt = (f"The user has been on a screen for {s['minutes']} minutes. It is {when}. "
              f"Their interests: {', '.join(g.interests())}.\n"
              f"Do not repeat these recent missions: {recent}\n"
              "Write ONE specific offline mission of 15-30 minutes that gets them away from screens "
              "and ends with taking one photo of something real. Be concrete and sensory "
              "(e.g. 'Walk to the nearest tree, find bark with an unusual texture and photograph it'). "
              + ("It is dark out, so keep it indoors or on a lit balcony. " if when == "night" else "")
              + "Reply with the mission only, one or two sentences, no preamble.")
    text = g.ollama(g.TEXT_MODEL, prompt).strip().strip('"')
    con.execute("INSERT INTO missions(at,text) VALUES(?,?)", (datetime.now().isoformat(timespec="seconds"), text))
    con.commit()
    return {"mission": text}


def act(s):
    msg = g.lamp("break")
    if not s.get("force"):
        g.notify(s["mission"])
    return {"lamp": msg}


_m = StateGraph(MissionState)
for name, fn in [("sense", sense), ("router", router), ("generate", generate), ("act", act)]:
    _m.add_node(name, fn)
_m.set_entry_point("sense")
_m.add_edge("sense", "router")
_m.add_conditional_edges("router", lambda s: s["route"],
                         {"mission": "generate", "rested": END, "already_nudged": END})
_m.add_edge("generate", "act")
_m.add_edge("act", END)
mission_graph = _m.compile()


class ReflectState(TypedDict, total=False):
    photo: bytes
    name: str
    mission_id: int
    mission: str
    seen: str
    entry: str
    path: str


def see(s):
    m = g.db().execute("SELECT * FROM missions WHERE done=0 ORDER BY id DESC LIMIT 1").fetchone()
    seen = g.ollama(g.VISION_MODEL, "Describe this photo in detail: objects, colours, light, textures.",
                    [base64.b64encode(s["photo"]).decode()])
    return {"seen": seen, "mission": m["text"] if m else "", "mission_id": m["id"] if m else 0}


def write(s):
    entry = g.ollama(g.TEXT_MODEL,
                     f"Someone stepped away from their screen and photographed this. What the photo shows: {s['seen']}\n"
                     + (f"(For context only, they had been asked to: {s['mission']})\n" if s["mission"] else "")
                     + "Write a 3-sentence reflective, grounding journal entry in second person about what is "
                     "actually in the photo. Never describe things that aren't in the photo description. "
                     "Do not mention AI, screens, photos or technology. No preamble.")
    return {"entry": entry}


def save(s):
    con, now = g.db(), datetime.now()
    dest = g.save_photo(s["photo"], s.get("name", "photo.jpg"))
    con.execute("INSERT INTO journal(at,mission,photo,entry) VALUES(?,?,?,?)",
                (now.isoformat(timespec="seconds"), s["mission"] or None, dest.name, s["entry"]))
    if s["mission_id"]:
        con.execute("UPDATE missions SET done=1 WHERE id=?", (s["mission_id"],))
    g.take_break(con)
    con.commit()
    with open(g.HOME / "grounding_journal.md", "a") as f:
        f.write(f"\n## {now:%a %d %b %Y, %H:%M}\n" + (f"*Mission:* {s['mission']}\n\n" if s["mission"] else "")
                + f"![](photos/{dest.name})\n\n{s['entry']}\n")
    g.lamp("focus")
    return {"path": dest.name}


_r = StateGraph(ReflectState)
for name, fn in [("see", see), ("write", write), ("save", save)]:
    _r.add_node(name, fn)
_r.set_entry_point("see")
_r.add_edge("see", "write")
_r.add_edge("write", "save")
_r.add_edge("save", END)
reflect_graph = _r.compile()


def run_mission(force=True, nudged=False):
    return mission_graph.invoke({"force": force, "nudged": nudged})


def run_reflect(photo, name="photo.jpg"):
    return reflect_graph.invoke({"photo": photo, "name": name})
