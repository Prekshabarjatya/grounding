"""Local vs cloud vision latency on the same photo.

Cloud is opt-in: it only runs when CLOUD_VISION_KEY (or OPENAI_API_KEY) is set, and it sends
the chosen photo to that provider. Any OpenAI-compatible endpoint works (OpenAI, OpenRouter, Groq…).
"""
import base64, json, os, statistics, time, urllib.request
from datetime import datetime
from pathlib import Path

import grounding as g

PROMPT = "Describe this photo in detail: objects, colours, light, textures."
CLOUD_URL = os.environ.get("CLOUD_VISION_URL", "https://api.openai.com/v1/chat/completions")
CLOUD_MODEL = os.environ.get("CLOUD_VISION_MODEL", "gpt-4o-mini")


def local(b64):
    return g.ollama(g.VISION_MODEL, PROMPT, [b64])


def cloud(b64, key):
    body = {"model": CLOUD_MODEL, "max_tokens": 300, "messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    req = urllib.request.Request(CLOUD_URL, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def timed(fn, runs):
    fn()  # warm-up: model load / TLS setup shouldn't count
    times, out = [], ""
    for _ in range(runs):
        t = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t)
    return {"median_s": round(statistics.median(times), 2), "min_s": round(min(times), 2),
            "runs": runs, "sample": out[:200]}


def run(photo: Path, runs=3):
    b64 = base64.b64encode(photo.read_bytes()).decode()
    res = {"photo": photo.name, "at": datetime.now().isoformat(timespec="seconds"),
           "local": {"model": g.VISION_MODEL, "bytes_sent_off_machine": 0, **timed(lambda: local(b64), runs)}}
    key = os.environ.get("CLOUD_VISION_KEY") or os.environ.get("OPENAI_API_KEY")
    if key:
        try:
            res["cloud"] = {"model": CLOUD_MODEL, "bytes_sent_off_machine": len(b64),
                            **timed(lambda: cloud(b64, key), runs)}
        except (OSError, KeyError) as e:
            res["cloud"] = {"model": CLOUD_MODEL, "error": str(e)}
    else:
        res["cloud"] = {"skipped": "set CLOUD_VISION_KEY or OPENAI_API_KEY to compare"}
    with open(g.HOME / "benchmarks.jsonl", "a") as f:
        f.write(json.dumps(res) + "\n")
    return res
