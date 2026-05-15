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
    renamed = False
    try:
        with open(tmp, "wb") as f:
            f.write(content_bytes)
            f.flush()
            os.fsync(f.fileno())
        # os.replace (not os.rename) so cross-platform overwrite works
        # (Codex iter-23 P2#2): on Windows os.rename fails when target
        # exists, breaking --overwrite-existing on every collided file.
        os.replace(tmp, target)
        renamed = True
    finally:
        _pending_tmp.discard(str(tmp))
        # If the rename didn't happen (write/fsync/replace raised), the
        # orphan .bootstrap-tmp must be removed here — the atexit/signal
        # cleanup can no longer see it once it's discarded from
        # _pending_tmp. Closes Codex iter-23 P2#1.
        if not renamed:
            with contextlib.suppress(OSError):
                os.remove(tmp)


def cleanup_tmp_artifacts(root):
    root = Path(root)
    if not root.exists():
        return
    for p in root.rglob("*" + TMP_SUFFIX):
        with contextlib.suppress(OSError):
            p.unlink()
