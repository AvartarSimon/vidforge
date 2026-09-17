"""Ask a question in a web chat (ChatGPT, Claude, Gemini, DeepSeek, Grok, Qwen, Kimi, 文心) and
return the answer text — through the user's logged-in browser profile.

Each site entry lists candidate selectors; the first that exists is used, and a generic
fallback (last visible textarea / contenteditable, largest new text block) covers DOM changes.
Completion = no "stop generating" button visible AND the answer text unchanged for `settle` s.
"""

from __future__ import annotations

import time

from . import BrowserError, _lock, _playwright, launch

GENERIC_INPUT = ["textarea:visible", "div[contenteditable='true']:visible"]
GENERIC_STOP = ["button[aria-label*='Stop' i]", "button[aria-label*='停止']", "button[data-testid*='stop' i]"]

SITES: dict[str, dict] = {
    "chatgpt": {"label": "ChatGPT", "url": "https://chatgpt.com/",
                "input": ["#prompt-textarea", "div#prompt-textarea[contenteditable]"],
                "answer": ["[data-message-author-role='assistant']"],
                "stop": ["button[data-testid='stop-button']"]},
    "claude": {"label": "Claude", "url": "https://claude.ai/new",
               "input": ["div.ProseMirror[contenteditable='true']", "div[contenteditable='true']"],
               "answer": ["[data-testid='assistant-message']", "div.font-claude-message", "div[data-is-streaming]"],
               "stop": ["button[aria-label='Stop response']", "button[aria-label='Stop Response']"]},
    "gemini": {"label": "Gemini", "url": "https://gemini.google.com/app",
               "input": ["rich-textarea div.ql-editor", "div.ql-editor[contenteditable='true']"],
               "answer": ["message-content .markdown", "model-response", "message-content"],
               "stop": ["button[aria-label*='Stop' i]", "button.stop"]},
    "deepseek": {"label": "DeepSeek", "url": "https://chat.deepseek.com/",
                 "input": ["textarea#chat-input", "textarea"],
                 "answer": [".ds-markdown", "div.ds-message"],
                 "stop": ["div[role='button'][aria-disabled='false'] .ds-icon svg[width='28']", *GENERIC_STOP]},
    "grok": {"label": "Grok", "url": "https://grok.com/",
             "input": ["textarea", "div[contenteditable='true']"],
             "answer": ["div.message-bubble", "div[class*='message'] .prose", ".prose"],
             "stop": GENERIC_STOP},
    "qwen": {"label": "通义千问", "url": "https://chat.qwen.ai/",
             "input": ["textarea#chat-input", "textarea"],
             "answer": ["div.markdown-content-container", ".response-message-body", ".markdown"],
             "stop": GENERIC_STOP},
    "kimi": {"label": "Kimi", "url": "https://www.kimi.com/",
             "input": ["div.chat-input-editor[contenteditable]", "div[contenteditable='true']", "textarea"],
             "answer": ["div.markdown", ".segment-content"],
             "stop": GENERIC_STOP},
    "yiyan": {"label": "文心一言", "url": "https://yiyan.baidu.com/",
              "input": ["div.yc-editor[contenteditable]", "div[contenteditable='true']", "textarea"],
              "answer": ["div.markdown-body", "div[class*='answer']"],
              "stop": GENERIC_STOP},
}


def _first(page, selectors: list[str], timeout: int = 15000):
    for sel in selectors:
        try:
            loc = page.locator(sel).last
            loc.wait_for(state="visible", timeout=timeout if sel == selectors[0] else 2000)
            return loc
        except Exception:  # noqa: BLE001
            continue
    return None


def _answer_text(page, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count():
                return loc.last.inner_text().strip()
        except Exception:  # noqa: BLE001
            continue
    # generic: the largest text block that appeared in <main>
    try:
        return page.evaluate("""() => {
            const els = [...document.querySelectorAll('main div, article, section')].filter(e => e.children.length < 40);
            let best = ''; for (const e of els) { const t = e.innerText || ''; if (t.length > best.length && t.length < 20000) best = t; }
            return best.trim(); }""")
    except Exception:  # noqa: BLE001
        return ""


def _login_wall_hint(page) -> str:
    """Best-effort: is the input box missing because we're stuck on a login/verification page?"""
    try:
        text = (page.title() + " " + page.url).lower()
        body = page.evaluate("() => document.body ? document.body.innerText.slice(0, 500) : ''").lower()
        markers = ["log in", "sign in", "登录", "登陆", "verify", "验证", "captcha", "手机号", "密码", "continue with"]
        if any(m in text or m in body for m in markers):
            return "看起来还停在登录/验证页，还没登录成功——"
    except Exception:  # noqa: BLE001
        pass
    return "可能未登录或有验证页——"


def _generating(page, selectors: list[str]) -> bool:
    for sel in selectors + GENERIC_STOP:
        try:
            if page.locator(sel).first.is_visible(timeout=200):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def ask(site_name: str, prompt: str, *, timeout: float = 240, settle: float = 4.0, headless: bool = False,
        log=print) -> str:
    """Type `prompt` into the site's chat box, wait for the reply, return its text."""
    site = SITES.get(site_name)
    if not site:
        raise BrowserError(f"未知站点 {site_name}；可选：{', '.join(SITES)}")
    sync_playwright = _playwright()
    with _lock, sync_playwright() as pw:
        ctx, page = launch(pw, headless=headless)
        try:
            page.goto(site["url"], wait_until="domcontentloaded", timeout=60000)
            box = _first(page, site["input"] + GENERIC_INPUT, timeout=20000)
            if box is None:
                shot = _shot(site_name)
                page.screenshot(path=str(shot))
                hint = _login_wall_hint(page)
                raise BrowserError(f"{site['label']}：没找到输入框——{hint}请运行 `vidforge browser login` 登录后重试"
                                   f"（截图已存到 {shot}，可以看看页面停在哪一步）。")
            before = _answer_text(page, site["answer"])
            box.click()
            page.keyboard.type(prompt, delay=2)                  # human-ish pace, fast enough for a long prompt
            time.sleep(0.4)
            page.keyboard.press("Enter")
            log(f"[browser] {site['label']} 已发送，等待回答…")

            t0 = time.time()
            last, stable_since = "", None
            while time.time() - t0 < timeout:
                time.sleep(1.0)
                text = _answer_text(page, site["answer"])
                if text and text != before and len(text) > 20:
                    if text == last:
                        if stable_since is None:
                            stable_since = time.time()
                        elif time.time() - stable_since >= settle and not _generating(page, site["stop"]):
                            return text
                    else:
                        last, stable_since = text, None
            if last:
                log("[browser] 超时，返回已收到的部分")
                return last
            page.screenshot(path=str(_shot(site_name)))
            raise BrowserError(f"{site['label']}：{int(timeout)} 秒内没有收到回答（截图已存到 ~/.vidforge/）")
        finally:
            ctx.close()


def _shot(site: str):
    from . import PROFILE_DIR
    p = PROFILE_DIR.parent / f"browser-{site}-{int(time.time())}.png"
    return p
