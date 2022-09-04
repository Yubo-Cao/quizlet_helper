from abc import abstractmethod
from typing import List
from urllib.parse import urlencode

from playwright.sync_api import Locator

from quizlet_helper.common import cached_property, scroll, headers
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
            raise ValueError("Invalid arguments.")

    def __init__(self, user: User, **kwargs):
        self.user = user
        assert all(
            k in {"id", "url", "name"} for k in kwargs.keys()
        ), "Invalid keyword arguments"
        self.__dict__.update(kwargs)

    @property
    def page(self):
        """
        The page where all folder related actions are performed.
        """
        return self.user.ctx.new_page()

    def create(self):
        """
        Create the folder. Idempotent is not guaranteed.
        """
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
        elif not value and c:
            self.delete()

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
            return self._query_get(name)
        except Exception:
            log.warning("Querying folders using GET failed. Falling back to JS.")
            return self._query_js(name)

    def _query_js(self, name) -> List["Folder"]:
        p = self.page
        p.goto(f"https://quizlet.com/{self.user.name}/folders")
        search: Locator = p.locator('[placeholder="搜索你的文件夹"]')
        if search.is_visible():
            search.fill(name)
            p.wait_for_load_state("networkidle")
        scroll(p)
        return [
            NamedFolder(self.user, name=name)
            for name in p.locator(".DashboardListItem header").all_text_contents()
        ]

    def _query_get(self, name):
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
            r = p.request
            url = "https://quizlet.com/webapi/3.2/folders" + "?" + urlencode(
                [(k, str(v).lower() if isinstance(v, bool) else v) for k, v in params.items()])
            rs = r.get(url, headers=headers)
            assert rs.ok, f"Failed to query folders: {rs!r}"
            rs = rs.json()["responses"]
            assert len(rs) == 1, f"Unexpected response: {rs!r}"
            rs = rs[0]
            models, paging = rs.values()
            results += [
                IDFolder(self.user, id=folder["id"], url=folder["_webUrl"])
                for folder in models["folder"]
            ]
            seen_folders += [folder["id"] for folder in models["folder"]]
            total += paging["total"]
            if total <= paging["perPage"] * paging["page"]:  # 200 per page
                break
            params[
                "page"
            ] += 1  # TODO: Not tested. I don't have an account that have 200+ folders.
        return [f for f in results if name in f.name]

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
            p.goto(f"https://quizlet.com/{self.user.name}/folders")
            p.locator('[placeholder="搜索你的文件夹"]').fill(self.name)
            folder = p.locator(f"text={self.name}")
            if folder.count() >= 1:
                log.warning(f"Duplicate folder name: {self.name}")
            folder.first.click()
        else:
            raise SpiderError(f"Folder {self.name} does not exist.")
        p.wait_for_load_state("networkidle")
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
        assert self.id or self.url, "Either id or url must be provided"

    @cached_property
    def url(self):
        return f"https://quizlet.com/{self.user.name}/folders/{self.id}/sets"

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
