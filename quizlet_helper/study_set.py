import time
from abc import abstractmethod
from typing import NamedTuple, List, Set
from urllib.parse import urlencode

from playwright.sync_api import Page

from quizlet_helper._common import clean, cached_property, scroll
from quizlet_helper.error import SpiderError, log
from quizlet_helper.folder import Folder, IDFolder, RootFolder
from quizlet_helper.lang import LANG_CODE_TO_NAME, Lang, POSSIBLE_LANG
from quizlet_helper.user import User


class Card(NamedTuple):
    word: str
    definition: str


class StudySet:
    """
    Abstract class of all study sets.
    """

    WORD_DEF_SEP = "<WD_SEP>"
    CARD_SEP = "<CARD_SEP>"

    def __new__(cls, *args, **kwargs):
        if "id" in kwargs or "url" in kwargs:
            return super().__new__(IDStudySet)
        return super().__new__(NamedStudySet)

    def __init__(self, user: User, **kwargs):
        self.user = user
        if not all(k in {"name", "folders", "cards", "word_lang", "definition_lang", "url", "id"} for k in kwargs):
            raise ValueError("Invalid keyword arguments")
        folders = kwargs.get("folders", [RootFolder])
        if not isinstance(folders, list):
            folders = [folders]
        if not folders:
            folders = [RootFolder]
        assert len(set(f.user for f in folders)) == 1, "Folders must be from same user"
        kwargs["folders"] = set(folders)

        if not isinstance(kwargs.get("cards", []), List):
            try:
                kwargs["cards"] = [
                    Card(*card.split(StudySet.WORD_DEF_SEP))
                    for card in kwargs["cards"].split(StudySet.CARD_SEP)
                ]
            except ValueError:
                raise ValueError(f"Illegal argument: '{self.cards}' for content.")

        if (wl := kwargs["word_lang"]) not in POSSIBLE_LANG:
            raise ValueError(f"Illegal argument: '{wl}' for key_lang.")
        if (dl := kwargs["definition_lang"]) not in POSSIBLE_LANG:
            raise ValueError(f"Illegal argument: '{dl}' for val_lang.")
        self.__dict__.update(kwargs)

    @cached_property
    def page(self) -> Page:
        """
        Page object of the study set, where all the related
        activities are happened
        """
        return self.user.ctx.new_page()

    @property
    @abstractmethod
    def folders(self) -> Set[Folder]:
        """
        The folder that the study set belongs to, if any.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The name of the study set.
        """

    @property
    @abstractmethod
    def word_lang(self) -> Lang:
        """
        The language of the words in the study set.
        """

    @property
    @abstractmethod
    def definition_lang(self) -> Lang:
        """
        The language of the definitions in the study set.
        """

    @property
    @abstractmethod
    def cards(self) -> List[Card]:
        """
        The cards in the study set.
        """

    @cached_property
    def id(self) -> str:
        """
        The id of the study set.
        """
        return self.page.evaluate("dataLayer[0].studyableId")

    @cached_property
    def url(self) -> str:
        """
        The url of the study set.
        """
        p = self.page
        p.goto(f"https://quizlet.com/{self.id}")
        return p.url

    def create(self) -> None:
        """
        Create the study set. Idempotent is not guaranteed.
        """
        log.debug(f"Creating {self}")
        p = self.page
        p.goto(
            f"https://quizlet.com/create-set" + ("" if
                                                 isinstance(folder := next(iter(self.folders)), RootFolder)
                                                 else f"?inFolder={folder.id}")
        )
        clean(p)
        p.locator('[aria-label="标题"]').fill(self.name)
        clean(p)
        p.locator("text=文件导入").click()
        p.locator(".ImportTerms-textarea").fill(
            StudySet.CARD_SEP.join(
                f"{card.word}{StudySet.WORD_DEF_SEP}{card.definition}"
                for card in self.cards
            )
        )
        loc = p.locator('[placeholder="\\-"]')
        loc.click()
        loc.fill(StudySet.WORD_DEF_SEP)
        loc = p.locator('[placeholder="\\\\n\\\\n"]')
        loc.click()
        loc.fill(StudySet.CARD_SEP)
        time.sleep(0.2)
        p.locator('[aria-label="导入"]').click()

        p.locator(".RichTextEditor p").first.click()

        def lang(n, content):
            log.debug(f"Setting {n} language to {content}")
            p.locator("button.UILink").nth(n).click()
            p.locator('[placeholder="搜索语言"]:visible').fill(content)
            p.locator('[role="option"]:visible').first.click()
            time.sleep(0.2)

        lang(0, self.word_lang)
        lang(1, self.definition_lang)

        p.locator('div[class*="heading"] [aria-label="创建"]').click()
        # jump to the study set page
        p.wait_for_load_state("networkidle")
        clean(p)

    def delete(self) -> None:
        """
        Delete the study set. Idempotent is not guaranteed.
        """
        p = self.page
        p.goto(self.url)
        p.locator(
            "button", has=p.locator('[aria-label="more menu - horizontal"]')
        ).click()
        p.locator("text='删除'").click()
        p.locator("text='是的'").click()
        clean(p)

    def __iter__(self):
        return iter(self.cards)

    def __getitem__(self, index):
        return self.cards[index]

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def query(self, query_str) -> List["StudySet"]:
        """
        Query study sets by the query string.
        """
        try:
            return self._query_get(query_str)
        except Exception as e:
            log.warn(f"Query failed, retrying with JS. {e}")
            return self._query_js(query_str)

    def _query_js(self, query_str) -> List["StudySet"]:
        p = self.page
        p.goto(f"https://quizlet.com/{self.user.name}/sets")
        p.locator('[placeholder="搜索你的学习集"]').fill(query_str)
        scroll(p)
        loc = p.locator(".DashboardListItem a:has([class*=Title])")
        return [
            IDStudySet(self.user, url=loc.nth(i).get_attribute("href"))
            for i in range(loc.count())
        ]

    def _query_get(self, query_str) -> List["StudySet"]:
        seen_session_ids = []
        seen_created_set_ids = []
        sets = []

        params = {
            "perPage": 25,
            "query": query_str,
            "seenClassSetIds": None,
            "seenSessionIds": None,
            "seenCreatedSetIds": None,
            "filters[itemType]": 1,
            "filters[sessions][isVisible]": True,
            "filters[sessions][itemType]": 1,
            "filters[sessions][repeatSets]": True,
            "filters[sets][isPublished]": True,
            "include[classSet][0]": "class",
            "include[classSet][1]": "set",
            "include[classSet][set]": "creator",
            "include[session][0]": "folder",
            "include[session][1]": "set",
            "include[session][folder]": "user",
            "include[session][set]": "creator",
            "include[set][]": "creator",
            "include[userContentPurchase][0]": "set",
            "include[userContentPurchase][1]": "folder",
            "include[userContentPurchase][set]": "creator",
            "include[userContentPurchase][folder]": "person",
        }

        p: Page = self.page

        while True:
            try:
                rp = p.goto(
                    f"https://quizlet.com/webapi/3.2/feed/{self.user.id}"
                    + "?"
                    + urlencode(
                        [
                            (k, str(v).lower() if isinstance(v, bool) else v)
                            for k, v in params.items()
                        ]
                    )
                )
                assert rp.ok
                rs = rp.json()["responses"]
                assert len(rs) == 1
                rs = rs[0]
                models = rs["models"]
                seen_session_ids += [session["id"] for session in models["session"]]
                seen_created_set_ids += [study_set["id"] for study_set in models["set"]]
                if rs["paging"]["isFeedFinished"]:
                    break
                params["seenSessionIds"] = ",".join(seen_session_ids)
                params["seenCreatedSetIds"] = ",".join(seen_created_set_ids)
                sets.extend(
                    [
                        StudySet(
                            self.user, id=study_set["id"], title=study_set["title"]
                        )
                        for study_set in models["set"]
                    ]
                )
            except (KeyError, AssertionError):
                raise SpiderError("Failed to get response from Quizlet.")
        return sets

    def __repr__(self):
        return f"Set<{self.name}, {self.url}, {self.user}>"

    def __str__(self):
        return self.name


class NamedStudySet(StudySet):
    """
    This set is intended to be created by the user.
    """

    @property
    def name(self) -> str:
        return self.__dict__["name"]

    @property
    def word_lang(self) -> Lang:
        return self.__dict__["word_lang"]

    @property
    def definition_lang(self) -> Lang:
        return self.__dict__["definition_lang"]

    @property
    def cards(self) -> List[Card]:
        return self.__dict__["cards"]

    @property
    def folders(self) -> Set[Folder]:
        return self.__dict__["folders"]

    def __init__(self, user, **kwargs):
        super().__init__(user, **kwargs)
        if not all(
                attr in kwargs for attr in ("name", "word_lang", "definition_lang", "cards")
        ):
            raise ValueError("name, word_lang, definition_lang, cards are required.")


class IDStudySet(StudySet):
    def __init__(self, user, **kwargs):
        super().__init__(user, **kwargs)
        if not hasattr(self, "id") and not hasattr(self, "url"):
            raise ValueError("id or url is required.")

    def _ensure(self):
        p = self.page
        if not p.url == self.url:
            p.goto(self.url)
        return p

    @cached_property
    def definition_lang(self):
        p = self._ensure()
        try:
            return LANG_CODE_TO_NAME[p.evaluate("Quizlet.setPageData.set.defLang")]
        except KeyError:
            raise NotImplementedError("Language not supported.")

    @cached_property
    def word_lang(self):
        p = self._ensure()
        try:
            return LANG_CODE_TO_NAME[p.evaluate("Quizlet.setPageData.set.wordLang")]
        except KeyError:
            raise NotImplementedError("Language not supported.")

    @cached_property
    def folders(self):
        p = self._ensure()
        folders = p.locator("text=添加至 >> css=a")
        return set(
            [
                IDFolder(
                    self.user,
                    url="https://quizlet.com" + folders.nth(i).get_attribute("href"),
                )
                for i in range(folders.count())
            ]
        )

    @cached_property
    def name(self):
        p = self._ensure()
        return p.evaluate('dataLayer[0]["studyableTitle"]')

    @cached_property
    def cards(self):
        p = self._ensure()
        p.goto(self.url)
        p.wait_for_load_state("domcontentloaded")
        return [
            Card(w, d)
            for w, d in zip(
                *(
                    (e.text_content() for e in p.query_selector_all(sel))
                    for sel in [".setPageTerm-wordText", ".setPageTerm-definitionText"]
                ),
                strict=True,
            )
        ]
