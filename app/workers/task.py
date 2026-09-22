from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class TaskThread(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(object)

    def __init__(self, action, with_progress=False):
        super().__init__()
        self.action = action
        self.with_progress = with_progress

    def run(self):
        try:
            result = self.action(self.progress.emit) if self.with_progress else self.action()
            self.completed.emit(result)
        except Exception as exc:
            from core.ai.service import friendly_error
            self.failed.emit(friendly_error(exc))


def start(action, completed, failed, progress=None):
    thread = TaskThread(action, with_progress=progress is not None)
    thread.completed.connect(completed)
    thread.failed.connect(failed)
    if progress is not None:
        thread.progress.connect(progress)
    thread.start()
    return thread
