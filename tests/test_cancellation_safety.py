from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from gui.pdf_toolkit_dialog import CmdWorker
from modules.archive_extract import ExtractionPlan, run_extraction

_QT_APP = None


def _app():
    # Keep a strong Python reference to QApplication; otherwise its C++ object
    # may be destroyed while the worker test is still running.
    global _QT_APP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if _QT_APP is None:
        _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_cmd_worker_cancel_stops_long_process():
    app = _app()
    worker = CmdWorker([sys.executable, "-c", "import time; time.sleep(30)"], timeout=60)
    cancelled = []
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.start()
    time.sleep(0.2)
    worker.cancel()
    deadline = time.monotonic() + 5
    while worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.05)
    worker.wait(1000)
    app.processEvents()
    assert not worker.isRunning()
    assert cancelled == [True]


def test_archive_cancel_keeps_archive_and_cleans_partial(tmp_path: Path):
    archive = tmp_path / "sample.zip"
    archive.write_bytes(b"placeholder")
    target = tmp_path / "sample"
    target.mkdir()
    (target / "partial.bin").write_bytes(b"partial")

    # The command itself is intentionally long-running; cancellation must
    # terminate it and preserve the source archive.
    import threading

    cancel = threading.Event()
    cancel.set()
    plan = ExtractionPlan(
        archive=archive,
        target_dir=target,
        tool="test",
        cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
        skip_existing=False,
    )
    result = run_extraction(plan, delete_on_success=True, timeout=60, cancel_event=cancel)
    assert result.cancelled is True
    assert result.success is False
    assert archive.exists()
    assert not target.exists()
