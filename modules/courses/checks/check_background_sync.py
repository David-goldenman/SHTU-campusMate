"""All source requests are dispatched before waiting for individual responses."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox


async def check():
    package = load('courses')
    with sandbox('courses') as context:
        started, dispatched = set(), asyncio.Event()

        async def api(module, path, **options):
            assert path == '/sync' and options['method'] == 'POST'
            started.add(module)
            if started == set(package.SOURCES):
                dispatched.set()
            await asyncio.Event().wait()

        context.api = api
        router = package.create_router(context)
        sync = next(route.endpoint for route in router.routes if route.path == '/sync')
        task = asyncio.create_task(sync())
        try:
            await asyncio.wait_for(dispatched.wait(), 2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert started == set(package.SOURCES)


if __name__ == '__main__':
    asyncio.run(check())
    print('courses: all connected sources dispatched before a page request is cancelled')
