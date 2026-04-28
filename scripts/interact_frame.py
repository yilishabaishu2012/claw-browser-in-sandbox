#!/usr/bin/env python3
"""
interact_frame.py — Operate inside iframes via CDP.
Rewritten with a class-based transport and redesigned frame traversal.
"""

import argparse
import json
import math
import sys
import time

import requests
import websocket

DEFAULT_CDP_PORT = 18800


class CdpConn:
    """Lightweight CDP WebSocket wrapper."""

    def __init__(self, port: int = DEFAULT_CDP_PORT):
        self.port = port
        self._url: str | None = None
        self._counter = 0

    @property
    def url(self) -> str | None:
        if self._url:
            return self._url
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            resp.raise_for_status()
            for page in resp.json():
                if page.get("type") == "page":
                    self._url = page.get("webSocketDebuggerUrl")
                    return self._url
        except Exception as exc:
            print(f"[!] CDP unreachable: {exc}", file=sys.stderr)
        return None

    def send(self, method: str, params: dict | None = None) -> dict:
        if not self.url:
            raise RuntimeError("No CDP URL")
        self._counter += 1
        payload = {"id": self._counter, "method": method, "params": params or {}}
        ws = websocket.create_connection(self.url, timeout=15)
        try:
            ws.send(json.dumps(payload))
            return json.loads(ws.recv())
        finally:
            ws.close()

    def eval_js(self, expression: str, context_id: int | None = None) -> any:
        params: dict = {"expression": expression, "returnByValue": True}
        if context_id is not None:
            params["contextId"] = context_id
        resp = self.send("Runtime.evaluate", params)
        inner = resp.get("result", {}).get("result", {})
        if inner.get("type") == "undefined":
            return None
        return inner.get("value")


class FrameCtl:
    """Frame tree inspection and iframe interaction."""

    def __init__(self, conn: CdpConn):
        self.conn = conn

    def get_tree(self) -> dict:
        resp = self.conn.send("Page.getFrameTree")
        return resp.get("result", {}).get("frameTree", {})

    def walk(self, node: dict | None = None, depth: int = 0) -> list[dict]:
        if node is None:
            node = self.get_tree()
        out = []
        frame = node.get("frame", {})
        out.append({
            "id": frame.get("id", ""),
            "parentId": frame.get("parentId"),
            "name": frame.get("name", ""),
            "url": frame.get("url", ""),
            "depth": depth,
        })
        for child in node.get("childFrames", []):
            out.extend(self.walk(child, depth + 1))
        return out

    def resolve_frame(self, pattern: str) -> dict | None:
        pattern_l = pattern.lower()
        for fr in self.walk():
            if pattern_l in fr["url"].lower() or pattern_l in fr["name"].lower():
                return fr
        return None

    def isolated_context(self, frame_id: str) -> int | None:
        resp = self.conn.send(
            "Page.createIsolatedWorld",
            {"frameId": frame_id, "worldName": "browser_sandbox_frame"},
        )
        return resp.get("result", {}).get("executionContextId")

    def eval_in_frame(self, frame_id: str, expression: str):
        ctx = self.isolated_context(frame_id)
        if not ctx:
            raise RuntimeError(f"Cannot create isolated world for frame {frame_id}")
        return self.conn.eval_js(expression, ctx)

    def elements_in_frame(self, frame_id: str) -> list[dict]:
        script = """
        (function() {
            const out = [];
            const sel = document.querySelectorAll('input, button, a, select, textarea, [role]');
            for (const el of sel) {
                const r = el.getBoundingClientRect();
                if (r.width < 1 || r.height < 1) continue;
                out.push({
                    tag: el.tagName,
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    text: (el.innerText || el.textContent || '').trim().substring(0, 40),
                    role: el.getAttribute('role') || '',
                    x: Math.round(r.left),
                    y: Math.round(r.top),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    cx: Math.round(r.left + r.width/2),
                    cy: Math.round(r.top + r.height/2),
                });
            }
            return out;
        })()
        """
        val = self.eval_in_frame(frame_id, script)
        return val or []

    def click_text_in_frame(self, frame_id: str, text: str, use_mouse: bool) -> bool:
        script = f"""
        (function() {{
            const kw = '{text}';
            const all = document.querySelectorAll('a, button, input, div, span');
            for (const el of all) {{
                const t = (el.innerText || el.textContent || el.placeholder || '').trim();
                if (t.includes(kw)) {{
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {{
                        {'el.click();' if not use_mouse else ''}
                        return {{
                            found: true,
                            text: t.substring(0, 50),
                            x: Math.round(r.left + r.width/2),
                            y: Math.round(r.top + r.height/2),
                            tag: el.tagName,
                        }};
                    }}
                }}
            }}
            return {{found: false}};
        }})()
        """
        val = self.eval_in_frame(frame_id, script)
        if not val or not val.get("found"):
            print(f"Element '{text}' not found in iframe")
            return False

        cx, cy = val["x"], val["y"]
        print(f"Found in iframe: '{val['text']}' ({val['tag']}) at ({cx}, {cy})")

        if use_mouse:
            # Calculate iframe offset in parent page
            frame = self.resolve_frame(frame_id)
            # Note: frame_id here is the CDP frame id; we need to find the iframe element by name/url
            offset_expr = f"""
            (function() {{
                const iframes = document.querySelectorAll('iframe');
                for (const f of iframes) {{
                    if (f.name.includes('{frame.get("name", "")}') ||
                        f.src.includes('{frame.get("url", "")[:30]}')) {{
                        const r = f.getBoundingClientRect();
                        return {{ox: r.left, oy: r.top}};
                    }}
                }}
                return {{ox: 0, oy: 0}};
            }})()
            """
            off = self.conn.eval_js(offset_expr) or {"ox": 0, "oy": 0}
            actual_x = cx + off.get("ox", 0)
            actual_y = cy + off.get("oy", 0)

            url = self.conn.url
            if not url:
                raise RuntimeError("No CDP connection")
            ws = websocket.create_connection(url, timeout=10)
            try:
                for ev in ("mousePressed", "mouseReleased"):
                    ws.send(json.dumps({
                        "id": 1,
                        "method": "Input.dispatchMouseEvent",
                        "params": {
                            "type": ev,
                            "x": actual_x,
                            "y": actual_y,
                            "button": "left",
                            "clickCount": 1,
                        },
                    }))
                    ws.recv()
            finally:
                ws.close()
            print(f"Mouse-clicked at ({actual_x}, {actual_y})")
        else:
            print("JS-click executed")
        return True

    def type_in_frame(self, frame_id: str, text: str) -> bool:
        focus_script = """
        (function() {
            const input = document.querySelector('input[type="text"], input[type="email"], input:not([type])');
            if (input) {
                input.focus();
                input.click();
                return {focused: true, placeholder: input.placeholder || ''};
            }
            return {focused: false};
        })()
        """
        val = self.eval_in_frame(frame_id, focus_script)
        if not val or not val.get("focused"):
            print("No focusable input found in iframe")
            return False

        print(f"Focused input: {val.get('placeholder', 'unnamed')}")
        url = self.conn.url
        if not url:
            raise RuntimeError("No CDP connection")
        ws = websocket.create_connection(url, timeout=10)
        try:
            for ch in text:
                ws.send(json.dumps({
                    "id": 1,
                    "method": "Input.dispatchKeyEvent",
                    "params": {"type": "char", "text": ch},
                }))
                ws.recv()
                time.sleep(0.01)
        finally:
            ws.close()
        print(f"Typed: {text}")
        return True


def print_tree(conn: CdpConn) -> None:
    ctl = FrameCtl(conn)
    frames = ctl.walk()
    print("\nFrame Tree:")
    print("-" * 60)
    for fr in frames:
        indent = "  " * fr["depth"]
        name = fr["name"] or "unnamed"
        url = fr["url"][:50] + "..." if len(fr["url"]) > 50 else fr["url"]
        parent = f" (parent: {fr['parentId'][:20]}...)" if fr.get("parentId") else " (main)"
        print(f"{indent}Frame: {name}")
        print(f"{indent}  URL: {url}")
        print(f"{indent}  ID:  {fr['id'][:30]}...{parent}")
    print(f"\nTotal: {len(frames)} frame(s)\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="iframe interaction via CDP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python interact_frame.py --list-frames
  python interact_frame.py --iframe "login" --find-elements
  python interact_frame.py --iframe "x-URS" --click-text "登录"
  python interact_frame.py --iframe "x-URS" --type "user@example.com"
        """,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT, help="CDP port")
    parser.add_argument("--list-frames", action="store_true", help="List all frames")
    parser.add_argument("--iframe", help="iframe selector (URL or name substring)")
    parser.add_argument("--find-elements", action="store_true", help="List elements inside iframe")
    parser.add_argument("--click-text", help="Click element by text inside iframe")
    parser.add_argument("--type", dest="type_text", help="Type text into iframe input")
    parser.add_argument("--use-mouse", action="store_true", help="Use real mouse instead of JS click")
    args = parser.parse_args()

    conn = CdpConn(args.port)
    if not conn.url:
        print("Error: cannot connect to browser CDP.", file=sys.stderr)
        return 1

    if args.list_frames:
        print_tree(conn)

    if args.iframe:
        ctl = FrameCtl(conn)
        frame = ctl.resolve_frame(args.iframe)
        if not frame:
            print(f"No iframe matched: {args.iframe}")
            return 1

        if args.find_elements:
            print(f"\nScanning iframe '{args.iframe}':")
            elems = ctl.elements_in_frame(frame["id"])
            print(f"Found {len(elems)} element(s):")
            for i, el in enumerate(elems[:15]):
                tag = el.get("tag", "unknown")
                txt = el.get("text") or el.get("placeholder") or el.get("name") or ""
                role = el.get("role", "")
                cx, cy = el.get("cx", 0), el.get("cy", 0)
                print(f"  [{i+1}] [{tag}] '{txt[:30]}' role={role} ({cx}, {cy})")

        if args.click_text:
            ctl.click_text_in_frame(frame["id"], args.click_text, use_mouse=args.use_mouse)

        if args.type_text:
            ctl.type_in_frame(frame["id"], args.type_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
