
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config" / "sources.json"
DATA_DIR = ROOT / "data"
OUTPUT_FILE = ROOT / "playlist.m3u"

TIMEOUT = 35
MAX_BYTES = 40 * 1024 * 1024

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

# Protected/authenticated stream instructions are never imported.
BLOCKED_MARKERS = (
    "#KODIPROP:",
    "#EXTHTTP:",
    "#EXTVLCOPT:",
    "license_key",
    "license_type",
    "clearkey",
    "cookie=",
    "authorization=",
    "stream_headers=",
    "http-extra-headers",
)

URL_FIELDS = (
    "url", "stream_url", "streamUrl", "m3u8",
    "m3u8_url", "hls_url", "hlsUrl",
    "play_url", "playUrl"
)

NAME_FIELDS = ("name", "channel_name", "channelName", "title")
LOGO_FIELDS = ("logo", "tvg_logo", "image", "icon")
GROUP_FIELDS = ("group", "category", "genre", "language")


def get_text(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
        stream=True
    )
    response.raise_for_status()

    chunks = []
    total = 0

    for chunk in response.iter_content(65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES:
            raise ValueError("Source file exceeds 40 MB")
        chunks.append(chunk)

    return b"".join(chunks).decode("utf-8-sig", errors="replace")


def is_public_hls(url):
    """Accept direct HTTP(S) .m3u8 URLs only."""
    try:
        parsed = urlparse(url.strip())
        return (
            parsed.scheme in ("http", "https")
            and parsed.path.lower().endswith(".m3u8")
            and not parsed.username
            and not parsed.password
        )
    except Exception:
        return False


def clean(value):
    if value is None:
        return ""
    return re.sub(r"[\r\n\t]+", " ", str(value)).strip()


def first_value(item, fields, default=""):
    for field in fields:
        value = item.get(field)
        if value:
            return clean(value)
    return default


def extract_items(data):
    """Handle common JSON list/container layouts."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict):
        for key in ("items", "channels", "data", "results", "channel_list"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                nested = extract_items(value)
                if nested:
                    return nested

    return []


def make_channel(item, source_name, default_group):
    url = first_value(item, URL_FIELDS)

    # MPD and other protected formats are deliberately excluded.
    if not url or not is_public_hls(url):
        return None

    name = first_value(item, NAME_FIELDS, "Unknown Channel")
    logo = first_value(item, LOGO_FIELDS)
    group = first_value(item, GROUP_FIELDS, default_group)

    return {
        "name": name,
        "url": url,
        "logo": logo,
        "group": group or default_group,
        "source": source_name,
    }


def fetch_json_channels(source):
    print(f"[JSON] Fetching {source['name']} ...")
    data = json.loads(get_text(source["url"]))
    items = extract_items(data)

    channels = []
    for item in items:
        channel = make_channel(
            item,
            source["name"],
            source.get("group", source["name"])
        )
        if channel:
            channels.append(channel)

    print(
        f"[JSON] {source['name']}: "
        f"{len(channels)} public HLS channels accepted "
        f"from {len(items)} records"
    )
    return channels


def parse_m3u_source(source):
    print(f"[M3U] Fetching {source['name']} ...")
    content = get_text(source["url"])
    lines = content.splitlines()

    channels = []
    current_info = None
    blocked = False

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("#EXTINF:"):
            current_info = line
            blocked = False
            continue

        if current_info is None:
            continue

        if line.startswith("#"):
            if any(marker in line.lower() for marker in BLOCKED_MARKERS):
                blocked = True
            continue

        url = line

        if blocked or not is_public_hls(url):
            current_info = None
            blocked = False
            continue

        name_match = re.search(r",\s*(.*?)\s*$", current_info)
        name = name_match.group(1) if name_match else source["name"]

        logo_match = re.search(r'tvg-logo="([^"]*)"', current_info)
        group_match = re.search(r'group-title="([^"]*)"', current_info)

        channels.append({
            "name": clean(name),
            "url": url,
            "logo": logo_match.group(1) if logo_match else "",
            "group": group_match.group(1) if group_match else source.get("name", "Other"),
            "source": source["name"],
        })

        current_info = None
        blocked = False

    print(f"[M3U] {source['name']}: {len(channels)} accepted")
    return channels


def make_playlist(channels):
    lines = [
        "#EXTM3U",
        f"#PLAYLIST:{'My IPTV Auto Playlist'}",
    ]

    for channel in channels:
        name = clean(channel["name"]).replace('"', "'")
        logo = clean(channel["logo"]).replace('"', "'")
        group = clean(channel["group"]).replace('"', "'")

        lines.append(
            f'#EXTINF:-1 tvg-name="{name}" '
            f'tvg-logo="{logo}" group-title="{group}",{name}'
        )
        lines.append(channel["url"])

    return "\n".join(lines) + "\n"


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = json.load(file)

    all_channels = []
    failures = []

    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue

        try:
            if source.get("format", "m3u").lower() == "m3u":
                all_channels.extend(parse_m3u_source(source))
        except Exception as error:
            message = f"{source.get('name', 'M3U')}: {error}"
            failures.append(message)
            print("[ERROR]", message)

    for source in config.get("json_sources", []):
        if not source.get("enabled", True):
            continue

        try:
            all_channels.extend(fetch_json_channels(source))
        except Exception as error:
            message = f"{source.get('name', 'JSON')}: {error}"
            failures.append(message)
            print("[ERROR]", message)

    # Deduplicate exact stream URLs.
    unique = []
    seen = set()

    for channel in all_channels:
        url = channel["url"].strip()
        if url in seen:
            continue
        seen.add(url)
        unique.append(channel)

    if not unique:
        print("[FAIL] No usable public HLS channels found.")
        print("[FAIL] Existing playlist has not been overwritten.")
        sys.exit(1)

    playlist = make_playlist(unique)

    OUTPUT_FILE.write_text(playlist, encoding="utf-8")
    (DATA_DIR / "combined.m3u").write_text(playlist, encoding="utf-8")

    with open(DATA_DIR / "channels.json", "w", encoding="utf-8") as file:
        json.dump(unique, file, indent=2, ensure_ascii=False)

    status = {
        "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_channels": len(unique),
        "sources_failed": failures,
    }

    with open(DATA_DIR / "status.json", "w", encoding="utf-8") as file:
        json.dump(status, file, indent=2, ensure_ascii=False)

    print("--------------------------------")
    print(f"[SUCCESS] Total channels: {len(unique)}")
    print(f"[SUCCESS] Playlist: {OUTPUT_FILE}")
    print(f"[INFO] Failed sources: {len(failures)}")
    print("--------------------------------")


if __name__ == "__main__":
    main()
