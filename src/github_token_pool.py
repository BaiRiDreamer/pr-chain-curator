"""Shared GitHub token pool with cooldown-aware scheduling."""
import threading
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GitHubTokenState:
    """Runtime state for a GitHub token."""
    token: str
    available_at: float = 0.0
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset_at: Optional[float] = None
    leased: bool = False


class GitHubTokenPool:
    """Coordinates a pool of GitHub tokens across concurrent workers."""

    def __init__(self, tokens: List[str]):
        cleaned = [token.strip() for token in tokens if token and token.strip()]
        if not cleaned:
            raise ValueError("At least one GitHub token is required")

        self._states = [GitHubTokenState(token=token) for token in cleaned]
        self._condition = threading.Condition()
        self._next_index = 0

    def acquire(self) -> GitHubTokenState:
        """Block until a token is available, then return it."""
        with self._condition:
            while True:
                now = time.time()
                state = self._pick_available_state(now)
                if state is not None:
                    state.leased = True
                    return state

                next_available = min(state.available_at for state in self._states)
                wait_seconds = max(next_available - now, 0.05)
                self._condition.wait(timeout=wait_seconds)

    def defer(self, state: GitHubTokenState, wait_seconds: float,
              remaining: Optional[int] = None,
              reset_at: Optional[float] = None):
        """Mark a token unavailable until the given wait has elapsed."""
        with self._condition:
            now = time.time()
            state.leased = False
            state.available_at = max(state.available_at, now + max(wait_seconds, 0.0))
            if remaining is not None:
                state.rate_limit_remaining = remaining
            if reset_at is not None:
                state.rate_limit_reset_at = reset_at
                state.available_at = max(state.available_at, reset_at)
            self._condition.notify_all()

    def release(self, state: GitHubTokenState, min_delay: float = 0.0,
                remaining: Optional[int] = None,
                reset_at: Optional[float] = None):
        """Release a leased token and update its availability."""
        with self._condition:
            now = time.time()
            state.leased = False
            state.available_at = max(state.available_at, now + max(min_delay, 0.0))
            if remaining is not None:
                state.rate_limit_remaining = remaining
            if reset_at is not None:
                state.rate_limit_reset_at = reset_at

            if remaining == 0 and reset_at is not None:
                state.available_at = max(state.available_at, reset_at)

            self._condition.notify_all()

    def _pick_available_state(self, now: float) -> Optional[GitHubTokenState]:
        """Pick the next available token in round-robin order."""
        state_count = len(self._states)
        for offset in range(state_count):
            index = (self._next_index + offset) % state_count
            state = self._states[index]
            if not state.leased and state.available_at <= now:
                self._next_index = (index + 1) % state_count
                return state
        return None
