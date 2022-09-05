from quizlet_helper import Folder, StudySet, Card
from sample_user import *

folder = Folder(user, name="Test")
folder.created = True
set = StudySet(user, name="Test", folders=folder, cards=[Card("a", "b"), Card("c", "d")], word_lang="英语",
               definition_lang="英语")
set.create()
