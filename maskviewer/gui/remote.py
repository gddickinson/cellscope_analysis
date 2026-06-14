"""Optional HTTP remote-control so an agent can drive the GUI headless.

Enable by setting ``MASKVIEWER_REMOTE=<port>`` before launching:

    MASKVIEWER_REMOTE=8765 python main_viewer.py

Then drive it over HTTP (localhost only), e.g.::

    curl 'http://127.0.0.1:8765/state'
    curl 'http://127.0.0.1:8765/set?recording=0&frame=5&color_by=area'
    curl 'http://127.0.0.1:8765/cmd?action=compute_population'
    curl 'http://127.0.0.1:8765/screenshot?path=/tmp/v.png&what=window'

Commands run on the GUI thread (queued + drained by a QTimer) so Qt stays happy.
Off by default — purely for automated testing / agent workflows.
"""
from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PyQt5 import QtCore


class RemoteControl(QtCore.QObject):
    def __init__(self, window, port):
        super().__init__(window)
        self.win = window
        self._q = queue.Queue()
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(50)
        self._server = ThreadingHTTPServer(("127.0.0.1", int(port)),
                                           self._make_handler())
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    # run a callable on the GUI thread, block for its result
    def call(self, fn):
        box, done = {}, threading.Event()
        self._q.put((fn, box, done))
        done.wait(timeout=60)
        return box.get("result"), box.get("error")

    def _drain(self):
        while not self._q.empty():
            fn, box, done = self._q.get()
            try:
                box["result"] = fn()
            except Exception as exc:                    # report, don't crash
                box["error"] = f"{type(exc).__name__}: {exc}"
            done.set()

    def _dispatch(self, path, q):
        w = self.win
        if path == "/set":
            return w.remote_set(q)
        if path == "/cmd":
            return w.remote_cmd(q)
        if path == "/screenshot":
            return w.remote_screenshot(q.get("path", "/tmp/maskviewer.png"),
                                       q.get("what", "window"))
        if path == "/state":
            return w.remote_state()
        return {"endpoints": ["/state", "/set", "/cmd", "/screenshot"]}

    def _make_handler(self):
        rc = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urlparse(self.path)
                params = {k: v[0] for k, v in parse_qs(u.query).items()}
                result, error = rc.call(lambda: rc._dispatch(u.path, params))
                self.send_response(500 if error else 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(
                    {"ok": error is None, "result": result, "error": error}
                ).encode())

        return Handler
