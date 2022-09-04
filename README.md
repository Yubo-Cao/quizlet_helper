# Quizlet Helper

## What is this?

Use `playwright` to automate the process of creating a quizlet set from a list of words. In addition,
this provides helpful object-oriented wrappers around it, so one may use it as an CLI tool, as well
as a library. In addition, extensive use of properties makes it taste very sweet; ost of the attributes
are initialized lazily, so speed is not that much of an issue. However, it does not use `asyncio`,
so it is inevitably slower than it could be.

An example looks like this

```python
from yaml import load, Loader
from playwright.sync_api import sync_playwright
from quizlet_helper.folder import Folder
from quizlet_helper.study_set import StudySet, Card
from quizlet_helper.user import User

with open("auth.yml", "r") as f:
    config = load(f, Loader=Loader)
    password, username = config["password"], config["username"]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    user = User(username, password, browser)
    folder = Folder(user, name="Barron")
    folder.created = True
    set = StudySet(
        user,
        name="Barron 1",
        cards=[
            Card("abandon", "放弃"),
            Card("ability", "能力"),
        ],
        definition_lang="中文（简体）",
        word_lang="英语",
    )
    set.create()
```

## Bugs

- It is yet to be understood how Quizlet use their weird parameters for Ajax requests. For now, it
  almost always fall back to use scroll window and dom manipulation to create a set. This is slow, and
  I hope to improve it in the future.
- I plan to port this to async, especially considering `playwright` is mainly async. However, this would
  introduce a lot of effort for error handling, and I am not sure if it is worth it.
- Most importantly, for the sake of robustness of API, it uses a lot of `aria-label` and `text=` selector.
  Since I am a Chinese, all the labels here are described based on one with locale setting of `zh-CN`. Hence,
  it is necessary for you to switch your locale to `zh-CN` if you want to use this. Maybe later, I will reimplement this
  in locale setting of `en-US`, or even introduction some globalization techniques to make it more robust.

## Warning
This project is not affiliate, endorsed, or supported by Quizlet. It is a personal project and,
therefore, does not provide warranty or support. Use at your own risk.

