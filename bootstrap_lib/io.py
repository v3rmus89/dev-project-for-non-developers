import atexit
import contextlib
import os
import signal
from pathlib import Path

TMP_SUFFIX = ".bootstrap-tmp"
_pending_tmp = set()
_handlers_installed = False


def _cleanup_pending(*_args):
    for tmp in list(_pending_tmp):
        with contextlib.suppress(OSError):
            os.remove(tmp)
        _pending_tmp.discard(tmp)


def install_signal_handlers():
    global _handlers_installed
    if _handlers_installed:
        return

    def _handler(signum, _frame):
        _cleanup_pending()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    atexit.register(_cleanup_pending)
    _handlers_installed = True


def atomic_write(target_path, content_bytes):
    target = Path(target_path)
    tmp = Path(str(target) + TMP_SUFFIX)
    target.parent.mkdir(parents=True, exist_ok=True)
    _pending_tmp.add(str(tmp))
    try:
        with open(tmp, "wb") as f:
            f.write(content_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, target)
    finally:
        _pending_tmp.discard(str(tmp))


def cleanup_tmp_artifacts(root):
    root = Path(root)
    if not root.exists():
        return
    for p in root.rglob("*" + TMP_SUFFIX):
        with contextlib.suppress(OSError):
            p.unlink()
