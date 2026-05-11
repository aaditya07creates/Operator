import asyncio
from typing import Callable, Any, TypeVar, Coroutine
from functools import wraps

T = TypeVar('T')


def sync_to_async(func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    Convert a synchronous function to async.
    Useful for wrapping blocking operations.

    Example:
        @sync_to_async
        def blocking_operation():
            time.sleep(5)
            return "done"

        # Now can be awaited
        result = await blocking_operation()
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    return wrapper


def run_async(coro: Coroutine) -> Any:
    """
    Run an async coroutine in a sync context.
    Creates event loop if needed.

    Example:
        result = run_async(async_function())
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in an async context
            # Create a new loop in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists
        return asyncio.run(coro)


class AsyncContextManager:
    """
    Context manager for handling async operations in sync code.

    Example:
        with AsyncContextManager() as run:
            result = run(async_function())
    """

    def __enter__(self):
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self.loop.run_until_complete

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # Keep loop alive for reuse


def make_sync(async_func: Callable[..., Coroutine]) -> Callable:
    """
    Create a synchronous version of an async function.

    Example:
        async def async_operation():
            await asyncio.sleep(1)
            return "done"

        sync_operation = make_sync(async_operation)
        result = sync_operation()  # No await needed
    """

    @wraps(async_func)
    def wrapper(*args, **kwargs):
        return run_async(async_func(*args, **kwargs))

    return wrapper