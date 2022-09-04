import sys
from logging import (
    Logger,
    StreamHandler,
    FileHandler,
    WARNING,
)


class SpiderError(Exception):
    """
    Base class for exceptions in this module.
    """


log = Logger("spider", level=WARNING)
log.addHandler(StreamHandler(sys.stdout))
log.addHandler(FileHandler("spider.log"))
