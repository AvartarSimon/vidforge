"""Drive the user's own logged-in browser like a person would.

Why: the user has web subscriptions (ChatGPT Plus, Claude Pro, Gemini, DeepSeek, Grok, Qwen,
Kimi, 文心一言) but no API keys. We open a *dedicated* Edge/Chrome profile
(~/.vidforge/browser-profile) in a visible window, the user logs in once, and from then on
vidforge types prompts and reads answers there.

Rules that keep this tolerable for the services and safe for the account:
  * one request at a time (module lock), visible window, human-paced typing and waits;
  * never runs in the background without the user asking (a button click or a CLI call);
  * if a site shows a captcha / login wall we stop and tell the user to handle it in the window.
  * ToS: consumer chat products forbid automation; this is the user's own account, own risk,
    and the "copy the prompt, paste the answer" path always remains available.

Requires `pip install playwright` (no browser download: uses the installed Edge or Chrome).
"""

from __future__ import annotations

import threading
from pathlib import Path

PROFILE_DIR = Path.home() / ".vidforge" / "browser-profile"
_lock = threading.Lock()


class BrowserError(RuntimeError):
    pass


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise BrowserError("浏览器自动化需要 playwright：pip install playwright（不用下载浏览器，直接用本机 Edge/Chrome）") from None
    return sync_playwright


def launch(pw, headless: bool = False, channel_order=("msedge", "chrome")):
    """Persistent context on the dedicated profile; returns (context, page)."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    last = None
    for channel in channel_order:
        try:
            ctx = pw.chromium.launch_persistent_context(
                str(PROFILE_DIR), channel=channel, headless=headless, viewport=None,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
                ignore_default_args=["--enable-automation"],
                locale="zh-CN",
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            return ctx, page
        except Exception as e:  # noqa: BLE001
            last = e
    raise BrowserError(f"无法启动 Edge/Chrome：{last}")


def login_session(sites: list[str] | None = None) -> None:
    """Open the profile window with one tab per site; returns when the user closes the window."""
    from .chat import SITES
    sync_playwright = _playwright()
    names = sites or list(SITES)
    with _lock, sync_playwright() as pw:
        ctx, page = launch(pw, headless=False)
        first = True
        for name in names:
            site = SITES.get(name)
            if not site:
                continue
            p = page if first else ctx.new_page()
            first = False
            try:
                p.goto(site["url"], wait_until="domcontentloaded", timeout=60000)
            except Exception:  # noqa: BLE001
                pass
        print("[vidforge] 请在打开的窗口里逐个登录各站点；全部登录后关闭窗口即可（登录状态会保存在 "
              f"{PROFILE_DIR}）。")
        try:
            ctx.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001
            pass
