"""Run a blocking function on a worker QThread, keeping the GUI responsive.

`TaskRunner.run(fn, on_done, on_error)` executes ``fn(progress_cb)`` off the GUI
thread; ``progress_cb(done, total)`` is re-emitted on the GUI thread via the
`progress` signal, and `on_done(result)` / `on_error(msg)` fire on the GUI thread
when it finishes. One task at a time (a busy runner refuses new work, returns
False). `AsyncComputeMixin` lets a panel run its compute through an injected
runner, falling back to synchronous compute when none is set (tests / headless).
"""
from __future__ import annotations

from PyQt5 import QtCore


class _FnWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            result = self._fn(lambda d, t: self.progress.emit(int(d), int(t)))
        except Exception as exc:                       # surface, don't crash the app
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


class TaskRunner(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = self._worker = None
        self._on_done = self._on_error = None

    @property
    def busy(self):
        return self._thread is not None and self._thread.isRunning()

    def run(self, fn, on_done, on_error=None):
        if self.busy:
            return False
        self._on_done, self._on_error = on_done, on_error
        self._thread = QtCore.QThread(self)
        self._worker = _FnWorker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.done.connect(self._done)
        self._worker.failed.connect(self._fail)
        self._thread.start()
        return True

    def _cleanup(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = self._worker = None

    def _done(self, result):
        cb = self._on_done
        self._cleanup()
        if cb:
            cb(result)

    def _fail(self, msg):
        cb = self._on_error
        self._cleanup()
        if cb:
            cb(msg)


class AsyncComputeMixin:
    """Mix into a panel to run its heavy compute off-thread when a host window
    injects ``run_async``; otherwise compute synchronously (back-compat)."""
    run_async = None        # set by the window to win.run_task(label, work, apply)

    def _dispatch(self, label, work, apply):
        """work(progress_cb) -> result (heavy, off-thread); apply(result) -> UI."""
        if self.run_async:
            self.run_async(label, work, apply)
        else:
            apply(work(None))
