---
name: browser-sandbox
description: Control a headed Chrome instance via CDP for automation on sites that block headless browsers or trigger app-launch pop-ups (e.g. Xiaohongshu, Douyin).
type: skill
tools: [exec, browser]
---

# Browser Sandbox Skill

## Overview

This skill drives a **real** Chrome window (not headless) over the Chrome DevTools Protocol (CDP). It is designed for scenarios where traditional headless automation is detected or blocked, and where sites attempt to open external apps via custom URI schemes.

**Key capabilities**
- Launches a genuine Chrome process inside an Xvfb virtual display
- Intercepts external protocol requests (`weixin://`, `taobao://`, etc.) before they reach the OS
- Exposes CLI tools for element discovery, clicking, typing, screenshots, and iframe traversal
- Ships per-site scenario notes so the agent knows platform-specific traps upfront

**When to use it**

| Situation | Recommendation |
|-----------|---------------|
| Site blocks headless Chrome | Use this skill |
| App-launch pop-ups interrupt flow | Use this skill (protocol guard is injected automatically) |
| Xiaohongshu, Douyin, etc. | Validated |
| Simple static scrape | Prefer a plain HTTP client or Playwright headless |
| Multi-tab parallel workload | Possible but you must manage tabs manually |

**Trigger phrases**
- "open the browser", "visit with a real browser"
- "Xiaohongshu", "Douyin", "xiaohongshu.com"
- "block the pop-up", "stop app redirect"
- "bypass bot detection"

---

## Prerequisites

```bash
# Debian / Ubuntu
sudo apt-get update
sudo apt-get install -y xvfb google-chrome-stable python3-pip
pip3 install websocket-client requests
```

---

## Concepts

### Path conventions

```
Skill root   = directory containing this SKILL.md
Scripts dir  = Skill root + /scripts/
Scenarios dir = Skill root + /scenarios/
```

Example:
- Skill root: `~/.config/browser-sandbox/`
- Scripts: `~/.config/browser-sandbox/scripts/`
- Scenarios: `~/.config/browser-sandbox/scenarios/`

### Scenario files

**Mandatory lookup before operating on a domain:**

1. Resolve the skill root.
2. Extract the target domain (e.g. `xiaohongshu.com`).
3. Attempt to read `{SKILL_ROOT}/scenarios/{domain}.md`.
4. If missing, fall back to `scenarios/generic.md`.

| File | Loaded when visiting | Notes |
|------|---------------------|-------|
| `xiaohongshu.com.md` | xiaohongshu.com | Checkbox-before-captcha rule |
| `douyin.com.md` | douyin.com | Canvas-heavy, bait-tab strategy |
| `zhihu.com.md` | zhihu.com | Standard DOM, infinite scroll |
| `bilibili.com.md` | bilibili.com | Prefer JS clicks |
| `generic.md` | Any other site | Universal principles |

---

## Tool scripts

### `browser.py` — Browser lifecycle

| Command | Purpose | Example |
|---------|---------|---------|
| `start [URL]` | Launch Chrome (optionally open a URL) | `browser.py start "https://xiaohongshu.com"` |
| `status` | Check whether Chrome is running | `browser.py status` |
| `stop` | Kill Chrome and Xvfb | `browser.py stop` |

**Environment variables**

| Variable | Default | Meaning |
|----------|---------|---------|
| `CDP_PORT` | 18800 | Remote-debugging port |
| `DISPLAY_NUM` | 99 | Xvfb display number |
| `SCREEN_WIDTH` | 1920 | Virtual screen width |
| `SCREEN_HEIGHT` | 1080 | Virtual screen height |
| `CHROME_PATH` | (auto-detect) | Path to Chrome/Chromium binary |

### `interact.py` — Page interaction

| Flag | Purpose | Example |
|------|---------|---------|
| `--find TEXT` | Find elements whose label/role contains the keyword(s) | `--find "login,mobile"` |
| `--click X Y` | Click an absolute coordinate | `--click 960 540` |
| `--click-text TEXT` | Click the first element whose visible text matches | `--click-text "Get code"` |
| `--js-click` | Use a JavaScript `.click()` instead of CDP mouse events | `--click-text "Login" --js-click` |
| `--type TEXT` | Send keystrokes to the currently focused element | `--type "13800138000"` |
| `--screenshot PATH` | Save a PNG (CDP first, Xvfb fallback) | `--screenshot /tmp/page.png` |
| `--snapshot` | Print a compact list of visible interactive elements | `--snapshot` |
| `--full-content` | Dump main page + every accessible iframe | `--full-content` |

**Click retry policy**
1. Inform the user: "Click failed, trying JavaScript click..."
2. Re-run with `--js-click`
3. If still failing, capture a screenshot and describe what is visible.

### `interact_frame.py` — iframe operations

| Flag | Purpose | Example |
|------|---------|---------|
| `--list-frames` | Print the frame tree | `--list-frames` |
| `--iframe PATTERN` | Target an iframe by URL or name substring | `--iframe "x-URS"` |
| `--find-elements` | List elements inside the chosen iframe | `--iframe "login" --find-elements` |
| `--click-text TEXT` | Click by text inside the iframe | `--iframe "dl.reg" --click-text "Login"` |
| `--type TEXT` | Type into the first text input inside the iframe | `--iframe "x-URS" --type "email@163.com"` |
| `--use-mouse` | Use CDP mouse events instead of JS click | `--use-mouse` |

**Mapping to Playwright concepts**

| Playwright | Equivalent here |
|------------|----------------|
| `page.frames` | `--list-frames` |
| `page.frame_locator('iframe')` | `--iframe "pattern"` |
| `frame.locator('input').click()` | `--click-text "placeholder"` |
| `frame.fill('input', 'text')` | `--type "text"` |

---

## Standard workflows

### Open a page and screenshot

```bash
# 1. Start Chrome in the background
python3 scripts/browser.py start "https://www.xiaohongshu.com" &

# 2. Wait for load
sleep 3

# 3. Capture
python3 scripts/interact.py --screenshot /tmp/page.png
```

### Find and click an element

```bash
# 1. Discover elements
python3 scripts/interact.py --find "login,mobile"

# 2. Click by coordinate or text
python3 scripts/interact.py --click 960 540
# or
python3 scripts/interact.py --click-text "Get code" --js-click

# 3. Verify with a screenshot
python3 scripts/interact.py --screenshot /tmp/after.png
```

### Type into a form

```bash
# 1. Focus the field by clicking it
python3 scripts/interact.py --click 960 438

# 2. Type
python3 scripts/interact.py --type "13800138000"

# 3. Verify
python3 scripts/interact.py --screenshot /tmp/typed.png
```

---

## Important notes

### Phone-login workflow (generic)

**You must check the "I agree" box before requesting a verification code.**

| Step | Action | Detail |
|------|--------|--------|
| 1 | Enter mobile number | Focus the phone field, then type |
| 2 | **Check the agreement box** | Mandatory on several platforms |
| 3 | Request code | Button is disabled until step 2 is done |

### Coordinate tips

To obtain coordinates without guessing:
1. Take a screenshot.
2. Open it in an image editor and read the cursor position.
3. Or use `--find` / `--snapshot` to see element centers printed in the terminal.

**Reference coordinates (1920×1080)**

| Site | Element | X | Y |
|------|---------|---|---|
| Xiaohongshu | Agreement checkbox | 1077 | 586 |
| Xiaohongshu | Request-code button | 1256 | 438 |

### Screenshot discipline

Every mutating action should be book-ended by screenshots:

```bash
python3 scripts/interact.py --screenshot /tmp/before.png
python3 scripts/interact.py --click 100 200
python3 scripts/interact.py --screenshot /tmp/after.png
```

---

## Page content discovery

### Why inspect iframes too?

Modern sites embed login forms, payment widgets, and captchas inside cross-origin iframes. Looking only at the main document will miss them.

| Situation | Main page | iframe content | Example |
|-----------|-----------|----------------|---------|
| 163 Mail login | Blank prompt | Full login form | `x-URS-iframe` |
| OAuth authorization | Grant button | Detailed consent text | Third-party login |
| Checkout | Order summary | Card-input fields | Payment iframe |

### Full-content dump

```bash
python3 scripts/interact.py --full-content
```

Sample output:

```
======================================================================
Full Page Content
======================================================================

Main frame: Example Site
  URL: https://example.com
  Elements: 15
    [1] [heading] 'Welcome'
    [2] [textbox] 'Mobile number'
    [3] [button] 'Get code'

Found 2 iframe(s):

  [1] login-frame
       URL: https://login.example.com/form
       Text: Please enter your account...
       Elements: 5
         [1] INPUT[text]: 'Email / mobile'
         [2] INPUT[password]: 'Password'
         [3] BUTTON: 'Login'

  [2] captcha-frame
       (cross-origin or inaccessible)

======================================================================
```

### Discovery cheat-sheet

| Flag | Output | Best for |
|------|--------|----------|
| `--snapshot` | Compact interactive-element list | Quick orientation |
| `--full-content` | Main page + all iframes | Finding embedded forms |
| `--find TEXT` | Filtered matches | Locating a known label |

### Recommended discovery flow

```bash
# 1. Always start with the full dump
python3 scripts/interact.py --full-content

# 2. If a target lives inside an iframe, switch tools
python3 scripts/interact_frame.py --list-frames
python3 scripts/interact_frame.py --iframe "login" --find-elements

# 3. Act inside the frame
python3 scripts/interact_frame.py --iframe "login" --click-text "Login"

# 4. Confirm
python3 scripts/interact.py --screenshot /tmp/result.png
```

---

## How it works

### Protocol guard

`protocol_guard.js` is injected at page-load time via Chrome's `--inject-js` flag. It wraps:
- `window.location` (via Proxy or descriptor override)
- `window.open`
- `history.pushState` / `replaceState`
- All `<a>` clicks (capture-phase listener)
- Dynamically injected anchors (MutationObserver)

Any URL whose scheme matches `^(weixin|wechat|alipay|taobao|openapp|dianping|meituan|jd|tmall)://` is silently dropped and logged to the console.

### Screenshot pipeline

```
1. CDP Page.captureScreenshot (full page)
2. If that fails → CDP viewport screenshot
3. If that fails → X11 grab via ImageMagick import / scrot
4. If all fail → report error
```

### CDP wiring

```
interact.py  ──WebSocket──►  Chrome CDP (port 18800)
       │                         │
       └──── commands ───────────┘
```

### iframe traversal

`Page.getFrameTree` returns a nested frame tree. `interact_frame.py`:
1. Recursively walks the tree.
2. Creates an isolated execution world (`Page.createIsolatedWorld`) inside the target frame.
3. Runs extraction or interaction scripts inside that world.
4. For mouse clicks, computes the iframe's offset in the parent document and adds it to the element's local coordinates.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Chrome won't start | Xvfb missing | `apt-get install xvfb` |
| CDP connection refused | Chrome not started or wrong port | Run `browser.py status`; adjust `CDP_PORT` |
| Element not found | Page still loading | Increase `sleep` |
| Click does nothing | Wrong coordinates or bot detection | Use `--js-click`; verify with screenshot |
| Text input ignored | Input not focused | Click the field first, then type |
| Screenshot blank | Canvas/WebGL page | Xvfb fallback usually succeeds |
| Chrome CPU spikes | Complex SPA or memory leak | `pkill -9 chrome && pkill -9 Xvfb` |

### Hard reset

```bash
pkill -9 chrome
pkill -9 Xvfb
ps aux | grep -E "chrome|Xvfb" | grep -v grep
```

---

## Best practices

1. **Plan before acting** — Know the target URL and the expected sequence of clicks/inputs.
2. **Read the scenario file** — Per-site notes save time.
3. **Pause between steps** — Pages need time to react; screenshots prove the state.
4. **Clean up** — Run `browser.py stop` when the task ends.
5. **Update scenario files** — New traps or successful patterns should be recorded for the next run.

---

## File layout

```
browser-sandbox/
├── SKILL.md                         # This file
├── README.md                        # Quick-start for humans
├── scripts/
│   ├── browser.py                   # Chrome / Xvfb lifecycle
│   ├── interact.py                  # Element interaction & screenshots
│   ├── interact_frame.py            # iframe-aware operations
│   └── protocol_guard.js            # External-protocol blocker
└── scenarios/
    ├── xiaohongshu.com.md           # Xiaohongshu quirks
    ├── douyin.com.md                # Douyin quirks
    ├── zhihu.com.md                 # Zhihu quirks
    ├── bilibili.com.md              # Bilibili quirks
    └── generic.md                   # Universal guidelines
```

---

## Appendix

### CDP vs Playwright iframe APIs

| Task | CDP (this skill) | Playwright |
|------|-----------------|------------|
| List frames | `Page.getFrameTree` | `page.frames` |
| Enter a frame | `Page.createIsolatedWorld` + `Runtime.evaluate` | `page.frame_locator(selector)` |
| Click inside frame | `Runtime.evaluate` with `.click()` | `frame_locator.locator().click()` |
| Cross-origin frames | Manual context switching | Handled automatically |

### Version note

This rewrite (`browser-sandbox`) preserves the architecture and behaviour of the original `headed-browser-open-v3` skill while re-implementing every script from scratch in Python (lifecycle manager, element operator, iframe operator) and modernising the protocol guard.
