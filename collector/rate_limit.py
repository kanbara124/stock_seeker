import random
import time
from urllib.parse import urlparse

import requests

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_DEFAULT_MIN_INTERVAL = 1.0
_MAX_RETRIES = 2
_RETRY_BACKOFF = 2.0

_HOST_MIN_INTERVAL = {
    "push2.eastmoney.com": 2.5,
}

_RETRYABLE = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

_last_call: dict[str, float] = {}


def _throttle(host: str) -> None:
    min_interval = _HOST_MIN_INTERVAL.get(host, _DEFAULT_MIN_INTERVAL)
    elapsed = time.monotonic() - _last_call.get(host, 0.0)
    wait = min_interval - elapsed
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.3))
    _last_call[host] = time.monotonic()


def safe_get(url: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", None) or {}
    headers.setdefault("User-Agent", _DEFAULT_UA)
    kwargs.setdefault("timeout", 8)
    host = urlparse(url).netloc

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        _throttle(host)
        try:
            return requests.get(url, headers=headers, **kwargs)
        except _RETRYABLE as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
    assert last_err is not None
    raise last_err
