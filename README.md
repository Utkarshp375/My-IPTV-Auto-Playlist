# My IPTV Auto Playlist — Multi-source edition

One stable M3U output assembled from the published playlist files of the sportlive18 repositories. GitHub Actions refreshes it every 30 minutes.

## Integrated playlist feeds

| Repository | Imported output |
|---|---|
| [All-Playlist](https://github.com/sportlive18/All-Playlist) | `combined.m3u` |
| [sportlink-update](https://github.com/sportlive18/sportlink-update) | `Combined.m3u` |
| [Fancode-New-Auto-Update](https://github.com/sportlive18/Fancode-New-Auto-Update) | `fancode.m3u` |
| [Sonyliv-Playlist-Autoupdate](https://github.com/sportlive18/Sonyliv-Playlist-Autoupdate) | `sonyliv.m3u`, `sonyliv2.m3u` |

**JioTV repository note:** `sportlive18/jio-tv-auto-update-playlist` currently redirects to `sportlive18/sportlink-update`. It is therefore included once, not fetched twice.

## Reviewed repositories that are not M3U feeds

- [Sportlink-Live](https://github.com/sportlive18/Sportlink-Live) has `api`, `fancode`, `live`, `prime`, `willow`, `world-sports` modules and `fetch_and_generate.py`. The repository page did not expose a verified standalone playlist output URL for these modules in this pass. The integration does not guess an endpoint or execute their scripts blindly. See `INTEGRATION_STATUS.json`.
- [sportlink-10](https://github.com/sportlive18/sportlink-10) contains FanCode web/player pages, not a confirmed M3U output. Its UI is not imported into a playlist generator.

## Output

- `playlist.m3u` — stable root-level playlist URL for IPTV apps
- `data/combined.m3u` — same generated playlist
- `data/channels.json` — channel metadata and update report
- `data/status.json` — last run status

Once uploaded to your own GitHub repository, the playlist URL format is:

`https://raw.githubusercontent.com/YOUR-USERNAME/YOUR-REPOSITORY/main/playlist.m3u`

## Install on Windows

1. Extract the ZIP.
2. Create a new GitHub repository and upload the **contents** of the `my-iptv-hub` folder to its root.
3. Open GitHub → Actions → `Refresh My IPTV Auto Playlist` → Run workflow once.
4. After the first successful run, add the raw `playlist.m3u` URL above to your IPTV player once. The URL remains unchanged as the file contents refresh.

## Refresh and merge behavior

- Runs every 30 minutes (and can be started manually).
- Each feed is fetched independently; a failing feed does not prevent other feeds from being used.
- Exact duplicate stream URLs are removed.
- The importer preserves basic channel name, logo, language and group metadata.
- It imports only direct HTTP(S) HLS `.m3u8` entries. DASH/MPD, DRM/license-key directives, cookie/authentication and injected-header entries are skipped. It does not bypass provider restrictions or renew expired tokens.
- If every feed fails or no usable entries remain, the last good playlist is preserved.
- The importer does not claim to probe every stream for playback. A URL being present does not guarantee it will play in every region or player.

## Attribution

These are upstream repositories maintained by their respective authors. This project consumes their published playlist outputs and does not copy their private credentials or protected playback logic. Follow each repository's license and attribution requirements.
