---
domain: zhihu.com
aliases: [知乎, Zhihu]
updated: 2026-04-27
---

# Zhihu automation notes

## Quick start

```bash
python3 scripts/browser.py start "https://www.zhihu.com"
sleep 4
python3 scripts/interact.py --screenshot /tmp/zhihu.png
```

## Platform traits

| Trait | Detail |
|-------|--------|
| Rendering | Standard DOM + partial dynamic loading |
| Login | Phone / email / third-party |
| Bot resistance | Medium |
| Protocol pop-ups | Rare |

## Patterns

### Browse a question anonymously

```bash
QUESTION="https://www.zhihu.com/question/XXXXXX"
python3 scripts/browser.py start "$QUESTION"
sleep 4
python3 scripts/interact.py --screenshot /tmp/zhihu_q.png
```

### Search a topic

```bash
python3 scripts/browser.py start "https://www.zhihu.com/search"
sleep 4
python3 scripts/interact.py --click-text "搜索" --js-click
python3 scripts/interact.py --type "keyword"
python3 scripts/interact.py --screenshot /tmp/zhihu_search.png
```

## Known traps

### Trap 1: login wall after scrolling
**Symptom:** A login modal appears after browsing several answers.
**Fix:** Currently only public browsing is well-supported. Login automation requires additional testing.

### Trap 2: click ignored
**Fix:** Retry with `--js-click`.

### Trap 3: infinite scroll
**Fix:** Load more content by scrolling via CDP JavaScript injection if needed.

## Updates

- **2026-04-27** — Adapted for `browser-sandbox` rewrite.
