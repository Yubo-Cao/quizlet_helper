import time

from playwright.sync_api import Page, TimeoutError

from quizlet_helper.error import log


def cached_property(fn):
    def getter(self):
        fld = f"@{fn.__name__}"
        if not hasattr(self, fld):
            setattr(self, fld, fn(self))
        return getattr(self, fld)

    def setter(self, value):
        setattr(self, f"@{fn.__name__}", value)

    return property(getter, setter)


__scroll_code = """
let ph = null;
let mid = setInterval(function () {
  let ch = innerHeight + scrollY;
  if (ph === null) ph = ch;
  else if (
    ph === ch &&
    window.getComputedStyle(
      document.querySelector('[data-testid="UILoadingIndicator"] circle')
    ).fill == "none"
  ) {
    clearInterval(mid);
    clearInterval(id);
  } else ph = ch;
}, 500);
let id = setInterval(function () {
  let e = document.scrollingElement || document.body;
  e.scrollTop = e.scrollHeight;
  console.log("scr");
}, 250);
"""


def scroll(page):
    page.evaluate(__scroll_code)


def clean(page: Page):
    try:
        close = page.locator('[aria-label="关闭窗口"] [aria-label="x"]')
        if page.locator('[role="dialog"]').is_visible() and close.is_visible():
            close.click(timeout=500)
            time.sleep(0.2)
        close = page.locator("text=知道了")
        if close.is_visible():
            close.click(timeout=500)
    except TimeoutError:
        log.warning("Failed to close dialog")


headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
}
