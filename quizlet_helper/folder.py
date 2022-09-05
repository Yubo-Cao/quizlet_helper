import time
from abc import abstractmethod
from typing import List
from urllib.parse import urlencode

from playwright.sync_api import Locator

from quizlet_helper._common import cached_property, scroll
from quizlet_helper.error import SpiderError, log
from quizlet_helper.user import User


class Folder:
    """
    Abstract class of all folders.
    """

    def __new__(cls, *args, **kwargs):
        if "id" in kwargs or "url" in kwargs:
            return super().__new__(IDFolder)
        elif "name" in kwargs:
            return super().__new__(NamedFolder)
        else:
            raise ValueError("You must specify either id or name")

    def __init__(self, user: User, **kwargs):
        self.user = user
        assert all(
            k in {"id", "url", "name"} for k in kwargs.keys()
        ), "Invalid keyword arguments"
        self.__dict__.update(kwargs)

    @cached_property
    def page(self):
        """
        The page where all folder related actions are performed.
        """
        return self.user.ctx.new_page()

    def create(self):
        """
        Create the folder. Idempotent is not guaranteed.
        """
        log.debug(f"Creating folder {self.name}")
        p = self.page
        p.goto(f"https://quizlet.com/{self.user.name}/folders")
        p.locator('[aria-label="创建"]').click()
        p.locator('button[role="menuitem"]:has-text("文件夹")').click()
        p.locator('[placeholder="输入标题"]').fill(self.name)
        p.locator('[aria-label="创建文件夹"]').click()

    def delete(self):
        """
        Delete the folder. Idempotent is not guaranteed.
        """
        log.debug(f"Deleting folder {self.name}")
        p = self.page
        p.goto(self.url)
        p.locator(
            "button", has=p.locator('[aria-label="more menu - horizontal"]')
        ).hover()
        p.locator("text=删除").click()
        p.locator("button", has=p.locator("text=删除文件夹")).click()

    @property
    @abstractmethod
    def created(self) -> bool:
        """
        Return True if the folder has been created.
        """

    @created.setter
    def created(self, value):
        c = self.created
        if value and not c:
            self.create()
            time.sleep(0.2)
        elif not value and c:
            self.delete()
            time.sleep(0.2)

    @property
    @abstractmethod
    def url(self) -> str:
        """
        Return the URL of the folder.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the name of the folder.
        """

    @property
    @abstractmethod
    def id(self) -> str:
        """
        Return the id of the folder.
        """

    def query(self, name: str = "") -> List["Folder"]:
        """
        Obtain all folder of the user. Optionally filter by name (contains).
        TODO: Cache the result.
        """
        try:
            log.debug("Querying folders using GET")
            return self._query_get(name)
        except Exception:
            log.debug("Querying folders using GET failed. Falling back to JS.")
            return self._query_js(name)

    def _query_js(self, query_str) -> List["Folder"]:
        p = self.page
        p.goto(f"https://quizlet.com/{self.user.name}/folders")
        search: Locator = p.locator('[placeholder="搜索你的文件夹"]')
        if search.is_visible():
            search.fill(query_str)
        scroll(p)
        time.sleep(0.5)
        loc = p.locator(".DashboardListItem header")
        log.debug(f"Found {loc.count()} folders")
        return [IDFolder(self.user, url=url)
                for url in p.evaluate(
                f"""Array.from(document.querySelectorAll(".DashboardListItem"))
    .filter((e) =>e.querySelector(`[class*='Title']`).textContent.includes(`{query_str}`))
    .map((e) => "https://quizlet.com" + e.querySelector("a").getAttribute("href"));""")]

    def _query_get(self, query_str):
        p = self.page
        params = {
            "filters[isDeleted]": False,
            "filters[isHidden]": False,
            "filters[personId]": self.user.id,
            "include[folder][]": "user",
            "page": 1,
        }
        results = []
        seen_folders = []
        total = 0
        while True:
            url = "https://quizlet.com/webapi/3.2/folders" + "?" + urlencode(
                [(k, str(v).lower() if isinstance(v, bool) else v) for k, v in params.items()])
            log.debug(f"Querying {url}")
            rs = p.goto(url)
            assert rs.ok, f"Failed to query folders: {rs.status} {rs.status_text}"
            rs = rs.json()["responses"]
            assert len(rs) == 1, f"Unexpected response: {rs!r}"
            rs = rs[0]
            models, paging = rs.values()
            results += [
                IDFolder(self.user, id=folder["id"], url=folder["_webUrl"], name=folder["name"])
                for folder in models["folder"]
            ]
            seen_folders += [folder["id"] for folder in models["folder"]]
            total += paging["total"]
            if total <= paging["perPage"] * paging["page"]:  # 200 per page
                break
            params[
                "page"
            ] += 1  # TODO: Not tested. I don't have an account that have 200+ folders.
        return [f for f in results if query_str in f.name]

    def __repr__(self):
        return f"<Folder {self.name}>"

    def __str__(self):
        return self.name


class NamedFolder(Folder):

    @property
    def name(self) -> str:
        return self.__dict__["name"]

    @cached_property
    def page(self):
        return self.user.ctx.new_page()

    @property
    def created(self):
        return any(f.name == self.name for f in self.query(self.name))

    @created.setter
    def created(self, value):
        c = self.created
        if value and not c:
            self.create()
        elif not value and c:
            self.delete()

    @cached_property
    def id(self):
        p = self.page
        p.goto(self.url)
        return p.evaluate("dataLayer[0].studyableId")

    @cached_property
    def url(self):
        p = self.page
        if self.created:
            results = self.query(self.name)
            if len(results) > 1:
                log.warning(f"More than one folder with name '{self.name}' found. Using the first one.")
            elif len(results) == 0:
                raise SpiderError(f"No folder with name '{self.name}' found.")
            return results[0].url
        else:
            raise SpiderError(f"Folder {self.name} does not exist.")
        return p.url

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)


class IDFolder(Folder):
    """
    Represents a folder constructed by ID or URL
    """

    def __init__(self, user: User, **kwargs):
        super().__init__(user, **kwargs)
        assert self.__dict__.get("id") or self.__dict__.get("url"), "Either id or url must be provided."
        if self.__dict__.get("id"):
            self.id = self.__dict__["id"]
        if self.__dict__.get("url"):
            self.url = self.__dict__["url"]
        if self.__dict__.get("name"):
            self.name = self.__dict__["name"]

    @cached_property
    def url(self):
        return f"https://quizlet.com/{self.user.name}/folders/{self.id}/sets"

    @cached_property
    def page(self):
        return self.user.ctx.new_page()

    def _ensure_url(self):
        if self.page.url != self.url:
            self.page.goto(self.url)

    @cached_property
    def id(self):
        self._ensure_url()
        return self.page.evaluate("dataLayer[0].studyableId")

    @cached_property
    def name(self):
        self._ensure_url()
        return self.page.locator(".DashboardHeaderTitle-title").text_content()

    @property
    def created(self):
        return bool([f.id == self.id for f in self.query(self.name)])

    @created.setter
    def created(self, value):
        c = self.created
        if value and not c:
            self.create()
        elif not value and c:
            self.delete()

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)


class RootFolder(Folder):
    def __new__(cls, user: User, **kwargs):
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance

    def create(self):
        raise SpiderError("Root folder cannot be created.")

    def delete(self):
        raise SpiderError("Root folder cannot be deleted.")

    @property
    def created(self):
        return True

    @created.setter
    def created(self, value):
        if not value:
            raise SpiderError("Root folder cannot be deleted.")

    @property
    def url(self):
        raise SpiderError("Root folder does not have a url.")

    @property
    def name(self) -> str:
        return "root"

    @property
    def id(self) -> str:
        return ""

    @property
    def user(self):
        return self.user

    def __hash__(self):
        return hash(id(self))

    def __eq__(self, other):
        return self is other
