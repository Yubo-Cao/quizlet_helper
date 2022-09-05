import time
from pathlib import Path

from playwright.sync_api import Browser

from quizlet_helper._common import cached_property


class User:
    def __init__(
        self,
        username: str,
        password: str,
        browser: Browser,
        auth_filename: str | Path = Path("auth.json"),
    ):
        self.name = username
        self.passwd = password
        self.auth_filename = Path(auth_filename)
        self.browser = browser

    @cached_property
    def page(self):
        return self.ctx.new_page()

    def _ensure(self):
        if not self.page.url == "https://quizlet.com/latest":
            self.page.goto("https://quizlet.com/latest")
            time.sleep(0.2)

    @cached_property
    def id(self) -> str:
        self._ensure()
        return self.page.evaluate("Quizlet.user.id")

    @property
    def logged_in(self):
        self._ensure()
        return self.page.evaluate("Quizlet.LOGGED_IN")

    @cached_property
    def ctx(self):
        if self.auth_filename.exists():
            ctx = self.browser.new_context(storage_state=self.auth_filename)
            p = ctx.new_page()
            p.goto("https://quizlet.com/latest")
            if p.evaluate("Quizlet.LOGGED_IN"):
                p.close()
                return ctx
            print("Auth file is invalid, logging in...")
        else:
            ctx = self.browser.new_context()
            p = ctx.new_page()
        p.goto("https://quizlet.com/zh-cn")
        p.locator("text=登录").click()
        p.locator("input[name='username']").fill(self.name)
        p.locator("input[name='password']").fill(self.passwd)
        p.locator('[data-testid="login-form"] [aria-label="登录"]').click()
        p.wait_for_url("https://quizlet.com/latest")
        ctx.storage_state(path=self.auth_filename)
        p.close()
        return ctx

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"<User {self.name}>"

    def __str__(self):
        return self.name
