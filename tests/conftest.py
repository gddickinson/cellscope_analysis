"""Shared test teardown: destroy the app's Qt windows/panels a test created, inside that test.

Many GUI tests build parentless windows and panels (ViewerWindow, CellInfoPanel, the
Comparison window ...) and never close them. Python then garbage-collects them at an
arbitrary later moment, often while a *later* test is processing Qt events, and tearing
down their pyqtgraph plots in that state can abort the interpreter ("libc++abi: Pure
virtual function called!"). This autouse fixture makes the destruction deterministic:
after each test it stops their worker threads, closes every top-level widget defined by
this project (``maskviewer.*`` classes), flushes pending events and runs the garbage
collector, so the Python owners destroy them at the end of the test that made them. (Calling
deleteLater() from here instead, or deleting pyqtgraph's own parentless helper menus, makes
Qt delete C++ objects pyqtgraph still uses and crashes in LabelItem.resizeEvent.)
"""
import gc
import sys

import pytest


@pytest.fixture(autouse=True)
def _destroy_qt_widgets():
    yield
    QtWidgets = sys.modules.get("PyQt5.QtWidgets")
    app = QtWidgets.QApplication.instance() if QtWidgets else None
    if app is None:
        return
    from PyQt5 import QtCore
    ours = [w for w in QtWidgets.QApplication.topLevelWidgets()
            if type(w).__module__.startswith("maskviewer.")]
    for w in ours:
        for th in w.findChildren(QtCore.QThread):
            if th.isRunning():
                th.quit()
                th.wait(10000)
        w.close()
    ours = w = None
    app.processEvents()
    gc.collect()                    # the Python owners destroy the closed widgets now
    app.processEvents()
