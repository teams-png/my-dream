"""Production cache on Redis: one connection pool per process (no new connections per request under ASGI),
and Redis trouble never turns a page into a 500."""
import asyncio
import shutil
import socket
import subprocess
import time

import pytest
from asgiref.sync import sync_to_async
from django.core.cache import CacheHandler

OPTIONS = {"pool_class": "apps.common.redis_cache.SharedConnectionPool", "max_connections": 5, "timeout": 3,
           "socket_connect_timeout": 1, "socket_timeout": 1}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def redis_url():
    if not shutil.which("redis-server"):
        pytest.skip("redis-server not installed")
    port = _free_port()
    proc = subprocess.Popen(["redis-server", "--port", str(port), "--save", "", "--appendonly", "no"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import redis
    client = redis.Redis(port=port)
    for _ in range(50):
        try:
            client.ping()
            break
        except redis.exceptions.ConnectionError:
            time.sleep(0.1)
    yield f"redis://127.0.0.1:{port}/0", client
    proc.terminate()
    proc.wait(5)


def _handler(url):
    return CacheHandler({"default": {"BACKEND": "apps.common.redis_cache.SafeRedisCache", "LOCATION": url,
                                     "KEY_PREFIX": "t", "OPTIONS": OPTIONS}})


def test_connections_stay_fixed_across_many_async_requests(redis_url):
    url, client = redis_url
    handler = _handler(url)

    def one_request(i):
        cache = handler["default"]  # under ASGI each request gets its own cache object
        cache.set(f"k{i}", i)
        assert cache.get(f"k{i}") == i
        handler.close_all()

    async def run():
        async def request(i):  # a new context per request, like an ASGI server
            await sync_to_async(one_request, thread_sensitive=False)(i)
        await asyncio.gather(*(request(i) for i in range(300)))

    client.config_resetstat()
    asyncio.run(run())
    opened = client.info("stats")["total_connections_received"]  # Django's own RedisCache opens one per request
    assert opened <= OPTIONS["max_connections"], opened


def test_redis_down_is_a_cache_miss_not_an_error():
    handler = _handler(f"redis://127.0.0.1:{_free_port()}/0")  # nothing listens there
    cache = handler["default"]
    assert cache.get("x", "fallback") == "fallback"
    assert cache.get_or_set("y", lambda: 7) == 7
    cache.set("x", 1)
    assert cache.add("rate", 1, 60) is True and cache.incr("rate") == 1
    assert cache.get_many(["a", "b"]) == {} and cache.delete("x") is False
