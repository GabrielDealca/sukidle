"""A deliberately polite HTTP client: rate limited, honest User-Agent, backs off, never bypasses."""

import logging
import random
import time
from collections.abc import Callable

import httpx

log = logging.getLogger(__name__)


class BlockedError(RuntimeError):
    """The site refused us (401/403). We stop; we never try to get around it."""


class PoliteClient:
    def __init__(
        self,
        user_agent: str,
        *,
        min_interval: float = 1.0,
        jitter: float = 0.5,
        max_retries: int = 4,
        backoff_base: float = 5.0,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self.jitter = jitter
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self.request_count = 0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def _wait_turn(self) -> None:
        if self._last_request is None:
            return
        target = self.min_interval + random.uniform(0, self.jitter)
        elapsed = self._clock() - self._last_request
        if elapsed < target:
            self._sleep(target - elapsed)

    def get(
        self, url: str, *, params: dict | None = None, headers: dict | None = None
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            self._wait_turn()
            self._last_request = self._clock()
            self.request_count += 1
            response = self._client.get(url, params=params, headers=headers)

            if response.status_code in (401, 403):
                raise BlockedError(f"{response.status_code} from {url}; stopping.")
            if response.status_code == 429 or response.status_code >= 500:
                delay = self._retry_delay(response, attempt)
                log.warning("HTTP %s from %s, retry in %.0fs", response.status_code, url, delay)
                if attempt < self.max_retries:
                    self._sleep(delay)
                    continue
            response.raise_for_status()
            return response
        raise RuntimeError("unreachable")  # pragma: no cover

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return float(retry_after)
        return self.backoff_base * (2**attempt)

    def close(self) -> None:
        self._client.close()
