import difflib
import hashlib
import json
import shutil
from pathlib import Path

from app.schemas import Artifact, Implementation, safe_path


class Artifacts:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.source = root / "source"
        self.source.mkdir(exist_ok=True)

    def write(self, name: str, value) -> None:
        safe_path(name)
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
        encoded = content.encode()
        if len(encoded) > 2_000_000:
            raise ValueError("Artifact size limit exceeded")
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_bytes(encoded)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def candidate(self, implementation: Implementation) -> str:
        # Only application-owned directories are removed. Container source is always read-only.
        if self.source.is_symlink() or self.source.resolve().parent != self.root.resolve():
            raise ValueError("Unsafe source directory")
        shutil.rmtree(self.source)
        self.source.mkdir()
        patch = ""
        for item in implementation.files:
            target = self.source / item.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item.content, encoding="utf-8", newline="")
            patch += "".join(difflib.unified_diff([], item.content.splitlines(keepends=True),
                                               fromfile="/dev/null", tofile=f"b/{item.path}"))
            if item.content and not item.content.endswith("\n"):
                patch += "\n\\ No newline at end of file\n"
        self.write("changes.patch", patch)
        return patch

    def manifest(self) -> list[dict]:
        result = []
        total = 0
        for path in sorted(self.root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlinks are forbidden in artifacts")
            if not path.is_file() or path.name == "manifest.json":
                continue
            data = path.read_bytes()
            total += len(data)
            if total > 20_000_000:
                raise ValueError("Run artifact quota exceeded")
            result.append(Artifact(path=path.relative_to(self.root).as_posix(), size=len(data),
                                   sha256=hashlib.sha256(data).hexdigest()).model_dump())
        self.write("manifest.json", result)
        return result

    def read(self, name: str) -> bytes:
        safe_path(name)
        path = self.root / name
        if not path.resolve().is_relative_to(self.root.resolve()) or path.is_symlink():
            raise ValueError("Unsafe artifact")
        if path.stat().st_size > 2_000_000:
            raise ValueError("Artifact too large")
        return path.read_bytes()
