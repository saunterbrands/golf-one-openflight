"""Threaded OpenGolfSim Web API bridge.

OpenGolfSim's browser simulator accepts launch-monitor data over one WebSocket
whose path identifies the signed-in account.  This module owns that connection
in the backend so shot delivery does not depend on the kiosk page's lifecycle.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Protocol, Tuple
from urllib.parse import quote

from simple_websocket import Client

from openflight.sim.types import ResolvedShot

logger = logging.getLogger(__name__)

OPENGOLFSIM_WEB_API_BASE = "wss://app.opengolfsim.com/api"
DEFAULT_RECONNECT_BACKOFF: Tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)
_DEVICE_READY_FRAME = json.dumps({"type": "device", "status": "ready"}, separators=(",", ":"))


class WebSocketConnection(Protocol):
    """Small subset of ``simple_websocket.Client`` used by the bridge."""

    def send(self, data: str) -> None: ...

    def receive(self, timeout: Optional[float] = None): ...

    def close(self, reason=None, message=None) -> None: ...


WebSocketFactory = Callable[[str], WebSocketConnection]


class WebBridgeState(str, Enum):
    """User-visible lifecycle states for the OpenGolfSim Web connection."""

    STOPPED = "stopped"
    UNCONFIGURED = "unconfigured"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    INVALID_USER = "invalid_user"


@dataclass(frozen=True)
class WebBridgeStatus:
    """Immutable status snapshot delivered to the UI/server callback."""

    state: WebBridgeState
    message: str = ""
    attempt: int = 0
    next_retry_in_s: float = 0.0
    permanent: bool = False


StatusCallback = Callable[[WebBridgeStatus], None]


def open_golf_sim_websocket_url(email: str) -> str:
    """Build the account-specific Web API URL without leaking raw delimiters."""

    return f"{OPENGOLFSIM_WEB_API_BASE}/{quote(email.strip(), safe='')}"


def build_web_shot_frame(resolved: ResolvedShot) -> str:
    """Serialize a resolved shot for OpenGolfSim's Web API.

    ``ResolvedShot`` stores speed in mph and spin in rpm, so the payload is
    explicitly imperial.  OpenFlight and the OpenGolfSim Web API use opposite
    spin-axis signs; invert only that field at this boundary.
    """

    spin_axis = round(-resolved.spin_axis_deg, 1)
    if spin_axis == 0:
        spin_axis = 0.0

    payload = {
        "type": "shot",
        "unit": "imperial",
        "shot": {
            "ballSpeed": round(resolved.ball_speed_mph, 1),
            "verticalLaunchAngle": round(resolved.vla, 1),
            "horizontalLaunchAngle": round(resolved.hla, 1),
            "spinSpeed": round(resolved.total_spin_rpm, 0),
            "spinAxis": spin_axis,
        },
    }
    return json.dumps(payload, separators=(",", ":"))


def _default_websocket_factory(url: str) -> WebSocketConnection:
    """Open a production WebSocket using the project's existing WS stack."""

    return Client.connect(url, ping_interval=25)


class OpenGolfSimWebBridge:
    """Own one reconnecting OpenGolfSim WebSocket connection.

    Public methods are safe to call from Flask/Socket.IO worker threads.  A
    single background thread owns connect and receive operations; outgoing shot
    writes and socket replacement are serialized by ``_socket_lock``.
    """

    def __init__(
        self,
        *,
        email: str = "",
        status_callback: Optional[StatusCallback] = None,
        websocket_factory: WebSocketFactory = _default_websocket_factory,
        reconnect_backoff: Tuple[float, ...] = DEFAULT_RECONNECT_BACKOFF,
        receive_timeout_s: float = 0.25,
    ):
        if not reconnect_backoff:
            raise ValueError("reconnect_backoff must contain at least one delay")
        if any(delay < 0 for delay in reconnect_backoff):
            raise ValueError("reconnect_backoff delays cannot be negative")
        if receive_timeout_s <= 0:
            raise ValueError("receive_timeout_s must be positive")

        self._email = email.strip()
        self._status_callback = status_callback
        self._websocket_factory = websocket_factory
        self._reconnect_backoff = reconnect_backoff
        self._receive_timeout_s = receive_timeout_s

        self._lifecycle_lock = threading.RLock()
        self._socket_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._websocket: Optional[WebSocketConnection] = None
        self._configuration_generation = 0
        self._status = WebBridgeStatus(WebBridgeState.STOPPED, "Bridge is stopped")

    @property
    def status(self) -> WebBridgeStatus:
        """Return the current immutable status snapshot."""

        with self._lifecycle_lock:
            return self._status

    @property
    def email(self) -> str:
        """Return the configured OpenGolfSim account email."""

        with self._lifecycle_lock:
            return self._email

    def is_connected(self) -> bool:
        """Whether a ready WebSocket is currently available for shots."""

        return self.status.state == WebBridgeState.CONNECTED

    def set_status_callback(
        self, callback: Optional[StatusCallback], *, replay: bool = True
    ) -> None:
        """Replace the status callback and optionally replay the latest status."""

        with self._lifecycle_lock:
            self._status_callback = callback
            status = self._status
        if callback is not None and replay:
            self._invoke_status_callback(callback, status)

    def configure_email(self, email: str) -> None:
        """Set or clear the account email and reconnect immediately when running.

        Calling this again with the same email is intentional: it lets an
        operator retry after creating or correcting an OpenGolfSim account.
        """

        with self._lifecycle_lock:
            self._email = email.strip()
            self._configuration_generation += 1
        self._drop_websocket()
        self._wake_event.set()

    def start(self) -> None:
        """Start the bridge's connection worker (idempotent)."""

        with self._lifecycle_lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._worker = threading.Thread(
                target=self._connection_loop,
                name="opengolfsim-web",
                daemon=True,
            )
            worker = self._worker
        worker.start()

    def stop(self) -> None:
        """Stop reconnecting, close the socket, and join the worker."""

        self._stop_event.set()
        self._wake_event.set()
        self._drop_websocket()

        with self._lifecycle_lock:
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=3.0)
        with self._lifecycle_lock:
            if self._worker is worker and (worker is None or not worker.is_alive()):
                self._worker = None
        self._publish(WebBridgeStatus(WebBridgeState.STOPPED, "Bridge is stopped"))

    def send_shot(self, resolved: ResolvedShot) -> bool:
        """Send one resolved shot, returning ``False`` if not connected.

        A send failure drops the socket so the owner thread reconnects.  Shots
        are not queued: stale golf shots must not be replayed after a network
        outage.
        """

        frame = build_web_shot_frame(resolved)
        failed_socket: Optional[WebSocketConnection] = None
        with self._socket_lock:
            websocket = self._websocket
            if websocket is None:
                return False
            try:
                websocket.send(frame)
            except Exception:  # SimpleWebSocket may surface protocol or socket errors.
                logger.info("OpenGolfSim Web shot send failed", exc_info=True)
                if self._websocket is websocket:
                    self._websocket = None
                failed_socket = websocket

        if failed_socket is not None:
            self._close_websocket(failed_socket)
            self._wake_event.set()
            return False
        return True

    def _connection_loop(self) -> None:
        attempt = 1
        while not self._stop_event.is_set():
            email, generation = self._configuration()
            if not email:
                self._publish(
                    WebBridgeStatus(
                        WebBridgeState.UNCONFIGURED,
                        "Enter the OpenGolfSim account email to connect",
                    )
                )
                self._wait_for_interrupt(generation, timeout=None)
                attempt = 1
                continue

            state = WebBridgeState.CONNECTING if attempt == 1 else WebBridgeState.RECONNECTING
            self._publish(
                WebBridgeStatus(
                    state,
                    "Connecting to OpenGolfSim",
                    attempt=attempt,
                )
            )

            websocket: Optional[WebSocketConnection] = None
            failure: Optional[Exception] = None
            try:
                websocket = self._websocket_factory(open_golf_sim_websocket_url(email))
                websocket.send(_DEVICE_READY_FRAME)
                if not self._claim_websocket(websocket, generation):
                    websocket = None
                    attempt = 1
                    continue
                self._publish(WebBridgeStatus(WebBridgeState.CONNECTED, "OpenGolfSim is connected"))
                attempt = 1
                failure = self._monitor_connection(websocket, generation)
            except Exception as exc:  # Network/protocol failures are retried below.
                failure = exc
            finally:
                if websocket is not None:
                    self._release_websocket(websocket)

            if self._stop_event.is_set():
                break
            if self._generation_changed(generation):
                attempt = 1
                continue
            if failure is not None and self._is_invalid_user(failure):
                message = getattr(failure, "message", None) or "Invalid User"
                self._publish(
                    WebBridgeStatus(
                        WebBridgeState.INVALID_USER,
                        str(message),
                        permanent=True,
                    )
                )
                self._wait_for_interrupt(generation, timeout=None)
                attempt = 1
                continue

            delay = self._reconnect_backoff[min(attempt - 1, len(self._reconnect_backoff) - 1)]
            attempt += 1
            message = str(failure) if failure is not None else "Connection closed"
            self._publish(
                WebBridgeStatus(
                    WebBridgeState.RECONNECTING,
                    message,
                    attempt=attempt,
                    next_retry_in_s=delay,
                )
            )
            self._wait_for_interrupt(generation, timeout=delay)

    def _configuration(self) -> tuple[str, int]:
        with self._lifecycle_lock:
            return self._email, self._configuration_generation

    def _generation_changed(self, generation: int) -> bool:
        with self._lifecycle_lock:
            return self._configuration_generation != generation

    def _claim_websocket(self, websocket: WebSocketConnection, generation: int) -> bool:
        with self._lifecycle_lock:
            if self._stop_event.is_set() or self._configuration_generation != generation:
                self._close_websocket(websocket)
                return False
            with self._socket_lock:
                self._websocket = websocket
        return True

    def _monitor_connection(
        self, websocket: WebSocketConnection, generation: int
    ) -> Optional[Exception]:
        while not self._stop_event.is_set() and not self._generation_changed(generation):
            with self._socket_lock:
                if self._websocket is not websocket:
                    return ConnectionError("OpenGolfSim socket was dropped")
            try:
                websocket.receive(timeout=self._receive_timeout_s)
            except Exception as exc:  # Close frames and socket errors end this connection.
                return exc
        return None

    def _release_websocket(self, websocket: WebSocketConnection) -> None:
        with self._socket_lock:
            if self._websocket is websocket:
                self._websocket = None
        self._close_websocket(websocket)

    def _drop_websocket(self) -> None:
        with self._socket_lock:
            websocket = self._websocket
            self._websocket = None
        if websocket is not None:
            self._close_websocket(websocket)

    @staticmethod
    def _close_websocket(websocket: WebSocketConnection) -> None:
        try:
            websocket.close()
        except Exception:
            logger.debug("OpenGolfSim WebSocket close failed", exc_info=True)

    @staticmethod
    def _is_invalid_user(exc: Exception) -> bool:
        reason = getattr(exc, "reason", None)
        try:
            return int(reason) == 1008
        except (TypeError, ValueError):
            return False

    def _wait_for_interrupt(self, generation: int, timeout: Optional[float]) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self._stop_event.is_set() and not self._generation_changed(generation):
            self._wake_event.clear()
            if self._stop_event.is_set() or self._generation_changed(generation):
                return
            if deadline is None:
                self._wake_event.wait()
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._wake_event.wait(timeout=remaining)

    def _publish(self, status: WebBridgeStatus) -> None:
        with self._lifecycle_lock:
            self._status = status
            callback = self._status_callback
        if callback is not None:
            self._invoke_status_callback(callback, status)

    @staticmethod
    def _invoke_status_callback(callback: StatusCallback, status: WebBridgeStatus) -> None:
        try:
            callback(status)
        except Exception:
            logger.exception("OpenGolfSim Web status callback failed")
