import os
import sys
from pathlib import Path
from typing import BinaryIO


class ControllerLock:
    """OS-released exclusive lease: a second controller cannot recover a live controller's runs."""

    def __init__(self, root: Path):
        self.root = root
        self.stream: BinaryIO | None = None

    def acquire(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        stream = (self.root / "controller.lock").open("a+b")
        try:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise RuntimeError("Cannot acquire TEAM_DATA_DIR controller lock. Stop the other API/CLI controller or select a different data directory.") from exc
        self.stream = stream

    def release(self) -> None:
        if self.stream is not None:
            self.stream.close()  # Closing the handle releases the OS lock, including after a crash.
            self.stream = None
