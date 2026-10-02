"""Testy międzyprocesowej blokady plikowej."""
from __future__ import annotations

import subprocess
import sys

import pytest

from services.locking import LockBusyError, acquire_lock


_TRY_SCRIPT = """
import sys
from services.locking import LockBusyError, acquire_lock
try:
    with acquire_lock(name=sys.argv[1], directory=sys.argv[2]):
        pass
except LockBusyError:
    raise SystemExit(2)
raise SystemExit(0)
"""
_HOLD_SCRIPT = """
import sys, time
from services.locking import acquire_lock
with acquire_lock(name=sys.argv[1], directory=sys.argv[2]):
    print('READY', flush=True)
    time.sleep(30)
"""


def _try_lock(tmp_path, name='sync'):
    return subprocess.run([sys.executable, '-c', _TRY_SCRIPT, name, str(tmp_path)],
                          capture_output=True, text=True, timeout=10)


def test_other_process_cannot_acquire_held_lock(tmp_path):
    with acquire_lock(name='sync', directory=tmp_path):
        result = _try_lock(tmp_path)
    assert result.returncode == 2


def test_other_process_acquires_after_lock_is_released(tmp_path):
    with acquire_lock(name='sync', directory=tmp_path):
        assert _try_lock(tmp_path).returncode == 2
    assert _try_lock(tmp_path).returncode == 0


def test_killing_holder_releases_system_lock(tmp_path):
    process = subprocess.Popen([sys.executable, '-c', _HOLD_SCRIPT, 'sync', str(tmp_path)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == 'READY'
        process.kill()
        process.wait(timeout=10)
        assert _try_lock(tmp_path).returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_exception_inside_context_releases_lock(tmp_path):
    with pytest.raises(RuntimeError, match='test'):
        with acquire_lock(name='sync', directory=tmp_path):
            raise RuntimeError('test')
    assert _try_lock(tmp_path).returncode == 0


def test_different_lock_names_do_not_collide(tmp_path):
    with acquire_lock(name='sync', directory=tmp_path):
        assert _try_lock(tmp_path, 'extract').returncode == 0
