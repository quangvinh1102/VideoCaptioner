#!/usr/bin/env python3
"""Generate VideoCaptioner_vi_VN.ts from English translations via Google Translate."""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "resource" / "translations" / "VideoCaptioner_en_US.ts"
DST = ROOT / "resource" / "translations" / "VideoCaptioner_vi_VN.ts"

BASE = "https://translate.googleapis.com/translate_a/single"

MESSAGE_RE = re.compile(r"(<message\b[^>]*>)(.*?)(</message>)", re.DOTALL)
TRANSLATION_RE = re.compile(
    r"(<translation)(\s[^>]*)?>(.*?)</translation>",
    re.DOTALL,
)
TS_OPEN_RE = re.compile(r"<TS\b([^>]*)>")


def log(msg: str) -> None:
    print(msg, flush=True)


def unescape_xml_text(text: str) -> str:
    return html.unescape(text)


def escape_xml_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def google_translate(text: str, retries: int = 4) -> str:
    if not text.strip():
        return text

    params = urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "vi", "dt": "t", "q": text}
    )
    url = f"{BASE}?{params}"
    last_err: Exception | None = None

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; VideoCaptioner/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            parts = data[0] if data and data[0] else []
            return "".join(seg[0] for seg in parts if seg and seg[0])
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = 1.2 * (attempt + 1)
            log(f"  retry {attempt + 1}/{retries} after error: {exc!r} (sleep {wait:.1f}s)")
            time.sleep(wait)

    raise RuntimeError(f"Translate failed for {text[:80]!r}: {last_err}")


def set_ts_language(content: str, language: str = "vi_VN") -> str:
    def repl(m: re.Match[str]) -> str:
        attrs = m.group(1)
        if re.search(r"\blanguage\s*=", attrs):
            attrs = re.sub(
                r'\blanguage\s*=\s*"[^"]*"',
                f'language="{language}"',
                attrs,
            )
        else:
            attrs = attrs.rstrip() + f' language="{language}"'
        return f"<TS{attrs}>"

    return TS_OPEN_RE.sub(repl, content, count=1)


def process_file() -> tuple[int, int]:
    if not SRC.is_file():
        raise FileNotFoundError(f"Missing source: {SRC}")

    content = SRC.read_text(encoding="utf-8")
    messages = list(MESSAGE_RE.finditer(content))
    total = len(messages)
    log(f"Found {total} <message> blocks in {SRC.name}")

    meta: list[dict] = []
    unique_texts: list[str] = []
    unique_index: dict[str, int] = {}

    for m in messages:
        body = m.group(2)
        tm = TRANSLATION_RE.search(body)
        if not tm:
            meta.append({"has_translation": False})
            continue

        attrs = tm.group(2) or ""
        eng = unescape_xml_text(tm.group(3))
        unfinished = 'type="unfinished"' in attrs or "type='unfinished'" in attrs
        empty = not eng.strip()

        entry: dict = {
            "has_translation": True,
            "attrs": attrs,
            "eng": eng,
            "unfinished": unfinished,
            "empty": empty,
            "match": tm,
            "unique_key": None,
        }

        if not empty:
            if eng not in unique_index:
                unique_index[eng] = len(unique_texts)
                unique_texts.append(eng)
            entry["unique_key"] = eng

        meta.append(entry)

    log(f"Unique non-empty strings to translate: {len(unique_texts)}")

    translated_unique: dict[str, str] = {}
    for i, eng in enumerate(unique_texts):
        vi = google_translate(eng)
        translated_unique[eng] = vi

        n = i + 1
        if n % 50 == 0 or n == len(unique_texts):
            log(f"Progress: {n}/{len(unique_texts)} unique translations")

        if n % 5 == 0:
            time.sleep(0.4)
        else:
            time.sleep(0.1)

    pieces: list[str] = []
    last = 0
    translated_count = 0
    skipped_empty = 0

    for idx, m in enumerate(messages):
        pieces.append(content[last : m.start()])
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
        info = meta[idx]

        if not info.get("has_translation"):
            pieces.append(open_tag + body + close_tag)
            last = m.end()
            continue

        tm = info["match"]
        attrs = info["attrs"]

        if info["empty"]:
            skipped_empty += 1
            new_body = body
        else:
            vi = translated_unique[info["unique_key"]]
            vi_esc = escape_xml_text(vi)
            attr_part = attrs if attrs else ""
            new_trans = f"<translation{attr_part}>{vi_esc}</translation>"
            new_body = body[: tm.start()] + new_trans + body[tm.end() :]
            translated_count += 1

        pieces.append(open_tag + new_body + close_tag)
        last = m.end()

        if (idx + 1) % 50 == 0:
            log(f"Progress: {idx + 1}/{total} messages rewritten")

    pieces.append(content[last:])
    out = "".join(pieces)
    out = set_ts_language(out, "vi_VN")

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(out, encoding="utf-8", newline="\n")
    log(f"Wrote {DST}")
    log(
        f"Messages: {total}, translated: {translated_count}, "
        f"empty skipped: {skipped_empty}, unique: {len(unique_texts)}"
    )
    return total, translated_count


def main() -> int:
    total, translated = process_file()
    log(f"Done. total_messages={total} translated={translated} output={DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
