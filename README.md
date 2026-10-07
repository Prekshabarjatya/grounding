# Grounding 🌱

An AI agent that tells you to log off. It notices long screen sessions, hands you a concrete offline mission, and turns the photo you bring back into a journal entry. **Everything runs on your machine**: Ollama models, local SQLite, and a phone app served over your own Wi-Fi. No cloud calls, no telemetry.

```
                ┌──────────── mission graph (LangGraph) ─────────────┐
idle time ──►  sense ──► router ──► generate (Llama 3.2) ──► act ──┼──► notification + lamp turns green
(mac/win/linux)            └─ rested / already nudged → END        │
                └────────────────────────────────────────────────────┘
                ┌──────────── reflect graph (LangGraph) ─────────────┐
phone camera ─► see (Moondream) ──► write (Llama 3.2) ──► save ─────┼──► journal.md + SQLite, lamp back to warm
                └────────────────────────────────────────────────────┘
        surfaces: Streamlit dashboard · phone web app (PWA) · MCP server · CLI · weekly PDF
```

## Quick start

```bash
ollama pull llama3.2:3b && ollama pull moondream
uv sync
uv run streamlit run app.py      # dashboard + phone app server (QR in "Phone app" tab)
uv run grounding.py watch        # background nudger
```

## Pieces

| | |
|---|---|
| `grounding.py` | core: SQLite store, cross-platform idle detection, Ollama client, lamp, notifications, CLI |
| `agents.py` | the two LangGraph graphs (mission, reflect) |
| `app.py` | Streamlit dashboard: today, journal (polaroids), report PDF, phone pairing QR, settings |
| `mobile.py` + `mobile.html` | phone app: installable web app with camera capture, paired by QR |
| `mcp_server.py` | MCP tools: `get_fatigue`, `get_offline_mission`, `journal_photo`, `set_lamp`, `weekly_report` |
| `report.py` | printable PDF of offline achievements (photos + entries + stats) |
| `bench.py` | local vs cloud vision latency on the same photo |

### CLI
```bash
uv run grounding.py mission | reflect PHOTO | status | report [DAYS] | bench PHOTO | phone [PORT] | watch
```

### Phone app
Open the dashboard's **Phone** tab and scan the QR code with a phone on the same Wi-Fi. Then choose **Add to Home Screen**. The QR code holds a private pairing key, which is swapped for an HttpOnly cookie. Unpaired devices get a 401. **Unpair all phones** rotates the key. Photos travel phone → your computer only. Port `8766` (`GROUNDING_PHONE_PORT`).

### MCP (Claude Code / Desktop / any client)
```bash
claude mcp add grounding -- uv run --project ~/Documents/grounding ~/Documents/grounding/mcp_server.py
```

### Fatigue detection
| OS | Source |
|---|---|
| macOS | `ioreg` HIDIdleTime |
| Windows | `GetLastInputInfo` |
| Linux | `xprintidle` (X11) or GNOME Mutter IdleMonitor (Wayland) |
| fallback | age of `~/.zsh_history` / `~/.bash_history` |

Five or more minutes idle counts as a break, and so does completing a mission. Each screen stretch is logged to the report.

### Smart lamp
```bash
GROUNDING_LAMP=homeassistant HA_URL=http://homeassistant.local:8123 HA_TOKEN=… HA_LIGHT=light.desk
GROUNDING_LAMP=wled WLED_URL=http://wled.local
GROUNDING_LAMP=webhook GROUNDING_LAMP_WEBHOOK=http://…   # receives {"state":"break|focus","rgb":[r,g,b]}
```
The lamp turns green when a mission is issued and warm after you journal. Test it from the dashboard.

### Benchmark
`uv run grounding.py bench photo.jpg` times the local model (after a warm-up run) and records the results in `~/.grounding/benchmarks.jsonl`. The cloud comparison is **opt-in**: set `CLOUD_VISION_KEY` (or `OPENAI_API_KEY`). It works with any OpenAI-compatible endpoint (`CLOUD_VISION_URL`, `CLOUD_VISION_MODEL`), and it sends that one photo to that provider.

### Config
| Var | Default |
|---|---|
| `GROUNDING_FATIGUE_MIN` | `90` |
| `GROUNDING_TEXT_MODEL` / `GROUNDING_VISION_MODEL` | `llama3.2:3b` / `moondream` |
| `GROUNDING_HOME` | `~/.grounding` (DB, photos, journal.md, interests.json, reports) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` |

## Privacy
- Models, data and photos stay on this computer.
- The dashboard is local. The phone server listens on your LAN and requires a pairing cookie; photo paths are sanitised.
- The only optional outbound calls are the lamp (your own device) and the opt-in cloud benchmark.

## Test
```bash
uv run test_grounding.py
```
