# Browser Sandbox

[中文](./README.zh.md) | English

A CDP-based automation toolkit that drives a **real headed Chrome** instance inside an Xvfb virtual display. Built for sites where headless automation is detected or blocked, and where external app-launch pop-ups (e.g. `weixin://`, `taobao://`) interrupt workflows.

## Quick start

```bash
# Install dependencies
sudo apt-get install -y xvfb google-chrome-stable python3-pip
pip3 install websocket-client requests

# Launch Chrome and open a site
python3 scripts/browser.py start "https://www.xiaohongshu.com"

# Wait for the page to settle
sleep 3

# Take a screenshot
python3 scripts/interact.py --screenshot /tmp/xhs.png

# Stop everything when done
python3 scripts/browser.py stop
```

## What is inside

| Script | Purpose |
|--------|---------|
| `scripts/browser.py` | Start / stop Chrome + Xvfb |
| `scripts/interact.py` | Find elements, click, type, screenshot |
| `scripts/interact_frame.py` | Operate inside `<iframe>` elements |
| `scripts/protocol_guard.js` | Injected script that blocks external URI schemes |
| `scenarios/*.md` | Per-site notes and known traps |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CDP_PORT` | `18800` | Chrome remote-debugging port |
| `DISPLAY_NUM` | `99` | Xvfb display number |
| `SCREEN_WIDTH` | `1920` | Virtual display width |
| `SCREEN_HEIGHT` | `1080` | Virtual display height |
| `CHROME_PATH` | auto-detect | Path to Chrome or Chromium binary |

## Common tasks

### Screenshot

```bash
python3 scripts/interact.py --screenshot /tmp/page.png
```

### Find and click an element

```bash
python3 scripts/interact.py --find "login"
python3 scripts/interact.py --click-text "login" --js-click
```

### Type text into a focused input

```bash
python3 scripts/interact.py --click 960 540
python3 scripts/interact.py --type "hello world"
```

### Inspect iframes

```bash
python3 scripts/interact_frame.py --list-frames
python3 scripts/interact_frame.py --iframe "login" --find-elements
python3 scripts/interact_frame.py --iframe "login" --click-text "Submit"
```

## Architecture

```
┌─────────────────┐     WebSocket      ┌──────────────┐
│  interact.py    │ ◄────────────────► │ Chrome + CDP │
│  interact_frame │                    │  (port 18800)│
└─────────────────┘                    └──────────────┘
       ▲                                      │
       │      HTTP (json/list)                │
       └──────────────────────────────────────┘

Chrome runs inside Xvfb (:99) so no physical monitor is required.
```

## License

MIT
