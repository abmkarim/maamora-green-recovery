"""Retry avec backoff exponentiel pour les appels réseau (Earth Engine, HTTP)."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)

class RequestTooLargeError(RuntimeError):
    """La requête doit être découpée (mémoire, délai ou charge utile dépassés)."""


def is_too_large(exc: BaseException) -> bool:
    """Indique si l'erreur suggère de découper la requête."""
    msg = str(exc).lower()
    return any(m in msg for m in ("memory limit", "computation timed out", "payload size"))


def with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = 6,
    base: float = 2.0,
    max_wait: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
    label: str = "appel",
) -> T:
    """Exécute `fn` avec retry et backoff exponentiel (avec gigue).

    Les erreurs de taille de requête sont relancées immédiatement sous forme de
    `RequestTooLargeError` pour que l'appelant découpe le lot.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - toute erreur réseau/EE est candidate au retry
            if is_too_large(exc):
                raise RequestTooLargeError(str(exc)) from exc
            msg = str(exc).lower()
            if any(m in msg for m in ("not found", "does not exist", "permission")):
                raise
            attempt += 1
            if attempt > max_retries:
                raise
            wait = min(max_wait, base**attempt) * (0.5 + random.random() / 2)
            log.warning("%s : échec %d/%d (%s), nouvel essai dans %.1fs",
                        label, attempt, max_retries, type(exc).__name__, wait)
            sleep(wait)
