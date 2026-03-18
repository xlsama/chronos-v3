from __future__ import annotations

import time

import httpx


def wait_for_healthy(url: str, timeout: float = 60) -> None:
    start = time.monotonic()
    delay = 0.5

    while time.monotonic() - start < timeout:
        try:
            resp = httpx.get(url, timeout=5)
            if resp.is_success:
                return
        except Exception:
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)

    raise TimeoutError(f"Health check timeout: {url} not ready after {timeout}s")
