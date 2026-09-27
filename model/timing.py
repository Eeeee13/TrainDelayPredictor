"""Request-local, non-overlapping stage timings for inference diagnostics."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

current_timings: ContextVar[dict | None] = ContextVar("inference_timings", default=None)


@contextmanager
def measure(stage):
    timings = current_timings.get()
    if timings is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        timings[stage] = timings.get(stage, 0.0) + (perf_counter() - started) * 1000


@contextmanager
def measured_lock(lock, stage):
    with measure(stage):
        lock.acquire()
    try:
        yield
    finally:
        lock.release()
