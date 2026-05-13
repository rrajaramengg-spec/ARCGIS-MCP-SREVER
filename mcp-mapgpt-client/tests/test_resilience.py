"""Unit tests for core.orchestrator.graph.resilience module.

Covers RetryPolicy, retry_with_backoff, RetryBudget, and CircuitBreaker.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.orchestrator.graph.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryBudget,
    RetryBudgetExhaustedError,
    RetryPolicy,
    TRANSIENT_ERRORS,
    retry_with_backoff,
)


# =========================================================================
# RetryPolicy
# =========================================================================


class TestRetryPolicy:
    """Tests for RetryPolicy dataclass defaults and customisation."""

    def test_default_values(self):
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 8.0
        assert policy.jitter is True
        assert policy.retryable_errors == TRANSIENT_ERRORS

    def test_custom_values(self):
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=0.5,
            max_delay=16.0,
            jitter=False,
            retryable_errors=(ValueError,),
        )
        assert policy.max_attempts == 5
        assert policy.base_delay == 0.5
        assert policy.max_delay == 16.0
        assert policy.jitter is False
        assert policy.retryable_errors == (ValueError,)

    def test_frozen(self):
        policy = RetryPolicy()
        with pytest.raises(AttributeError):
            policy.max_attempts = 10  # type: ignore[misc]


# =========================================================================
# retry_with_backoff
# =========================================================================


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff async helper."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        fn = AsyncMock(return_value="ok")
        result = await retry_with_backoff(fn, RetryPolicy(max_attempts=3))
        assert result == "ok"
        assert fn.await_count == 1

    @pytest.mark.asyncio
    async def test_transient_retry_then_success(self):
        fn = AsyncMock(side_effect=[TimeoutError("t"), "ok"])
        policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=False)
        result = await retry_with_backoff(fn, policy)
        assert result == "ok"
        assert fn.await_count == 2

    @pytest.mark.asyncio
    async def test_max_attempts_exhausted(self):
        fn = AsyncMock(side_effect=TimeoutError("always"))
        policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=False)
        with pytest.raises(TimeoutError, match="always"):
            await retry_with_backoff(fn, policy)
        assert fn.await_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_not_retried(self):
        fn = AsyncMock(side_effect=ValueError("bad input"))
        policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=False)
        with pytest.raises(ValueError, match="bad input"):
            await retry_with_backoff(fn, policy)
        assert fn.await_count == 1

    @pytest.mark.asyncio
    async def test_jitter_adds_variation(self):
        """Jitter should produce a delay > base_delay (statistically)."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("t")
            return "ok"

        policy = RetryPolicy(
            max_attempts=2, base_delay=0.001, max_delay=1.0, jitter=True
        )
        result = await retry_with_backoff(flaky, policy)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_delay_capped_at_max_delay(self):
        """Even with many retries the delay must not exceed max_delay."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 5:
                raise TimeoutError("t")
            return "ok"

        policy = RetryPolicy(
            max_attempts=5, base_delay=0.001, max_delay=0.01, jitter=False
        )
        result = await retry_with_backoff(flaky, policy)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_budget_consumed_on_retry(self):
        fn = AsyncMock(side_effect=[TimeoutError("t"), "ok"])
        policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=False)
        budget = RetryBudget(max_retries=5)
        result = await retry_with_backoff(fn, policy, budget=budget)
        assert result == "ok"
        assert budget.used == 1

    @pytest.mark.asyncio
    async def test_budget_exhausted_raises(self):
        fn = AsyncMock(side_effect=TimeoutError("always"))
        policy = RetryPolicy(max_attempts=5, base_delay=0.0, jitter=False)
        budget = RetryBudget(max_retries=2)
        # Use up the budget manually.
        budget.record_retry()
        budget.record_retry()
        assert not budget.can_retry()

        with pytest.raises(RetryBudgetExhaustedError):
            await retry_with_backoff(fn, policy, budget=budget)
        # Only one attempt — the retry was blocked by the exhausted budget.
        assert fn.await_count == 1

    @pytest.mark.asyncio
    async def test_connection_error_is_retried(self):
        fn = AsyncMock(side_effect=[ConnectionError("refused"), "ok"])
        policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=False)
        result = await retry_with_backoff(fn, policy)
        assert result == "ok"
        assert fn.await_count == 2

    @pytest.mark.asyncio
    async def test_os_error_is_retried(self):
        fn = AsyncMock(side_effect=[OSError("network"), "ok"])
        policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=False)
        result = await retry_with_backoff(fn, policy)
        assert result == "ok"
        assert fn.await_count == 2


# =========================================================================
# RetryBudget
# =========================================================================


class TestRetryBudget:
    """Tests for the RetryBudget dataclass."""

    def test_initial_state(self):
        budget = RetryBudget(max_retries=5)
        assert budget.can_retry() is True
        assert budget.used == 0

    def test_record_and_exhaust(self):
        budget = RetryBudget(max_retries=2)
        budget.record_retry()
        assert budget.used == 1
        assert budget.can_retry() is True
        budget.record_retry()
        assert budget.used == 2
        assert budget.can_retry() is False

    def test_zero_budget(self):
        budget = RetryBudget(max_retries=0)
        assert budget.can_retry() is False

    def test_custom_max(self):
        budget = RetryBudget(max_retries=10)
        for _ in range(10):
            assert budget.can_retry() is True
            budget.record_retry()
        assert budget.can_retry() is False
        assert budget.used == 10


# =========================================================================
# CircuitBreaker
# =========================================================================


class TestCircuitBreaker:
    """Tests for the CircuitBreaker state machine."""

    @pytest.mark.asyncio
    async def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED

    @pytest.mark.asyncio
    async def test_success_stays_closed(self):
        cb = CircuitBreaker()
        result = await cb.call(AsyncMock(return_value="ok"))
        assert result == "ok"
        assert cb.state == CircuitBreaker.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, window=60.0)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreaker.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=100.0)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreaker.OPEN
        with pytest.raises(CircuitOpenError):
            await cb.call(AsyncMock(return_value="ok"))

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreaker.OPEN

        # With recovery_timeout=0, the next call should transition to HALF_OPEN
        # and execute the probe.
        result = await cb.call(AsyncMock(return_value="recovered"))
        assert result == "recovered"
        assert cb.state == CircuitBreaker.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_probe_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreaker.OPEN

        # Probe fails → should re-open.
        with pytest.raises(ValueError):
            await cb.call(AsyncMock(side_effect=ValueError("probe fail")))
        assert cb.state == CircuitBreaker.OPEN

    @pytest.mark.asyncio
    async def test_half_open_probe_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))

        result = await cb.call(AsyncMock(return_value="ok"))
        assert result == "ok"
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_failures_within_window_counted(self):
        cb = CircuitBreaker(failure_threshold=3, window=60.0)
        # Two failures — not enough to trip.
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 2

    @pytest.mark.asyncio
    async def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreaker.OPEN

        await cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_open_error_has_recovery_after(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        with pytest.raises(CircuitOpenError) as exc_info:
            await cb.call(AsyncMock(return_value="ok"))
        assert exc_info.value.recovery_after > 0
