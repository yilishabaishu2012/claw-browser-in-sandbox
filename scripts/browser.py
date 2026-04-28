#!/usr/bin/env python3
"""
browser.py — Headed browser lifecycle manager.
Starts/stops a real Chrome instance backed by Xvfb, with CDP remote debugging enabled.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# Tunables via environment
CDP_PORT = int(os.getenv("CDP_PORT", "18800"))
DISPLAY_NUM = int(os.getenv("DISPLAY_NUM", "99"))
SCREEN_WIDTH = int(os.getenv("SCREEN_WIDTH", "1920"))
SCREEN_HEIGHT = int(os.getenv("SCREEN_HEIGHT", "1080"))

SCRIPT_DIR = Path(__file__).resolve().parent
GUARD_JS = SCRIPT_DIR / "protocol_guard.js"
USER_DATA_DIR = Path("/tmp/browser-sandbox-chrome-data")

# Common Chrome/Chromium locations
CHROME_CANDIDATES = [
    "/home/sandbox/chrome-linux/chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/opt/google/chrome/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def _log(msg: str) -> None:
    print(msg, flush=True)


def find_chrome() -> str:
    custom = os.getenv("CHROME_PATH")
    if custom:
        return custom

    for candidate in CHROME_CANDIDATES:
        if shutil.which(candidate):
            return candidate

    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path

    _log("Error: Chrome/Chromium not found. Please install it or set CHROME_PATH.")
    sys.exit(1)


def is_chrome_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"chrome.*remote-debugging-port={CDP_PORT}"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def is_xvfb_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"Xvfb.*:{DISPLAY_NUM}"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def ensure_xvfb() -> None:
    if is_xvfb_running():
        return
    _log(f"Starting Xvfb :{DISPLAY_NUM} ({SCREEN_WIDTH}x{SCREEN_HEIGHT})...")
    subprocess.Popen(
        [
            "Xvfb",
            f":{DISPLAY_NUM}",
            "-screen",
            "0",
            f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}x24",
            "-ac",
            "+extension",
            "RANDR",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)


def write_preferences() -> None:
    default_dir = USER_DATA_DIR / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)

    prefs = {
        "profile": {
            "default_content_setting_values": {"protocol_handler": 2},
        },
        "session": {
            "restore_on_startup": 5,
            "startup_urls": ["about:blank"],
        },
        "browser": {
            "enabled_labs_experiments": ["disable-external-intent-requests@2"],
        },
    }

    (default_dir / "Preferences").write_text(
        json.dumps(prefs, separators=(",", ":")), encoding="utf-8"
    )

    # Erase session restoration artifacts to avoid "Restore pages?" bubble
    for pattern in ("Singleton*", "Last*", "*_startup_log*"):
        for p in USER_DATA_DIR.glob(pattern):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

    sessions_dir = default_dir / "Sessions"
    if sessions_dir.exists():
        shutil.rmtree(sessions_dir, ignore_errors=True)

    for suffix in ("Current", "Last"):
        for p in default_dir.glob(f"{suffix}*"):
            p.unlink(missing_ok=True)


def build_chrome_args(url: str | None) -> list[str]:
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        f"--remote-debugging-port={CDP_PORT}",
        f"--window-size={SCREEN_WIDTH},{SCREEN_HEIGHT}",
        "--force-device-scale-factor=1",
        "--disable-blink-features=AutomationControlled",
        "--disable-popup-blocking",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={USER_DATA_DIR}",
        "--remote-allow-origins=*",
        # Keep-alive tuning
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-networking",
        "--disable-breakpad",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--safebrowsing-disable-auto-update",
        "--password-store=basic",
        "--use-mock-keychain",
        "--enable-automation",
        "--disable-session-crashed-bubble",
        "--disable-restore-session-state",
    ]

    if url:
        if GUARD_JS.exists():
            args.append(f"--inject-js={GUARD_JS}")
        args.append(url)

    return args


def start_browser(url: str | None) -> int:
    if is_chrome_running():
        _log(f"Browser already running (CDP port {CDP_PORT}).")
        return 0

    ensure_xvfb()
    write_preferences()

    chrome_path = find_chrome()
    _log(f"Using Chrome: {chrome_path}")

    env = os.environ.copy()
    env["DISPLAY"] = f":{DISPLAY_NUM}"

    cmd = [chrome_path] + build_chrome_args(url)
    _log(f"Launching Chrome (CDP port {CDP_PORT})...")
    subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(3)

    if is_chrome_running():
        _log("Browser started successfully.")
        _log(f"  CDP port: {CDP_PORT}")
        _log(f"  Display:  :{DISPLAY_NUM}")
        if url:
            _log(f"  URL:      {url}")
        return 0
    else:
        _log("Browser failed to start.")
        return 1


def stop_browser() -> int:
    _log("Stopping browser...")
    for pattern in (f"chrome.*remote-debugging-port={CDP_PORT}", f"Xvfb.*:{DISPLAY_NUM}"):
        subprocess.run(["pkill", "-f", pattern], capture_output=True)
    _log("Stopped.")
    return 0


def check_status() -> int:
    if is_chrome_running():
        _log(f"Browser is running (CDP port {CDP_PORT}).")
        return 0
    else:
        _log("Browser is not running.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Headed browser lifecycle manager",
        usage="%(prog)s {start [URL]|stop|status}",
    )
    parser.add_argument("command", choices=["start", "stop", "status"], help="Action to perform")
    parser.add_argument("url", nargs="?", help="Optional URL to open (with 'start')")
    args = parser.parse_args()

    if args.command == "start":
        return start_browser(args.url)
    elif args.command == "stop":
        return stop_browser()
    elif args.command == "status":
        return check_status()

    return 1


if __name__ == "__main__":
    sys.exit(main())
