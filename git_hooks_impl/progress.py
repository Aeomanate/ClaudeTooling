#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Progress display for long-running Claude calls.
"""

import asyncio
import sys
import time

from git_hooks_impl.logger import console_tag, cyan, stderr_lock

# ---------------------------------------------------------------------------
#  Progress runner
# ---------------------------------------------------------------------------

async def run_with_progress(task, label):
    """Run an async callable with a progress spinner.

    task must be a coroutine-returning callable (e.g. lambda: provider.text_completion(...)).
    Shows: [<current command>] <label> 5s

    Spinner uses asyncio.create_task (docs.python.org/3.10/library/asyncio-task.html):
      "asyncio.create_task(coro) — Wrap the coro coroutine into a Task and schedule
      its execution. Return the Task object."
    Delay uses asyncio.sleep (docs.python.org/3.10/library/asyncio-task.html):
      "coroutine asyncio.sleep(delay) — Block for delay seconds."
    """
    wall_start = time.time()

    async def _spinner():
        start = time.time()
        try:
            while True:
                elapsed = int(time.time() - start)
                with stderr_lock:
                    sys.stderr.write(
                        f'\r{cyan(console_tag())} {label} {elapsed}s   '
                    )
                    sys.stderr.flush()
                # asyncio.sleep yields control to event loop each second
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    # asyncio.create_task schedules spinner concurrently with the AI call
    spinner_task = asyncio.create_task(_spinner())

    error = None
    result = None
    try:
        result = await task()
    except Exception as exc:
        error = exc
    finally:
        spinner_task.cancel()
        wall_elapsed = time.time() - wall_start
        with stderr_lock:
            sys.stderr.write(f'\r{cyan(console_tag())} {label} done ({wall_elapsed:.0f}s)   \n')
            sys.stderr.flush()

    if error:
        raise error

    return result
