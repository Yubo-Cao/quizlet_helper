from playwright.sync_api import *
from yaml import Loader, load

from quizlet_helper import User

with open('auth.yml') as auth:
    config = load(auth, Loader=Loader)
    username, password = config['username'], config['password']

p = sync_playwright().start()
browser = p.chromium.launch(headless=False)
user = User(username, password, browser)