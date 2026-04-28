---
domain: bilibili.com
aliases: [B站, Bilibili]
updated: 2026-04-27
---

# Bilibili automation notes

## Quick start

```bash
python3 scripts/browser.py start "https://www.bilibili.com"
sleep 5
python3 scripts/interact.py --screenshot /tmp/bilibili.png
```

## Platform traits

| Trait | Detail |
|-------|--------|
| Rendering | Standard DOM + some dynamic loading |
| Bot resistance | Medium |
| Element search | `--find` works for many elements |
| Login | Password / SMS / QR code |
| Protocol pop-ups | Uncommon |

## Patterns

### Click login button

The login button sits in the top-right corner. JS clicks are more reliable than CDP mouse events here.

```bash
python3 scripts/interact.py --click-text "登录" --js-click
```

### Search

```bash
python3 scripts/interact.py --click-text "搜索" --js-click
python3 scripts/interact.py --type "OpenClaw"
python3 scripts/interact.py --screenshot /tmp/bilibili_search.png
```

## Known traps

### Trap 1: login button does not react
**Cause:** Coordinate mismatch or event interception.
**Fix:** Use `--js-click`.

### Trap 2: `--find "登录"` returns too many matches
**Cause:** "登录" appears in multiple places (header, sidebars, footers).
**Fix:** Use a more specific keyword, or rely on `--click-text` with `--js-click` to hit the first visible match.

### Trap 3: QR-code login is default
**Fix:** After clicking login, a modal appears. Switch to password/SMS mode manually if automated QR scanning is not available.

## Updates

- **2026-04-27** — Adapted for `browser-sandbox` rewrite.
