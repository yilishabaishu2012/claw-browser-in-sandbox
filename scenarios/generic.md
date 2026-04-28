---
domain: generic
aliases: [通用场景, default]
updated: 2026-04-27
---

# Generic automation guidelines

This file collects principles that apply to most sites when driven through Browser Sandbox.

## Principles

### 1. Screenshot-first verification
Every mutating action (click, type, navigation) should be followed by a screenshot. This proves the state changed as expected and makes debugging possible.

```bash
python3 scripts/interact.py --screenshot /tmp/before.png
python3 scripts/interact.py --click 960 540
python3 scripts/interact.py --screenshot /tmp/after.png
```

### 2. Dynamic discovery over hard-coded coordinates
Coordinates vary with resolution, zoom level, and responsive layout. Prefer querying the DOM via CDP, then using the returned element centers.

```bash
python3 scripts/interact.py --find "login,mobile"
python3 scripts/interact.py --click-text "Get code"
```

If you must use coordinates, derive them from a screenshot rather than copying tables.

### 3. Focus before typing
Text sent via CDP key events goes to the focused element. If nothing is focused, the input is lost.

Correct sequence:
1. Click the target input field.
2. Type the text.
3. Screenshot to verify.

### 4. Agreement checkboxes block forms
Some platforms disable the "Get verification code" button until a terms-of-service checkbox is ticked. The agent must discover and click that checkbox first.

## Standard phone-login flow

| Step | Action |
|------|--------|
| 1 | Open the site, screenshot to confirm load |
| 2 | Click the login entry point |
| 3 | Enter the mobile number |
| 4 | **Tick the agreement checkbox** (if present) |
| 5 | Request the verification code |
| 6 | Enter the code and submit |

## Platform traits

| Trait | Observation |
|-------|-------------|
| Element discovery | `--find` can fail on heavily dynamic pages (React/Vue/Canvas). Use `--snapshot` or `--full-content` instead. |
| Coordinate clicks | Reliable, but brittle across resolutions. |
| Text input | Always requires prior focus. |
| CDP screenshots | Fast, but may fail on Canvas/WebGL. Xvfb fallback is more reliable in those cases. |

## Known traps

### Trap: element discovery returns nothing
**Symptom:** `--find` reports zero matches.
**Cause:** The site renders text inside Canvas or uses virtual scrolling.
**Fix:** Rely on screenshots and coordinate clicks, or use `--js-click` with a keyword.

### Trap: click appears to do nothing
**Symptom:** Screenshot before and after are identical.
**Cause:** The element moved, or the site ignores untrusted mouse events.
**Fix:**
1. Retry with `--js-click`.
2. If that fails, inspect the page again (`--snapshot`) to see whether a modal or overlay intercepted the event.

### Trap: typed text does not appear
**Symptom:** Input field stays empty after `--type`.
**Cause:** The field never received focus.
**Fix:** Click the field first, wait briefly, then type.

### Trap: verification-code button is inert
**Symptom:** Clicking "Get code" produces no SMS.
**Cause:** The agreement checkbox is unchecked.
**Fix:** Search for checkbox-like elements near the phone field and click them before requesting the code.

### Trap: screenshot is blank or partial
**Symptom:** PNG is white or missing content.
**Cause:** The page draws via Canvas/WebGL.
**Fix:** The Xvfb fallback (`import -window root`) usually captures the virtual screen correctly.

## Updates

- **2026-04-27** — Re-structured as generic guidelines for the rewritten `browser-sandbox` skill.
