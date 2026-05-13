"""Resilience primitives for graph node execution.

Provides per-node retry with exponential backoff, a graph-level retry budget
to prevent retry amplification, and a circuit breaker for ArcGIS service
protection.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RetryBudgetExhaustedError(Exception):
    """Raised when the graph-level retry budget is exhausted."""


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and calls are rejected."""

    def __init__(self, recovery_after: float) -> None:
        self.recovery_after = recovery_after
        super().__init__(
            f"Circuit open, retry after {recovery_after:.1f}s"
        )


# Default set of errors considered transient and retryable.
TRANSIENT_ERRORS: Tuple[Type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
)


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for per-node retry behaviour.

    Args:
        max_attempts: Total execution attempts (1 = no retry).
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Upper bound on delay in seconds.
        jitter: When ``True``, add uniform random jitter up to 50 % of the
            computed delay to spread retry storms.
        retryable_errors: Tuple of exception types considered transient.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 8.0
    jitter: bool = True
    retryable_errors: Tuple[Type[BaseException], ...] = TRANSIENT_ERRORS


# ---------------------------------------------------------------------------
# RetryBudget
# ---------------------------------------------------------------------------


@dataclass
class RetryBudget:
    """Graph-level cap on the total number of retries across all nodes.

    Prevents retry amplification — if many nodes fail simultaneously, the
    budget stops retries early so the graph fails fast instead of
    multiplying latency.

    Args:
        max_retries: Maximum number of retries allowed across the entire
            graph execution.
    """

    max_retries: int = 5
    _used: int = field(default=0, init=False, repr=False)

    @property
    def used(self) -> int:
        """Number of retries consumed so far."""
        return self._used

    def can_retry(self) -> bool:
        """Return ``True`` if budget still has capacity."""
        return self._used < self.max_retries

    def record_retry(self) -> None:
        """Consume one retry from the budget."""
        self._used += 1


# ---------------------------------------------------------------------------
# retry_with_backoff
# ---------------------------------------------------------------------------


async def retry_with_backoff(
    fn: Callable[..., Awaitable[Any]],
    policy: RetryPolicy,
    budget: Optional[RetryBudget] = None,
) -> Any:
    """Execute *fn* with exponential backoff on transient errors.

    Args:
        fn: Zero-argument async callable to execute.
        policy: Retry configuration.
        budget: Optional graph-level retry budget.  When supplied, each
            retry consumes one unit and raises
            ``RetryBudgetExhaustedError`` when exhausted.

    Returns:
        The return value of *fn* on success.

    Raises:
        RetryBudgetExhaustedError: When *budget* is exhausted before a
            retry can proceed.
        Exception: The last exception raised by *fn* after all attempts
            are exhausted or a non-retryable error is encountered.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(policy.max_attempts):
        try:
            return await fn()
        except policy.retryable_errors as exc:
            last_exc = exc
            remaining = policy.max_attempts - attempt - 1
            if remaining == 0:
                # All attempts exhausted — propagate.
                raise

            # Check graph-level budget.
            if budget is not None and not budget.can_retry():
                raise RetryBudgetExhaustedError(
                    f"Retry budget exhausted ({budget.max_retries} retries used)"
                ) from exc

            if budget is not None:
                budget.record_retry()

            delay = min(policy.base_delay * (2 ** attempt), policy.max_delay)
            if policy.jitter:
                delay += random.uniform(0, delay * 0.5)

            logger.warning(
                "Retry %d/%d after %.2fs — %s",
                attempt + 1,
                policy.max_attempts - 1,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
        except Exception:
            # Non-retryable error — propagate immediately.
            raise

    # Should not be reached, but satisfy the type checker.
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Three-state circuit breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.

    Protects against hammering a degraded external service (e.g. ArcGIS
    REST API).  Shared across all requests as a singleton.

    Args:
        failure_threshold: Number of failures within *window* to trip open.
        recovery_timeout: Seconds to wait in OPEN before transitioning to
            HALF_OPEN.
        window: Rolling time window in seconds for failure counting.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        window: float = 60.0,
    ) -> None:
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._window = window

        self._state: str = self.CLOSED
        self._failure_timestamps: list[float] = []
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()

    # -- Public properties ---------------------------------------------------

    @property
    def state(self) -> str:
        """Current circuit state (CLOSED, OPEN, or HALF_OPEN)."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Number of recorded failures within the rolling window."""
        now = time.monotonic()
        return len([t for t in self._failure_timestamps if now - t < self._window])

    # -- Core API ------------------------------------------------------------

    async def call(self, fn: Callable[..., Awaitable[Any]]) -> Any:
        """Execute *fn* through the circuit breaker.

        Args:
            fn: Zero-argument async callable.

        Returns:
            The return value of *fn* on success.

        Raises:
            CircuitOpenError: When the circuit is OPEN and the recovery
                timeout has not yet elapsed.
        """
        await self._check_state()

        try:
            result = await fn()
        except Exception:
            await self._record_failure()
            raise

        await self._record_success()
        return result

    # -- Internal state machine ---------------------------------------------

    async def _check_state(self) -> None:
        async with self._lock:
            if self._state == self.OPEN:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._recovery_timeout:
                    self._state = self.HALF_OPEN
                    logger.info("Circuit breaker → HALF_OPEN (probe allowed)")
                else:
                    remaining = self._recovery_timeout - elapsed
                    raise CircuitOpenError(recovery_after=remaining)

    async def _record_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._failure_timestamps.append(now)
            # Trim old entries outside the window.
            self._failure_timestamps = [
                t for t in self._failure_timestamps if now - t < self._window
            ]

            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._opened_at = now
                logger.warning("Circuit breaker → OPEN (probe failed)")
            elif len(self._failure_timestamps) >= self._threshold:
                self._state = self.OPEN
                self._opened_at = now
                logger.warning(
                    "Circuit breaker → OPEN (%d failures in %.0fs)",
                    len(self._failure_timestamps),
                    self._window,
                )

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state == self.HALF_OPEN:
                self._state = self.CLOSED
                self._failure_timestamps.clear()
                logger.info("Circuit breaker → CLOSED (probe succeeded)")
            elif self._state == self.CLOSED:
                # Successful call — no state change needed, but reset count
                # so healthy calls don't accumulate stale failures.
                now = time.monotonic()
                self._failure_timestamps = [
                    t for t in self._failure_timestamps if now - t < self._window
                ]

    async def reset(self) -> None:
        """Force-reset the circuit to CLOSED. For testing."""
        async with self._lock:
            self._state = self.CLOSED
            self._failure_timestamps.clear()
            self._opened_at = 0.0
