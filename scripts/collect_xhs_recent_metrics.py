import argparse
import asyncio
import json
import re
import urllib.request
from pathlib import Path

import websockets


DEFAULT_DEBUG_PORT = 9226
DEFAULT_URL_PREFIX = "https://creator.xiaohongshu.com/new/note-manager"


async def evaluate_page(page_ws_url: str, expression: str) -> dict:
    async with websockets.connect(page_ws_url, open_timeout=20, max_size=2**24) as conn:
        await conn.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                    },
                }
            )
        )

        while True:
            raw = await conn.recv()
            payload = json.loads(raw)
            if payload.get("id") == 1:
                return payload


def get_page_ws_url(debug_port: int, url_prefix: str) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=10) as response:
        pages = json.loads(response.read().decode("utf-8"))
    for page in pages:
        if page.get("url", "").startswith(url_prefix):
            return page["webSocketDebuggerUrl"]
    raise RuntimeError(f"No page found for prefix: {url_prefix}")


def parse_note_text(note_text: str) -> dict:
    normalized = re.sub(r"\s+", " ", note_text).strip()
    parts = [part for part in normalized.split(" ") if part]
    if len(parts) < 8:
        return {"raw": normalized}

    title = parts[0]
    publish_date = parts[2]
    publish_time = parts[3]
    tail_numbers = []
    for part in parts[4:]:
        if re.fullmatch(r"\d+", part):
            tail_numbers.append(int(part))
        else:
            break

    metrics = {
        "rawSequence": tail_numbers,
    }
    if len(tail_numbers) >= 5:
        metrics.update(
            {
                "view": tail_numbers[0],
                "comment": tail_numbers[1],
                "like": tail_numbers[2],
                "collect": tail_numbers[3],
                "share": tail_numbers[4],
            }
        )

    return {
        "title": title,
        "publishedAt": f"{publish_date} {publish_time}",
        "metrics": metrics,
        "raw": normalized,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug-port", type=int, default=DEFAULT_DEBUG_PORT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    page_ws_url = get_page_ws_url(args.debug_port, DEFAULT_URL_PREFIX)
    expression = """
      JSON.stringify({
        title: document.title,
        href: location.href,
        lines: (document.body && document.body.innerText ? document.body.innerText : '')
          .split(/\\n+/)
          .map(line => line.replace(/\\s+/g, ' ').trim())
          .filter(Boolean)
          .slice(0, 240),
        notes: Array.from(document.querySelectorAll('.note'))
          .slice(0, 12)
          .map(note => ({
            text: (note.innerText || '').replace(/\\s+/g, ' ').trim(),
            html: note.innerHTML.slice(0, 4000)
          }))
      })
    """
    result = await evaluate_page(page_ws_url, expression)
    value = result["result"]["result"]["value"]
    data = json.loads(value)
    data["parsedNotes"] = [parse_note_text(item["text"]) for item in data.get("notes", [])]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
