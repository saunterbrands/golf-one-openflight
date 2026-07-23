"""Loopback relay between the Golf One backend and OpenGolfSim's FUSE iframe.

The current OpenGolfSim web app injects shots into its game iframe with
``postMessage``. Chromium's Golf One extension polls this relay, posts a
single canonical shot into that iframe, and reports the resulting FUSE event
back here. Only one live browser session and one in-flight shot are allowed;
that mirrors a physical hitting bay and prevents stale or duplicate shots.
"""

from __future__ import annotations

import copy
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


class InvalidBrowserSession(RuntimeError):
    """Raised when an expired, replaced, or unknown browser session is used."""


@dataclass(frozen=True)
class BrowserPublishResult:
    """Outcome of trying to place a shot in the browser delivery slot."""

    accepted: bool
    sequence: Optional[int] = None
    reason: str = ""


class BrowserShotRelay:
    """Thread-safe, one-shot-at-a-time relay for a local FUSE browser game."""

    def __init__(
        self,
        *,
        session_ttl_s: float = 45.0,
        shot_timeout_s: float = 45.0,
        poll_timeout_s: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(24),
    ):
        if session_ttl_s <= 0:
            raise ValueError("session_ttl_s must be positive")
        if shot_timeout_s <= 0:
            raise ValueError("shot_timeout_s must be positive")
        if poll_timeout_s < 0:
            raise ValueError("poll_timeout_s cannot be negative")

        self._session_ttl_s = session_ttl_s
        self._shot_timeout_s = shot_timeout_s
        self._poll_timeout_s = poll_timeout_s
        self._clock = clock
        self._token_factory = token_factory
        self._condition = threading.Condition(threading.RLock())

        self._session_id: Optional[str] = None
        self._session_expires_at = 0.0
        self._sequence = 0
        self._ready = False
        self._pending: Optional[dict] = None
        self._in_flight: Optional[dict] = None
        self._in_flight_started_at: Optional[float] = None
        self._last_delivery: Optional[dict] = None

    def _expire_locked(self) -> None:
        if self._session_id and self._clock() >= self._session_expires_at:
            self._session_id = None
            self._session_expires_at = 0.0
            self._ready = False
            self._pending = None
            self._in_flight = None
            self._in_flight_started_at = None
            self._condition.notify_all()

    def _expire_in_flight_locked(self) -> None:
        if (
            self._in_flight is not None
            and self._in_flight_started_at is not None
            and self._clock() - self._in_flight_started_at >= self._shot_timeout_s
        ):
            sequence = self._in_flight["sequence"]
            self._in_flight = None
            self._in_flight_started_at = None
            self._ready = True
            self._last_delivery = {
                "sequence": sequence,
                "state": "error",
                "reason": "OpenGolfSim did not finish the shot in time",
            }
            self._condition.notify_all()

    def _require_session_locked(self, session_id: str) -> None:
        self._expire_locked()
        if not session_id or session_id != self._session_id:
            raise InvalidBrowserSession("OpenGolfSim browser session is no longer active")

    def _touch_locked(self) -> None:
        self._session_expires_at = self._clock() + self._session_ttl_s

    def _game_state_locked(self) -> str:
        if not self._session_id:
            return "inactive"
        if self._pending is not None:
            return "queued"
        if self._in_flight is not None:
            return "in_flight"
        return "ready" if self._ready else "loading"

    def _status_locked(self) -> dict:
        return {
            "active": self._session_id is not None,
            "game_state": self._game_state_locked(),
            "cursor": self._sequence,
            "last_delivery": copy.deepcopy(self._last_delivery),
        }

    def open_session(self) -> dict:
        """Open a new game session and invalidate any stale tab/session.

        The returned cursor starts at the latest sequence. A freshly loaded
        game therefore never replays a shot created for an earlier round.
        """

        with self._condition:
            self._expire_locked()
            self._expire_in_flight_locked()
            self._session_id = self._token_factory()
            self._touch_locked()
            self._ready = True
            self._pending = None
            self._in_flight = None
            self._in_flight_started_at = None
            self._condition.notify_all()
            return {
                "session_id": self._session_id,
                "cursor": self._sequence,
                **self._status_locked(),
            }

    def mark_ready(self, session_id: str) -> dict:
        """Refresh a live session after FUSE reports a usable player/ball."""

        with self._condition:
            self._require_session_locked(session_id)
            self._expire_in_flight_locked()
            self._touch_locked()
            if self._pending is None and self._in_flight is None:
                self._ready = True
            return {
                "session_id": self._session_id,
                **self._status_locked(),
            }

    def close_session(self, session_id: str) -> None:
        """Close the matching browser session without affecting a newer tab."""

        with self._condition:
            self._require_session_locked(session_id)
            self._session_id = None
            self._session_expires_at = 0.0
            self._ready = False
            self._pending = None
            self._in_flight = None
            self._in_flight_started_at = None
            self._condition.notify_all()

    def is_active(self) -> bool:
        """Return whether a game session has checked in within its TTL."""

        with self._condition:
            self._expire_locked()
            self._expire_in_flight_locked()
            return self._session_id is not None

    def publish(self, payload: dict) -> BrowserPublishResult:
        """Queue one canonical FUSE payload for the active local game."""

        with self._condition:
            self._expire_locked()
            self._expire_in_flight_locked()
            if self._session_id is None:
                return BrowserPublishResult(
                    accepted=False,
                    reason="OpenGolfSim does not have an active browser game",
                )
            if not self._ready or self._pending is not None or self._in_flight is not None:
                return BrowserPublishResult(
                    accepted=False,
                    reason="OpenGolfSim is still playing the previous shot",
                )

            self._sequence += 1
            envelope = {
                "sequence": self._sequence,
                "payload": copy.deepcopy(payload),
            }
            self._pending = envelope
            self._ready = False
            self._last_delivery = {
                "sequence": self._sequence,
                "state": "queued",
            }
            self._condition.notify_all()
            return BrowserPublishResult(accepted=True, sequence=self._sequence)

    def poll(
        self,
        *,
        session_id: str,
        after: int,
        timeout_s: Optional[float] = None,
    ) -> list[dict]:
        """Long-poll for a shot newer than ``after``.

        Delivery remains visible until the browser advances its cursor, so a
        transient HTTP response loss does not silently lose a physical shot.
        """

        if not isinstance(after, int) or isinstance(after, bool) or after < 0:
            raise ValueError("after must be a non-negative integer")
        timeout = self._poll_timeout_s if timeout_s is None else timeout_s
        if timeout < 0:
            raise ValueError("timeout_s cannot be negative")

        real_deadline = time.monotonic() + timeout
        with self._condition:
            self._require_session_locked(session_id)
            self._expire_in_flight_locked()
            self._touch_locked()
            while True:
                if self._pending is not None and self._pending["sequence"] > after:
                    self._touch_locked()
                    return [copy.deepcopy(self._pending)]

                remaining = real_deadline - time.monotonic()
                if remaining <= 0:
                    self._touch_locked()
                    return []
                self._condition.wait(timeout=remaining)
                self._require_session_locked(session_id)
                self._expire_in_flight_locked()
                self._touch_locked()

    def acknowledge(
        self,
        *,
        session_id: str,
        sequence: int,
        state: str,
        result: Optional[dict] = None,
    ) -> dict:
        """Record browser posting, a completed FUSE result, or delivery error."""

        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        if state not in {"posted", "completed", "error"}:
            raise ValueError("state must be posted, completed, or error")

        with self._condition:
            self._require_session_locked(session_id)
            self._expire_in_flight_locked()
            self._touch_locked()

            if state == "posted":
                if (
                    self._last_delivery is not None
                    and self._last_delivery.get("sequence") == sequence
                    and self._last_delivery.get("state") in {"completed", "error"}
                ):
                    return self._status_locked()
                if self._pending is not None and self._pending["sequence"] == sequence:
                    self._in_flight = self._pending
                    self._pending = None
                    self._in_flight_started_at = self._clock()
                    self._last_delivery = {"sequence": sequence, "state": "posted"}
                elif self._in_flight is None or self._in_flight["sequence"] != sequence:
                    raise ValueError("shot sequence is not active in this browser session")
            elif (self._pending is not None and self._pending["sequence"] == sequence) or (
                self._in_flight is not None and self._in_flight["sequence"] == sequence
            ):
                self._pending = None
                self._in_flight = None
                self._in_flight_started_at = None
                self._ready = True
                self._last_delivery = {
                    "sequence": sequence,
                    "state": state,
                    **(
                        {"result": copy.deepcopy(result)}
                        if state == "completed" and result is not None
                        else {}
                    ),
                }
                self._condition.notify_all()
            elif (
                self._last_delivery is not None
                and self._last_delivery.get("sequence") == sequence
                and self._last_delivery.get("state") in {"completed", "error"}
            ):
                return self._status_locked()
            else:
                raise ValueError("shot sequence is not active in this browser session")

            return self._status_locked()

    def status(self) -> dict:
        """Return a public status snapshot without exposing the session token."""

        with self._condition:
            self._expire_locked()
            self._expire_in_flight_locked()
            return self._status_locked()
