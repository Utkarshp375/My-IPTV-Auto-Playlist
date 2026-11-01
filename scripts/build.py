from __future__ import annotations
import json, re, sys, time
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.json"
DATA = ROOT / "data"
UA = "MyIPTVHub/2.0 playlist-refresh (+https://github.com/)"
TIMEOUT = 35


def attrs(line: str) -> dict:
    return {k.lower(): v for k, v in re.findall(r'([\w-]+)="([^"]*)"', line)}


def safe_text(value: str) -> str:
    return str(value or "").replace('"', "'").replace("\r", " ").replace("\n", " ").strip()


def parse_m3u(text: str, source_name: str) -> tuple[list[dict], int]:
    """Import direct HLS URLs only; never copy DRM directives or injected credentials/headers."""
    imported, rejected = [], 0
    current = None
    block = []

    def flush():
        nonlocal current, block, rejected
        if current is None:
            block = []
            return
        joined = "\n".join(block).lower()
        blocked = (
            "#kodiprop:", "license_key", "license_type", "#exthttp:",
            "#extvlcopt:", "cookie=", "authorization=", "|user-agent=",
            "|referer=", "|cookie=", "|origin=", "http-extra-headers",
            "stream_headers="
        )
        url_line = next((x.strip() for x in block if x.strip() and not x.strip().startswith("#")), "")
        parsed = urlparse(url_line)
        if (any(x in joined for x in blocked) or "|" in url_line or
            parsed.scheme not in ("http", "https") or not parsed.netloc or
            not parsed.path.lower().endswith(".m3u8")):
            rejected += 1
        else:
            current["url"] = url_line
            current["format"] = "hls"
            current["source"] = source_name
            current["name"] = safe_text(current["name"]) or "Unknown channel"
            current["group"] = safe_text(current["group"]) or "Other"
            current["language"] = safe_text(current["language"])
            imported.append(current)
        current, block = None, []

    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line or line.startswith("#EXTM3U") or line.startswith("#====="):
            continue
        if line.startswith("#EXTINF:"):
            flush()
            title = line.rsplit(",", 1)[-1].strip() if "," in line else "Unknown channel"
            a = attrs(line)
            current = {
                "name": title,
                "tvg_id": a.get("tvg-id", ""),
                "logo": a.get("tvg-logo", ""),
                "language": a.get("tvg-language", a.get("language", "")),
                "group": a.get("group-title", "Other"),
                "source": source_name,
                "url": "", "format": ""
            }
            block = [line]
        elif current is not None:
            block.append(line)
    flush()
    return imported, rejected


def fetch_text(url: str) -> str:
    r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    r.raise_for_status()
    if len(r.content) > 40 * 1024 * 1024:
        raise ValueError("Playlist exceeds 40 MB safety limit")
    return r.text


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    channels, rejected, failures = [], 0, []
    for src in config.get("sources", []):
        if not src.get("enabled", True):
            continue
        name, url = src.get("name", "Playlist"), src.get("url", "")
        if not url:
            continue
        try:
            print(f"Fetching {name}: {url}")
            parsed, skipped = parse_m3u(fetch_text(url), name)
            print(f"  accepted {len(parsed)} HLS entries; skipped {skipped} unsupported/protected entries")
            channels.extend(parsed)
            rejected += skipped
        except Exception as e:
            failures.append(f"{name}: {e}")
            print(f"WARNING: {name}: {e}", file=sys.stderr)

    # Do not overwrite a previously generated playlist with an empty result after a source outage.
    if not channels:
        raise SystemExit("No usable HLS entries fetched. Existing playlist files were left unchanged. " + "; ".join(failures))

    unique, seen = [], set()
    for ch in channels:
        # Exact URL de-duplication preserves separate language/audio variants.
        key = ch["url"].strip()
        if key not in seen:
            seen.add(key)
            unique.append(ch)

    DATA.mkdir(exist_ok=True)
    generated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "title": config.get("playlist_title", "My IPTV Auto Playlist"),
        "generated_at": generated,
        "channel_count": len(unique),
        "source_count": sum(1 for s in config.get("sources", []) if s.get("enabled", True)),
        "sources": [s.get("name", "Playlist") for s in config.get("sources", []) if s.get("enabled", True)],
        "skipped_unsupported_or_protected": rejected,
        "source_failures": failures,
        "epg_urls": config.get("epg_urls", []),
        "repository_integrations": config.get("repository_integrations", []),
        "channels": unique
    }
    (DATA / "channels.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["#EXTM3U"]
    for ch in unique:
        lines.append(
            f'#EXTINF:-1 tvg-id="{safe_text(ch["tvg_id"])}" tvg-name="{safe_text(ch["name"])}" '
            f'tvg-logo="{safe_text(ch["logo"])}" tvg-language="{safe_text(ch["language"])}" '
            f'group-title="{safe_text(ch["group"])}",{safe_text(ch["name"])}'
        )
        lines.append(ch["url"])
    m3u = "\n".join(lines) + "\n"
    (DATA / "combined.m3u").write_text(m3u, encoding="utf-8")
    # Stable root-level alias for IPTV players; content changes, URL does not.
    (ROOT / "playlist.m3u").write_text(m3u, encoding="utf-8")
    (DATA / "status.json").write_text(json.dumps({
        "updated_at": generated, "channels": len(unique), "skipped": rejected,
        "failed_sources": failures
    }, indent=2), encoding="utf-8")
    print(f"SUCCESS: generated {len(unique)} unique HLS entries; skipped {rejected} unsupported/protected entries")

if __name__ == "__main__":
    main()
