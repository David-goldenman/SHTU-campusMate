from backend.services.campus import Source
from .reader import fetch

_source = None


def create_router(context):
    global _source
    _source = Source(context, "ids", ["eams.shanghaitech.edu.cn"], fetch, target="timetable")
    return _source.router()


def stop(context):
    if _source is not None:
        _source.close()
