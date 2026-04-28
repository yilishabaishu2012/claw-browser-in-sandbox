---
domain: douyin.com
aliases: [抖音, Douyin]
updated: 2026-04-27
---

# Douyin automation notes

## Quick start

```bash
python3 scripts/browser.py start "https://www.douyin.com"
sleep 5
python3 scripts/interact.py --screenshot /tmp/douyin_status.png
```

Douyin is heavier than most sites; allow 5 s or more for initial load.

## Platform traits

| Trait | Detail |
|-------|--------|
| Rendering | Heavy Canvas + dynamic loading |
| Bot resistance | High; frequent actions trigger verification |
| Element search | `--find` usually returns nothing |
| Strategy | Screenshots first, coordinate clicks second |

## Bait-tab strategy for login

Douyin triggers an OS-level "Open Douyin App?" dialog on first visit. Because the browser is real, this dialog blocks automation.

**Work-around:** open the site in a first tab (bait), let it absorb the dialog, then open a second tab for actual work.

```bash
# Tab 1: bait
cd scripts && python3 browser.py start "https://www.douyin.com"
sleep 5
python3 interact.py --screenshot /tmp/douyin_bait.png

# Tab 2: work (create via raw CDP)
python3 -c "
import json, urllib.request, websocket
pages = json.loads(urllib.request.urlopen('http://127.0.0.1:18800/json/list').read())
ws_url = pages[0]['webSocketDebuggerUrl']
ws = websocket.create_connection(ws_url)
ws.send(json.dumps({'id':1,'method':'Target.createTarget','params':{'url':'https://www.douyin.com'}}))
ws.close()
"
sleep 3
python3 interact.py --screenshot /tmp/douyin_work.png
```

## Known traps

### Trap 1: no elements found
**Cause:** Canvas rendering.
**Fix:** Do not rely on `--find`. Use screenshots and `--js-click` or coordinate clicks.

### Trap 2: page load timeout
**Cause:** Large JS bundles and video assets.
**Fix:** Increase sleep to 5–10 s.

### Trap 3: high CPU
**Cause:** Video decoding + SPA complexity.
**Fix:** Kill Chrome and restart.

## Updates

- **2026-04-27** — Adapted for `browser-sandbox` rewrite.
