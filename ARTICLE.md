---
title: I built an AI agent that tells me to log off (and it never touches the cloud)
tags: ai, python, opensource, hacktoberfest
---

Everyone is building AI to keep us on screens for longer. For Hacktoberfest I built one that does the opposite: **Grounding** notices when I've been heads-down too long, sends me outside with a specific mission, and turns the photo I bring back into a journal entry.

Everything runs on my laptop: Ollama models, SQLite, and even the phone app.

## The loop

1. **Notice.** Every minute it reads keyboard/mouse idle time (macOS `ioreg`, Windows `GetLastInputInfo`, Linux `xprintidle` or GNOME's IdleMonitor). Five idle minutes count as a real break. Ninety minutes without one and you're "fatigued."
2. **Nudge.** A LangGraph *mission graph* (`sense → router → generate → act`) asks Llama 3.2 3B for a concrete 15–30 minute task built from my interests. Not "take a walk," but *"walk to the nearest tree with an interesting shape, feel the bark, photograph its pattern."* It knows the time of day, so at night it keeps missions indoors, and it avoids repeating recent missions. I get a desktop notification and my desk lamp turns green (Home Assistant, WLED, or any webhook).
3. **Go outside.** The phone app is just a web page my laptop serves over home Wi-Fi. I pair by scanning a QR code: the pairing key becomes an HttpOnly cookie, and unpaired devices get a 401. I tap **Take photo** and the camera opens.
4. **Reflect.** A *reflect graph* (`see → write → save`) has Moondream describe the photo, then Llama writes a three-sentence grounding journal entry. It's saved to SQLite and `grounding_journal.md`, the mission is marked done, the break is logged, and the lamp goes back to warm.
5. **Look back.** A weekly PDF collects missions, completion rate, longest screen stretch, and every photo with its entry.

It's also an **MCP server** (`get_fatigue`, `get_offline_mission`, `journal_photo`, `set_lamp`, `weekly_report`), so Claude, or any MCP client, can check in on me mid-session.

## Why local

These are screen habits and personal photos, possibly with location in the metadata. Sending them to a cloud API just to hear "nice tree" felt wrong. The `bench` command makes the trade-off measurable: it times local Moondream against any OpenAI-compatible vision API on the same photo and records how many bytes left the machine. Locally that's always **0**. On my Mac, Moondream's median was **~5 s** once warm. The cloud side is opt-in, because running it means sending the photo.

## Things that bit me

- **The newest `mcp` is 2.x**, which renamed `FastMCP` to `MCPServer`. I pinned `<2`.
- **Python 3.14** had no wheels yet for part of the dependency tree, so the project pins `<3.14`, which uv handles.
- **The `cgi` module is gone** (since Python 3.13). Multipart phone uploads are parsed with `email.parser` and `policy.HTTP`, about four lines.
- **The PDF fonts are Latin-1 only**, and LLMs love curly quotes and em-dashes. The report uses a system Unicode TTF and falls back to safe replacement.
- **Small models over-trust the prompt.** My first journal prompt led with the mission ("photograph a tree"), so when the photo wasn't a tree the entry still talked about bark. Now the vision description comes first and the mission is labelled "context only."

## Stack

Python · LangGraph · Ollama (Llama 3.2 3B, Moondream) · Streamlit · MCP · SQLite · fpdf2 · a plain stdlib HTTP server for the phone

The meta-joke writes itself: I built an AI during a hackathon whose whole job is to make me stop using my computer. It's the first productivity tool I've made that I actually want to obey.

*Written with AI assistance.*
