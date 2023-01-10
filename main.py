from quizlet_helper import User, Folder, StudySet, Card
from playwright.sync_api import sync_playwright

username, password = ("StudyHard4399", "Cao12123781")

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
