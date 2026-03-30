# =====================================================
# STOCKNEWSBR ASYNC MARKET PIPELINE
# =====================================================

import asyncio
import logging

logger = logging.getLogger("stocknewsbr.engine.pipeline")

MAX_CONCURRENCY = 16
TASK_TIMEOUT = 30


async def run_async_pipeline(tasks):
    if not tasks:
        return []

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cleaned = []

        for result in results:
            if isinstance(result, Exception):
                logger.error("Async task failed: %s", result)
                continue

            cleaned.append(result)

        return cleaned
    except Exception as exc:
        logger.error("Async pipeline error: %s", exc)
        return []


async def run_task(func, *args):
    try:
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, func, *args),
            timeout=TASK_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Async task timeout for %s", getattr(func, "__name__", "task"))
        return None
    except Exception as exc:
        logger.error("Async task wrapper error: %s", exc)
        return None


async def run_batched_pipeline(func, items, batch_size: int = MAX_CONCURRENCY):
    if not items:
        return []

    results = []

    for start in range(0, len(items), max(1, batch_size)):
        batch = items[start : start + batch_size]
        tasks = [run_task(func, item) for item in batch]
        results.extend(await run_async_pipeline(tasks))

    return results
