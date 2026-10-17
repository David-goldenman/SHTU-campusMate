from backend.services.campus import Source
from .reader import fetch

_source = None


def create_router(context):
    global _source
    _source = Source(context, "ids", ["ecourse.shanghaitech.edu.cn"], fetch,
                     target="ecourse", network_target="ecourse")
    return _source.router()


def stop(context):
    if _source is not None:
        _source.close()
