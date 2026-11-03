"""Bounded, privacy-conscious media anomaly logs; never part of motor control.

Only the validated schema below can reach disk. This deliberately does not accept
URLs, headers, arbitrary error messages, configuration, or raw user-agent strings.
Normal playback is not logged. Logging failure must never fail a playback action.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Collection
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


FRONTEND_BUILD = 'recovery-diagnostics-20261102'
MAX_LOG_BYTES = 1024 * 1024
BACKUP_COUNT = 4
KEY_COOLDOWN_SECONDS = 10.0
MAX_RATE_KEYS = 1024
MAX_RECORDS_PER_MINUTE = 60

Seconds = Annotated[float, Field(ge=0, le=31_536_000, allow_inf_nan=False)]
Counter = Annotated[int, Field(ge=0, le=9_007_199_254_740_991)]
SessionId = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$', max_length=32)]
PageId = Annotated[str, Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', max_length=36)]
PointId = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,48}$', max_length=48)]
Version = Annotated[str, Field(pattern=r'^\d{1,6}(?:\.\d{1,6}){0,3}$', max_length=27)]


class MediaDiagnosticEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    event: Literal['media_error', 'play_rejected', 'stalled', 'recovered', 'retry_requested']
    pageId: PageId | Literal['server']
    sessionId: SessionId | None = None
    revision: Counter | None = None
    pointId: PointId | None = None
    pageMode: Literal['embedded', 'standalone', 'server'] = 'standalone'
    visibility: Literal['visible', 'hidden'] | None = None
    frontendBuild: Literal['recovery-diagnostics-20261102'] = FRONTEND_BUILD
    browserFamily: Literal['Edge', 'Chrome', 'WebView2', 'Other'] = 'Other'
    browserVersion: Version | None = None
    errorCode: Annotated[int, Field(ge=0, le=4)] | None = None
    exceptionName: Literal['AbortError', 'NotAllowedError', 'NotSupportedError',
                           'InvalidStateError', 'SecurityError', 'NetworkError',
                           'UnknownError'] | None = None
    readyState: Annotated[int, Field(ge=0, le=4)] | None = None
    networkState: Annotated[int, Field(ge=0, le=3)] | None = None
    currentTime: Seconds | None = None
    duration: Seconds | None = None
    bufferedSeconds: Seconds | None = None
    stalledSeconds: Seconds | None = None
    totalFrames: Counter | None = None
    droppedFrames: Counter | None = None
    paused: bool | None = None
    ended: bool | None = None
    seeking: bool | None = None
    muted: bool | None = None
    volume: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    playbackState: Literal['idle', 'loading', 'showing', 'playing', 'paused',
                           'stopped', 'ended', 'error'] | None = None


class _QuietRotatingHandler(RotatingFileHandler):
    """RotatingFileHandler normally prints internal IO errors to stderr."""
    write_succeeded = False

    def emit(self, record: logging.LogRecord) -> None:
        self.write_succeeded = True
        super().emit(record)

    def handleError(self, record: logging.LogRecord) -> None:
        self.write_succeeded = False


class MediaDiagnostics:
    """One instance per application runtime; safe for concurrent request threads.

    ``allowed_point_ids`` is the server configuration's point-id set. Unknown
    values are replaced with None, so client-supplied free text cannot be saved
    as a point name. client_id is used only in memory for limiting, never logged.
    The entire log set is at most 5 MiB (1 current + 4 rotated files).
    """
    def __init__(self, root: Path, *, clock=time.monotonic) -> None:
        self.path = Path(root) / 'logs' / 'media-errors.jsonl'
        self._clock = clock
        self._lock = threading.Lock()
        self._handler: _QuietRotatingHandler | None = None
        self._recent: OrderedDict[tuple[str, str, str | None, str], float] = OrderedDict()
        self._window: deque[float] = deque()

    def record(self, event: MediaDiagnosticEvent, *, client_id: str = 'local',
               allowed_point_ids: Collection[str] = ()) -> bool:
        try:
            # Revalidate even model_construct()/mutated objects; serialize only
            # model fields, never the caller's dictionary or request headers.
            checked = MediaDiagnosticEvent.model_validate(event.model_dump())
            data = checked.model_dump(exclude_none=True)
            if checked.pointId not in allowed_point_ids:
                data.pop('pointId', None)
            data['schema'] = 'rail.media-anomaly/v1'
            data['at'] = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
            line = json.dumps(data, ensure_ascii=True, separators=(',', ':'))
            if len(line) > 4096:
                return False
            with self._lock:
                now = self._clock()
                key = (str(client_id)[:128], checked.pageId, checked.sessionId, checked.event)
                while self._window and now - self._window[0] >= 60:
                    self._window.popleft()
                previous = self._recent.get(key)
                if previous is not None and now - previous < KEY_COOLDOWN_SECONDS:
                    return False
                if len(self._window) >= MAX_RECORDS_PER_MINUTE:
                    return False
                self._recent[key] = now
                self._recent.move_to_end(key)
                while len(self._recent) > MAX_RATE_KEYS:
                    self._recent.popitem(last=False)
                self._window.append(now)
                if self._handler is None:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self._handler = _QuietRotatingHandler(
                        self.path, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT,
                        encoding='utf-8', delay=True)
                    self._handler.setFormatter(logging.Formatter('%(message)s'))
                record = logging.LogRecord('rail.media-diagnostics', logging.WARNING,
                                           '', 0, line, (), None)
                self._handler.handle(record)
                return self._handler.write_succeeded
        except Exception:
            # Includes validation, read-only disks, permissions, rotations, and
            # handler initialization. An observer must not break the exhibit.
            return False

    def close(self) -> None:
        with self._lock:
            if self._handler is not None:
                self._handler.close()
                self._handler = None
