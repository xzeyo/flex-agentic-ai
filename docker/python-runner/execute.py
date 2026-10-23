"""Trusted in-container entry point: fixed commands, bounded output, writable tmpfs only."""
import os
import shutil
import signal
import subprocess
import sys

PROFILES = {
    "lint": ["ruff", "check", "--isolated", "--no-cache", "."],
    "test": ["python", "-m", "pytest", "-c", "/runner/pytest.ini", "-q", "-p", "no:cacheprovider", "tests"],
}


def main():
    argv = PROFILES.get(sys.argv[1] if len(sys.argv) == 2 else "")
    if argv is None:
        return 126
    shutil.copytree("/input", "/workspace", dirs_exist_ok=True)
    process = subprocess.Popen(argv, cwd="/workspace", stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    remaining = 63_000
    assert process.stdout
    while chunk := process.stdout.read1(4096):
        sys.stdout.buffer.write(chunk[:remaining])
        sys.stdout.buffer.flush()
        remaining -= len(chunk)
        if remaining <= 0:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            print("\nOutput limit exceeded.")
            return 125
    return process.wait()


if __name__ == "__main__":
    sys.exit(main())
