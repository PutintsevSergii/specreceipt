"""Operation-scoped batching for derived reports, never durable transactions."""
from contextlib import contextmanager
from functools import wraps


@contextmanager
def scope(h):
    h._report_depth = getattr(h, '_report_depth', 0) + 1
    try:
        yield
    finally:
        h._report_depth -= 1
        if not h._report_depth and getattr(h, '_report_dirty', False):
            h._report_dirty = False
            from .reporting import refresh_current
            refresh_current(h)


def operation(method):
    @wraps(method)
    def call(h, *args, **kwargs):
        with scope(h):
            return method(h, *args, **kwargs)
    return call
