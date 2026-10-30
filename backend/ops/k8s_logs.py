import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from django.core import signing
from rest_framework.exceptions import APIException, ValidationError


PAGE_BYTES = 512 * 1024
SNAPSHOT_TTL = 15 * 60
SNAPSHOT_ROOT = Path(tempfile.gettempdir()) / 'sxdevops-k8s-logs'
SNAPSHOT_SLOTS = threading.BoundedSemaphore(3)
CURSOR_SALT = 'ops.k8s.pod-logs.v1'


class LogSnapshotError(APIException):
    status_code = 503
    default_detail = '日志暂不可用，请稍后重试。'


def _cleanup_snapshots():
    SNAPSHOT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    deadline = time.time() - SNAPSHOT_TTL
    for path in SNAPSHOT_ROOT.glob('*.log'):
        try:
            if path.stat().st_mtime < deadline:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _cursor(snapshot_id, offset, scope, tail=False):
    return signing.dumps({'snapshot': snapshot_id, 'offset': offset, 'scope': scope, 'tail': tail}, salt=CURSOR_SALT, compress=True)


def _open_cursor(cursor, scope):
    try:
        payload = signing.loads(cursor, salt=CURSOR_SALT, max_age=SNAPSHOT_TTL)
        if payload['scope'] != scope or not re.fullmatch('[a-f0-9]{32}', payload['snapshot']):
            raise ValueError
        offset = int(payload['offset'])
        path = SNAPSHOT_ROOT / f"{payload['snapshot']}.log"
        if offset < 0 or offset > path.stat().st_size:
            raise ValueError
        return payload['snapshot'], offset, path, bool(payload.get('tail'))
    except (signing.BadSignature, KeyError, TypeError, ValueError, OSError):
        error = LogSnapshotError('日志会话已过期或不属于当前用户和容器，请刷新日志。')
        error.status_code = 410
        raise error


def _snapshot(loader):
    if not SNAPSHOT_SLOTS.acquire(blocking=False):
        raise LogSnapshotError('日志采集繁忙，请稍后重试。')
    snapshot_id = uuid.uuid4().hex
    path = SNAPSHOT_ROOT / f'{snapshot_id}.log'
    response = None
    try:
        _cleanup_snapshots()
        started = time.monotonic()
        written = 0
        disk_check = 0
        response = loader()
        with path.open('xb') as output:
            os.chmod(path, 0o600)
            for chunk in response.stream(amt=64 * 1024):
                if time.monotonic() - started > 60:
                    raise LogSnapshotError('日志采集超时，请刷新重试。')
                if written >= disk_check:
                    if shutil.disk_usage(SNAPSHOT_ROOT).free < 128 * 1024 * 1024:
                        raise LogSnapshotError('日志临时空间不足，请稍后重试。')
                    disk_check = written + 8 * 1024 * 1024
                output.write(chunk)
                written += len(chunk)
        return snapshot_id, path
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        if response is not None:
            response.close()
            response.release_conn()
        SNAPSHOT_SLOTS.release()


def _read_page(path, offset, direction, page_size):
    size = path.stat().st_size
    with path.open('rb') as source:
        if direction == 'newer':
            start = offset
            source.seek(start)
            data = source.read(PAGE_BYTES)
            pieces = data.splitlines(keepends=True)
            if start + len(data) < size and len(pieces) > 1 and not pieces[-1].endswith(b'\n'):
                pieces.pop()
            data = b''.join(pieces[:page_size])
            while data and start + len(data) < size:
                source.seek(start + len(data))
                following = source.read(1)
                if not following or following[0] & 0xc0 != 0x80:
                    break
                data = data[:-1]
            end = start + len(data)
        else:
            end = size if direction == 'latest' else offset
            start = max(0, end - PAGE_BYTES)
            source.seek(start)
            data = source.read(end - start)
            if start:
                first_break = data.find(b'\n')
                if 0 <= first_break < len(data) - 1:
                    start += first_break + 1
                    data = data[first_break + 1:]
                else:
                    while data and data[0] & 0xc0 == 0x80:
                        start += 1
                        data = data[1:]
            data = b''.join(data.splitlines(keepends=True)[-page_size:])
            start = end - len(data)
    return start, end, data.decode('utf-8', errors='replace'), size


def _find_anchor(path, anchor):
    buffer = b''
    offset = 0
    with path.open('rb') as source:
        while chunk := source.read(64 * 1024):
            buffer += chunk
            position = buffer.find(anchor)
            if position >= 0:
                return offset + position
            retained = max(0, len(anchor) - 1)
            discard = max(0, len(buffer) - retained)
            buffer = buffer[discard:]
            offset += discard
    error = LogSnapshotError('容器日志已轮转或容器已重启，请刷新日志后继续浏览。')
    error.status_code = 409
    raise error


def pod_log_page(params, scope, loader):
    direction = params.get('direction', 'latest')
    if direction not in {'latest', 'older', 'newer'}:
        raise ValidationError('无效的日志翻页方向。')
    try:
        page_size = int(params.get('page_size', 500))
    except (TypeError, ValueError):
        raise ValidationError('日志每页行数必须是整数。')
    if not 1 <= page_size <= 1000:
        raise ValidationError('日志每页行数需在 1 到 1000 之间。')
    cursor = params.get('cursor')
    if cursor:
        snapshot_id, offset, path, tail = _open_cursor(cursor, scope)
        if tail and direction == 'older' and offset == 0:
            with path.open('rb') as source:
                anchor = source.read(64 * 1024)
            snapshot_id, path = _snapshot(lambda: loader(None))
            try:
                offset = _find_anchor(path, anchor)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            tail = False
    else:
        snapshot_id, path = _snapshot(lambda: loader(500))
        offset = path.stat().st_size
        with path.open('rb') as source:
            line_count = 0
            final_byte = b''
            while chunk := source.read(64 * 1024):
                line_count += chunk.count(b'\n')
                final_byte = chunk[-1:]
            if final_byte and final_byte != b'\n':
                line_count += 1
            tail = line_count >= 500
        direction = 'latest'
    start, end, content, size = _read_page(path, offset, direction, page_size)
    return {
        'logs': content,
        'before': _cursor(snapshot_id, start, scope, tail) if start or tail else None,
        'after': _cursor(snapshot_id, end, scope, tail) if end < size else None,
        'snapshot': _cursor(snapshot_id, 0, scope, tail),
        'has_older': start > 0 or tail,
        'has_newer': end < size,
        'bytes': size,
    }
