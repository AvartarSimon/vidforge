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
import time
from pathlib import Path

PROFILE_DIR = Path.home() / ".vidforge" / "browser-profile"
_lock = threading.Lock()
LAST_LOGIN_STATUS: dict[str, bool] = {}   # site id -> logged in, from the last `login_session()` run


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


def login_session(sites: list[str] | None = None) -> dict[str, bool]:
    """Open the profile window with one tab per site; returns when the user closes the window.

    While the window is open, each tab is polled for its chat input box (the same selectors
    `chat.ask()` looks for) so we know, per site, whether the login actually went through —
    without this the only feedback was a confusing "input box not found" the next time someone
    tried to generate something. Result is also kept in LAST_LOGIN_STATUS for the UI to read.
    """
    from .chat import GENERIC_INPUT, SITES
    sync_playwright = _playwright()
    names = [n for n in (sites or list(SITES)) if n in SITES]
    status = {n: False for n in names}
    with _lock, sync_playwright() as pw:
        ctx, page = launch(pw, headless=False)
        pages: dict[str, object] = {}
        first = True
        for name in names:
            p = page if first else ctx.new_page()
            first = False
            pages[name] = p
            try:
                p.goto(SITES[name]["url"], wait_until="domcontentloaded", timeout=60000)
            except Exception:  # noqa: BLE001
                pass
        try:
            next(iter(pages.values())).bring_to_front()   # surface the window — a background
        except Exception:                                  # thread's popup can otherwise open
            pass                                            # behind everything else unnoticed
        print(f"[vidforge] 请在打开的窗口里逐个登录各站点；全部登录后关闭窗口即可（登录状态会保存在 {PROFILE_DIR}）。")
        t0 = time.time()
        try:
            while ctx.pages and time.time() - t0 < 3600:
                for name, p in pages.items():
                    if status[name]:
                        continue
                    try:
                        if p.is_closed():
                            continue
                        for sel in SITES[name]["input"] + GENERIC_INPUT:
                            if p.locator(sel).last.is_visible(timeout=300):
                                status[name] = True
                                break
                    except Exception:  # noqa: BLE001
                        continue
                time.sleep(2)
        except Exception:  # noqa: BLE001
            pass   # the context/window was closed out from under the loop — that's the exit signal
    LAST_LOGIN_STATUS.update(status)
    return status
