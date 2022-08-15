from playwright.sync_api import sync_playwright
from yaml import Loader, load

from quizlet_helper.folder import Folder
from quizlet_helper.study_set import StudySet, Card
from quizlet_helper.user import User


def main():
    with open("auth.yml", "r") as f:
        config = load(f, Loader=Loader)
        password, username = config["password"], config["username"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        user = User(username, password, browser)
        folder = Folder(user, name="Barron")
        folder.created = True
        sset = StudySet(
            user,
            name="Barron 1",
            cards=[
                Card("abandon", "放弃"),
                Card("ability", "能力"),
                Card("able", "能够"),
                Card("abnormal", "异常"),
                Card("abolish", "废除"),
                Card("actor", "演员"),
                Card("actress", "女演员"),
            ],
            definition_lang="中文（简体）",
            word_lang="英语",
        )
        sset.create()


if __name__ == '__main__':
    main()
