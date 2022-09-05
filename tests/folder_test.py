from sample_user import *
from quizlet_helper import Folder

folder = Folder(user, name="Barron")
print(repr(folder))

print(folder.created)
folder.created = True
print(folder.created)
folder.created = False
print(folder.created)