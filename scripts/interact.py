#!/usr/bin/env python3
"""
interact.py — CDP-based page interaction tool.
Replaces element.py with a class-based architecture and rewritten internals.
"""

import argparse
import base64
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
import websocket


DEFAULT_CDP_PORT = 18800


class CdpTransport:
    """Manages the WebSocket connection to Chrome DevTools Protocol."""

    def __init__(self, port: int = DEFAULT_CDP_PORT):
        self.port = port
        self._ws_url: str | None = None
        self._seq = 0

    @property
    def ws_url(self) -> str | None:
        if self._ws_url:
            return self._ws_url
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            resp.raise_for_status()
            for page in resp.json():
                if page.get("type") == "page":
                    self._ws_url = page.get("webSocketDebuggerUrl")
                    return self._ws_url
        except Exception as exc:
            print(f"[!] Cannot reach CDP: {exc}", file=sys.stderr)
        return None

    def call(self, method: str, params: dict | None = None) -> dict:
        url = self.ws_url
        if not url:
            raise RuntimeError("CDP WebSocket URL unavailable")

        self._seq += 1
        msg = {"id": self._seq, "method": method, "params": params or {}}

        ws = websocket.create_connection(url, timeout=15)
        try:
            ws.send(json.dumps(msg))
            raw = ws.recv()
            return json.loads(raw)
        finally:
            ws.close()

    def evaluate(self, expression: str, return_by_value: bool = True) -> Any:
        resp = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": return_by_value},
        )
        result = resp.get("result", {})
        inner = result.get("result", {})
        if inner.get("type") == "undefined":
            return None
        return inner.get("value")


class FrameExplorer:
    """Recursively collects frame trees and extracts content from each frame."""

    def __init__(self, transport: CdpTransport):
        self.transport = transport

    def tree(self) -> dict:
        resp = self.transport.call("Page.getFrameTree")
        return resp.get("result", {}).get("frameTree", {})

    def flatten(self, node: dict | None = None) -> list[dict]:
        if node is None:
            node = self.tree()
        out = []
        frame = node.get("frame", {})
        out.append({
            "id": frame.get("id"),
            "parentId": frame.get("parentId"),
            "name": frame.get("name", ""),
            "url": frame.get("url", ""),
        })
        for child in node.get("childFrames", []):
            out.extend(self.flatten(child))
        return out

    def isolated_context_id(self, frame_id: str) -> int | None:
        resp = self.transport.call(
            "Page.createIsolatedWorld",
            {"frameId": frame_id, "worldName": "browser_sandbox_extractor"},
        )
        return resp.get("result", {}).get("executionContextId")

    def content_in_frame(self, frame_id: str) -> dict | None:
        ctx = self.isolated_context_id(frame_id)
        if not ctx:
            return None
        script = """
        (function() {
            function gather() {
                const nodes = [];
                const tree = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_ELEMENT,
                    null,
                    false
                );
                let el;
                while ((el = tree.nextNode())) {
                    const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {width:0,height:0};
                    if (r.width < 2 || r.height < 2) continue;
                    const tag = el.tagName;
                    const role = el.getAttribute('role') || tag.toLowerCase();
                    const label =
                        el.getAttribute('aria-label') ||
                        el.getAttribute('placeholder') ||
                        el.getAttribute('title') ||
                        el.getAttribute('name') ||
                        (el.textContent || '').trim().substring(0, 60) ||
                        (el.value || '').substring(0, 60) ||
                        '';
                    nodes.push({
                        tag: tag,
                        role: role,
                        label: label,
                        type: el.type || '',
                        x: Math.round(r.left),
                        y: Math.round(r.top),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        cx: Math.round(r.left + r.width / 2),
                        cy: Math.round(r.top + r.height / 2),
                    });
                }
                return {
                    url: window.location.href,
                    title: document.title,
                    bodyText: (document.body ? document.body.innerText : '').substring(0, 600),
                    nodes: nodes,
                };
            }
            return gather();
        })()
        """
        resp = self.transport.call(
            "Runtime.evaluate",
            {"expression": script, "contextId": ctx, "returnByValue": True},
        )
        inner = resp.get("result", {}).get("result", {})
        if inner.get("type") == "undefined":
            return None
        return inner.get("value")


class PageScanner:
    """Produces snapshots and searches the current page."""

    def __init__(self, transport: CdpTransport):
        self.transport = transport

    def _run_snapshot_script(self) -> dict:
        script = """
        (function() {
            function visible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && r.top >= 0 && r.left >= 0;
            }
            function labelOf(el) {
                return (
                    el.getAttribute('aria-label') ||
                    el.getAttribute('placeholder') ||
                    el.getAttribute('title') ||
                    el.getAttribute('name') ||
                    (el.textContent || '').trim().substring(0, 50) ||
                    (el.value || '').substring(0, 50) ||
                    ''
                );
            }
            const interactive = new Set(['a','button','input','select','textarea']);
            const all = Array.from(document.querySelectorAll('[role], a, button, input, select, textarea'));
            const items = [];
            for (const el of all) {
                if (!visible(el)) continue;
                const r = el.getBoundingClientRect();
                const name = labelOf(el);
                const role = el.getAttribute('role') || el.tagName.toLowerCase();
                if (!name && !interactive.has(el.tagName.toLowerCase())) continue;
                items.push({
                    role: role,
                    name: name,
                    tag: el.tagName,
                    x: Math.round(r.left),
                    y: Math.round(r.top),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    cx: Math.round(r.left + r.width / 2),
                    cy: Math.round(r.top + r.height / 2),
                });
            }
            return {
                title: document.title,
                url: window.location.href,
                items: items,
            };
        })()
        """
        result = self.transport.evaluate(script)
        if not result:
            return {"title": "", "url": "", "items": []}
        return result

    def snapshot(self) -> dict:
        return self._run_snapshot_script()

    def find(self, keywords: list[str]) -> list[dict]:
        data = self._run_snapshot_script()
        hits = []
        seen = set()
        for item in data.get("items", []):
            name = item.get("name", "").lower()
            role = item.get("role", "").lower()
            for kw in keywords:
                if kw.lower() in name or kw.lower() in role:
                    key = (item.get("cx", item.get("x")), item.get("cy", item.get("y")))
                    if key not in seen:
                        seen.add(key)
                        hits.append(item)
                    break
        return hits


class Actor:
    """Performs mouse/keyboard actions via CDP."""

    def __init__(self, transport: CdpTransport):
        self.transport = transport

    def click_coordinate(self, x: int, y: int) -> None:
        url = self.transport.ws_url
        if not url:
            raise RuntimeError("No CDP connection")
        ws = websocket.create_connection(url, timeout=10)
        try:
            for ev_type in ("mousePressed", "mouseReleased"):
                ws.send(
                    json.dumps({
                        "id": 1,
                        "method": "Input.dispatchMouseEvent",
                        "params": {
                            "type": ev_type,
                            "x": x,
                            "y": y,
                            "button": "left",
                            "clickCount": 1,
                        },
                    })
                )
                ws.recv()
        finally:
            ws.close()
        print(f"Clicked ({x}, {y})")

    def click_by_text(self, text: str, use_js: bool = False) -> bool:
        scanner = PageScanner(self.transport)
        hits = scanner.find([text])
        if not hits:
            print(f"No element matched '{text}', falling back to legacy scan...")
            return self._legacy_click(text, use_js)

        target = hits[0]
        x = target.get("cx", target.get("x", 0))
        y = target.get("cy", target.get("y", 0))
        role = target.get("role", "unknown")
        name = target.get("name", "")[:30]

        if use_js:
            script = f"""
            (function() {{
                const all = document.querySelectorAll('[role], button, a, input');
                for (const el of all) {{
                    const r = el.getBoundingClientRect();
                    if (Math.abs(r.left + r.width/2 - {x}) < 5 &&
                        Math.abs(r.top + r.height/2 - {y}) < 5) {{
                        el.click();
                        return {{ok: true}};
                    }}
                }}
                const fallback = document.elementFromPoint({x}, {y});
                if (fallback) fallback.click();
                return {{ok: true, method: 'fallback'}};
            }})()
            """
            self.transport.evaluate(script)
            print(f"JS-clicked [{role}] '{name}' at ({x}, {y})")
        else:
            self.click_coordinate(x, y)
            print(f"Clicked [{role}] '{name}' at ({x}, {y})")
        return True

    def _legacy_click(self, text: str, use_js: bool) -> bool:
        if use_js:
            script = f"""
            (function() {{
                const keywords = ['{text}'];
                const all = document.querySelectorAll('a, button, div, span');
                for (const el of all) {{
                    const t = (el.innerText || el.textContent || '').trim();
                    for (const kw of keywords) {{
                        if (t.includes(kw)) {{
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0 && r.top > 0 && r.left > 0) {{
                                el.click();
                                return {{ok: true, text: t.substring(0,50), x: Math.round(r.left+r.width/2), y: Math.round(r.top+r.height/2)}};
                            }}
                        }}
                    }}
                }}
                return {{ok: false}};
            }})()
            """
            val = self.transport.evaluate(script)
            if val and val.get("ok"):
                print(f"[Legacy] JS-clicked '{val.get('text')}' at ({val['x']}, {val['y']})")
                return True
            print(f"[Legacy] JS-click failed for '{text}'")
            return False
        else:
            script = f"""
            (function() {{
                const el = Array.from(document.querySelectorAll('*')).find(
                    e => (e.textContent || '').trim().includes('{text}')
                );
                if (el) {{
                    const r = el.getBoundingClientRect();
                    el.click();
                    return {{x: r.left + r.width/2, y: r.top + r.height/2}};
                }}
                return null;
            }})()
            """
            val = self.transport.evaluate(script)
            if val:
                print(f"[Legacy] Clicked '{text}' at ({math.floor(val['x'])}, {math.floor(val['y'])})")
                return True
            print(f"Element '{text}' not found")
            return False

    def type_text(self, text: str) -> None:
        url = self.transport.ws_url
        if not url:
            raise RuntimeError("No CDP connection")
        ws = websocket.create_connection(url, timeout=10)
        try:
            for ch in text:
                ws.send(
                    json.dumps({
                        "id": 1,
                        "method": "Input.dispatchKeyEvent",
                        "params": {"type": "char", "text": ch},
                    })
                )
                ws.recv()
                time.sleep(0.01)
        finally:
            ws.close()
        print(f"Typed: {text}")

    def screenshot(self, out_path: str, display: int = 99) -> bool:
        # Attempt 1: CDP full-page screenshot
        try:
            resp = self.transport.call("Page.captureScreenshot", {"format": "png"})
            data = resp.get("result", {}).get("data")
            if data:
                Path(out_path).write_bytes(base64.b64decode(data))
                print(f"Screenshot saved: {out_path}")
                return True
        except Exception as exc:
            print(f"CDP screenshot failed: {exc}")

        # Attempt 2: viewport-only CDP screenshot
        try:
            resp = self.transport.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
            data = resp.get("result", {}).get("data")
            if data:
                Path(out_path).write_bytes(base64.b64decode(data))
                print(f"Viewport screenshot saved: {out_path}")
                return True
        except Exception as exc:
            print(f"Viewport screenshot failed: {exc}")

        # Attempt 3: X11 screen grab via common tools
        print("Falling back to display capture...")
        tools = [
            ["import", "-window", "root", out_path],
            ["scrot", out_path],
        ]
        env = dict(os.environ)
        env["DISPLAY"] = f":{display}"
        for cmd in tools:
            try:
                subprocess.run(cmd, env=env, check=True, capture_output=True)
                print(f"Display screenshot saved: {out_path}")
                return True
            except Exception:
                continue

        print("Screenshot failed: all methods exhausted", file=sys.stderr)
        return False


def print_snapshot(transport: CdpTransport) -> None:
    scanner = PageScanner(transport)
    data = scanner.snapshot()
    print(f"\nPage: {data.get('title', 'Unknown')}")
    print(f"URL:  {data.get('url', 'Unknown')}\n")
    items = data.get("items", [])
    if items:
        print(f"Elements ({len(items)} visible):")
        for i, it in enumerate(items[:15]):
            role = it.get("role", "unknown")
            name = it.get("name", "")[:35]
            cx, cy = it.get("cx", 0), it.get("cy", 0)
            print(f"  [{i+1}] [{role}] '{name}' ({cx}, {cy})")
        if len(items) > 15:
            print(f"  ... and {len(items) - 15} more")
    else:
        print("No interactive elements detected.")
    print()


def print_full_content(transport: CdpTransport) -> None:
    explorer = FrameExplorer(transport)
    tree = explorer.tree()
    main_frame = tree.get("frame", {})

    print("\n" + "=" * 70)
    print("Full Page Content")
    print("=" * 70)

    # Main frame via PageScanner for richer output
    scanner = PageScanner(transport)
    main_snap = scanner.snapshot()
    print(f"\nMain frame: {main_snap.get('title', 'Unknown')}")
    print(f"  URL: {main_frame.get('url', 'Unknown')}")
    items = main_snap.get("items", [])
    if items:
        print(f"  Elements: {len(items)}")
        for i, it in enumerate(items[:8]):
            print(f"    [{i+1}] [{it.get('role')}] '{it.get('name', '')[:30]}'")

    # Frames
    frames = explorer.flatten()
    child_frames = [f for f in frames if f.get("parentId")]
    if child_frames:
        print(f"\nFound {len(child_frames)} iframe(s):")
        for idx, fr in enumerate(child_frames, 1):
            print(f"\n  [{idx}] {fr.get('name') or 'unnamed'}")
            print(f"       URL: {fr.get('url', 'Unknown')[:60]}")
            content = explorer.content_in_frame(fr["id"])
            if content:
                txt = content.get("bodyText", "")[:80]
                nodes = content.get("nodes", [])
                if txt:
                    print(f"       Text: {txt}...")
                if nodes:
                    key = [n for n in nodes if n.get("tag") in ("INPUT", "BUTTON", "A")]
                    for j, n in enumerate(key[:4]):
                        tag = n.get("tag", "")
                        lbl = n.get("label", "")[:20]
                        print(f"       [{j+1}] {tag}: '{lbl}'")
                    if len(key) > 4:
                        print(f"       ... {len(key) - 4} more")
            else:
                print("       (cross-origin or inaccessible)")
    print("\n" + "=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="CDP page interaction tool")
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT, help="CDP port")
    parser.add_argument("--find", help="Comma-separated keywords to search")
    parser.add_argument("--click", nargs=2, type=int, metavar=("X", "Y"), help="Click at coordinate")
    parser.add_argument("--click-text", help="Click element containing text")
    parser.add_argument("--js-click", action="store_true", help="Use JavaScript click")
    parser.add_argument("--type", dest="type_text", help="Type text into focused element")
    parser.add_argument("--screenshot", help="Save screenshot to path")
    parser.add_argument("--display", type=int, default=99, help="Xvfb display number")
    parser.add_argument("--snapshot", action="store_true", help="Print page snapshot")
    parser.add_argument("--full-content", action="store_true", help="Print main page + iframes")
    args = parser.parse_args()

    transport = CdpTransport(args.port)
    if not transport.ws_url:
        print("Error: cannot connect to browser CDP. Is it running?", file=sys.stderr)
        return 1

    if args.full_content:
        print_full_content(transport)
    elif args.snapshot:
        print_snapshot(transport)

    if args.find:
        scanner = PageScanner(transport)
        keywords = [k.strip() for k in args.find.split(",")]
        hits = scanner.find(keywords)
        if hits:
            print(f"Found {len(hits)} match(es) for {keywords}:")
            for i, h in enumerate(hits[:8]):
                role = h.get("role", "unknown")
                name = h.get("name", "")[:40]
                cx, cy = h.get("cx", 0), h.get("cy", 0)
                print(f"  [{i+1}] [{role}] '{name}' at ({cx}, {cy})")
        else:
            print(f"No matches for {keywords}")

    actor = Actor(transport)

    if args.click:
        actor.click_coordinate(args.click[0], args.click[1])

    if args.click_text:
        actor.click_by_text(args.click_text, use_js=args.js_click)

    if args.type_text:
        actor.type_text(args.type_text)

    if args.screenshot:
        actor.screenshot(args.screenshot, args.display)

    return 0


if __name__ == "__main__":
    sys.exit(main())
