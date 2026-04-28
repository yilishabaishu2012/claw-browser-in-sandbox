---
domain: xiaohongshu.com
aliases: [小红书, XHS]
updated: 2026-04-27
---

# Xiaohongshu automation notes

## Quick start

```bash
python3 scripts/browser.py start "https://www.xiaohongshu.com"
sleep 3
python3 scripts/interact.py --screenshot /tmp/xhs_status.png
```

## Platform traits

| Trait | Detail |
|-------|--------|
| Rendering | Mixed DOM + Canvas |
| Bot resistance | Medium |
| Element search | `--find` works for some elements |
| Protocol pop-ups | Triggers `weixin://` etc. (blocked by `protocol_guard.js`) |
| Strategy | Combine element search with coordinate clicks |

## Effective patterns

### Pattern 1: element search

```bash
python3 scripts/interact.py --find "登录,手机号"
python3 scripts/interact.py --click-text "获取验证码"
```

### Pattern 2: coordinate click

Reference for 1920×1080:

| Element | X | Y | Note |
|---------|---|---|------|
| Agreement checkbox | 1077 | 586 | Must click first |
| Phone input | 960 | 438 | Center of field |
| Request-code button | 1256 | 438 | Enabled only after agreement |
| Code input | 960 | 520 | SMS code |
| Login button | 960 | 600 | Final step |

## Login flow

**Correct order:**
1. Enter mobile number.
2. **Tick the agreement checkbox** (mandatory).
3. Click "Get verification code".
4. Wait for user to provide the SMS code.
5. Enter the code and click login.

**Wrong order:**
1. Enter mobile number.
2. Click "Get verification code" without ticking agreement → button does nothing.

## Known traps

### Trap 1: requesting code without agreement
**Fix:** Always tick the checkbox first.

### Trap 2: click ignored by site
**Fix:** Retry with `--js-click`.

### Trap 3: "Open WeChat" prompt
**Fix:** `protocol_guard.js` is injected automatically. If it still appears, verify the script path in `browser.py`.

## Updates

- **2026-04-27** — Adapted for `browser-sandbox` rewrite.
