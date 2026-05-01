import os
import threading
import time
from collections import deque
from typing import Deque, Optional


_REQUEST_TIMESTAMPS: Deque[float] = deque()
_REQUEST_LOCK = threading.Lock()


def get_configured_llm_rpm(default: Optional[int] = None) -> Optional[int]:
    raw_value = os.environ.get("UNIVERRA_LLM_RPM") or os.environ.get("LLM_REQUESTS_PER_MINUTE")
    if not raw_value:
        return default

    try:
        rpm = int(raw_value)
    except ValueError:
        return default

    return rpm if rpm > 0 else default


def wait_for_llm_slot():
    rpm = get_configured_llm_rpm()
    if not rpm:
        return

    min_interval = 60.0 / max(rpm, 1)

    while True:
        sleep_seconds = 0.0
        with _REQUEST_LOCK:
            now = time.monotonic()
            while _REQUEST_TIMESTAMPS and now - _REQUEST_TIMESTAMPS[0] >= 60.0:
                _REQUEST_TIMESTAMPS.popleft()

            if _REQUEST_TIMESTAMPS:
                spacing_wait = min_interval - (now - _REQUEST_TIMESTAMPS[-1])
                if spacing_wait > sleep_seconds:
                    sleep_seconds = spacing_wait

            if len(_REQUEST_TIMESTAMPS) >= rpm:
                window_wait = 60.0 - (now - _REQUEST_TIMESTAMPS[0]) + 0.05
                if window_wait > sleep_seconds:
                    sleep_seconds = window_wait

            if sleep_seconds <= 0:
                _REQUEST_TIMESTAMPS.append(now)
                return

        time.sleep(sleep_seconds)
