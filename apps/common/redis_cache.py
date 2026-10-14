"""Redis cache that keeps a fixed number of connections and never takes the site down.

Under ASGI (daphne / uvicorn) Django makes a new cache object for every request, and Django's RedisCache
makes a new connection pool for every cache object and never closes it. Connections pile up until Redis
answers "max number of clients reached" and every page fails. Here:

* ``SharedConnectionPool`` — one pool per Redis URL for the whole process, with a fixed number of
  connections (a request waits a moment for a free one instead of opening another).
* ``SafeRedisCache`` — if Redis is unreachable or full, cache calls behave like a cache miss
  (the page is built fresh, rate limits let the request through) instead of a 500 error.
"""
import logging
import threading

import redis
from django.core.cache.backends.redis import RedisCache

log = logging.getLogger(__name__)
_pools = {}
_lock = threading.Lock()


class SharedConnectionPool(redis.BlockingConnectionPool):
    @classmethod
    def from_url(cls, url, **kwargs):
        key = (url, tuple(sorted((k, repr(v)) for k, v in kwargs.items())))
        with _lock:
            pool = _pools.get(key)
            if pool is None:
                pool = _pools[key] = super().from_url(url, **kwargs)
        return pool


def _safe(default):
    def wrap(method):
        def inner(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except redis.exceptions.RedisError as exc:
                log.warning("cache %s failed: %s", method.__name__, exc)
                return default(*args, **kwargs) if callable(default) else default
        inner.__name__ = method.__name__
        return inner
    return wrap


def _get_default(key, default=None, *args, **kwargs):
    return default


def _get_or_set_default(key, default=None, *args, **kwargs):
    return default() if callable(default) else default


class SafeRedisCache(RedisCache):
    get = _safe(_get_default)(RedisCache.get)
    get_many = _safe({})(RedisCache.get_many)
    get_or_set = _safe(_get_or_set_default)(RedisCache.get_or_set)
    has_key = _safe(False)(RedisCache.has_key)
    add = _safe(True)(RedisCache.add)  # rate limits: treat as a first visit
    set = _safe(None)(RedisCache.set)
    set_many = _safe([])(RedisCache.set_many)
    touch = _safe(False)(RedisCache.touch)
    delete = _safe(False)(RedisCache.delete)
    delete_many = _safe(None)(RedisCache.delete_many)
    incr = _safe(1)(RedisCache.incr)
    clear = _safe(None)(RedisCache.clear)
