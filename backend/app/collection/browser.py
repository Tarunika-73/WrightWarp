"""Lightweight browser abstraction for future Playwright-based adapters.

Establishes the shape (launch / context / page / close) without any
stealth, fingerprint-evasion, or CAPTCHA-handling logic - none of that
will ever be added here (see README "Ethical scraping principles").
Playwright is imported lazily inside methods so that importing this
module - or the rest of the collection package - never requires browser
binaries to be installed, and nothing here launches a browser at import
time or at FastAPI startup.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool = True
    timeout_ms: int = 30_000
    user_agent: str = "WrightWarpBot/0.1 (+https://github.com/; research use, see robots.txt)"


class BrowserManager:
    """Owns a single Playwright browser process."""

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser = None

    async def launch(self):
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.config.headless)
        return self._browser

    async def new_context(self):
        if self._browser is None:
            raise RuntimeError("BrowserManager.launch() must be called before new_context()")
        return await self._browser.new_context(user_agent=self.config.user_agent)

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


class SessionManager:
    """Owns one browser context (cookies/storage scoped to one logical session)."""

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._browser_manager = browser_manager
        self._context = None

    async def open(self):
        self._context = await self._browser_manager.new_context()
        self._context.set_default_timeout(self._browser_manager.config.timeout_ms)
        return self._context

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None


class PageManager:
    """Owns one page within a session."""

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager
        self._page = None

    async def open(self):
        if self._session_manager._context is None:
            raise RuntimeError("SessionManager.open() must be called before PageManager.open()")
        self._page = await self._session_manager._context.new_page()
        return self._page

    async def close(self) -> None:
        if self._page is not None:
            await self._page.close()
            self._page = None
