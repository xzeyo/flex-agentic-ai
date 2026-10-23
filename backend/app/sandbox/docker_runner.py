import io
import tarfile
import time
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import docker
from docker.types import LogConfig, Mount, Ulimit
from requests.exceptions import RequestException

from app.config import Settings
from app.errors import SandboxError
from app.sandbox.policy import command
from app.schemas import MAX_LOG_BYTES, MAX_SOURCE_BYTES, CheckResult, SourceFile


class DockerRunner:
    def __init__(self, settings: Settings, run_id: str):
        self.settings = settings
        self.run_id = run_id
        self.cleanup_errors: list[str] = []
        _ = self.settings.instance_id

    @staticmethod
    def owner(settings: Settings) -> str:
        return settings.instance_id

    def restrictions(self) -> dict:
        return dict(
            user="10001:10001", network_mode="none", privileged=False,
            cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            read_only=True, mem_limit="256m", memswap_limit="256m", nano_cpus=1_000_000_000,
            pids_limit=64, ulimits=[Ulimit(name="nofile", soft=128, hard=128),
                                   Ulimit(name="fsize", soft=8_388_608, hard=8_388_608)],
            tmpfs={"/workspace": "rw,nosuid,nodev,size=32m,uid=10001,gid=10001,mode=0700",
                   "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=10001,gid=10001,mode=0700"},
            environment={"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1",
                         "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONUNBUFFERED": "1"},
            labels={"four-agent.run_id": self.run_id, "four-agent.owner": self.owner(self.settings)},
            log_config=LogConfig(type="json-file", config={"max-size": "128k", "max-file": "1"}),
            working_dir="/workspace", detach=True,
        )

    @staticmethod
    def archive(source: Path) -> bytes:
        stream = io.BytesIO()
        total = 0
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for path in sorted(source.rglob("*")):
                if path.is_symlink():
                    raise SandboxError("Source symlinks are forbidden")
                if not path.is_file():
                    continue
                data = path.read_bytes()
                relative = path.relative_to(source).as_posix()
                SourceFile(path=relative, content=data.decode())
                total += len(data)
                if total > MAX_SOURCE_BYTES:
                    raise SandboxError("Source quota exceeded")
                info = tarfile.TarInfo(relative)
                info.size, info.mode, info.uid, info.gid = len(data), 0o444, 10001, 10001
                archive.addfile(info, io.BytesIO(data))
        return stream.getvalue()

    def run(self, source: Path, profile: str, abort) -> CheckResult:
        argv = command(profile)  # Reject unknown profiles before contacting Docker.
        archive = self.archive(source)
        client = None
        volume = None
        containers = []
        started = time.monotonic()
        try:
            abort()
            client = docker.from_env(timeout=15)
            client.ping()
            image = client.images.get(self.settings.runner_image)  # Never pull an agent image.
            assert image.id is not None
            volume = client.volumes.create(name=f"team-{self.run_id}-{uuid4().hex[:8]}",
                                           labels={"four-agent.run_id": self.run_id,
                                                   "four-agent.owner": self.owner(self.settings)})
            # A trusted idle container receives validated files. It never executes submitted code.
            staging = client.containers.create(
                image.id, command=["python", "-I", "-c", "import time; time.sleep(120)"],
                mounts=[Mount(target="/input", source=volume.name, type="volume")],
                **self.restrictions(),
            )
            containers.append(staging)
            staging.start()
            abort()
            if not staging.put_archive("/input", archive):
                raise SandboxError("Could not stage validated source")
            staging.remove(force=True)
            containers.remove(staging)
            container = client.containers.create(
                image.id, command=argv,
                mounts=[Mount(target="/input", source=volume.name, type="volume", read_only=True)],
                **self.restrictions(),
            )
            containers.append(container)
            abort()
            container.start()
            timed_out = False
            while True:
                abort()
                container.reload()
                if container.status in {"exited", "dead"}:
                    break
                if time.monotonic() - started > self.settings.check_timeout:
                    timed_out = True
                    container.kill()
                    container.reload()
                    break
                time.sleep(0.1)
            raw = container.logs(stdout=True, stderr=True)
            state = container.attrs.get("State", {})
            exit_code = state.get("ExitCode")
            return CheckResult(
                profile=cast(Literal["lint", "test"], profile), exit_code=exit_code,
                duration_seconds=round(time.monotonic() - started, 3),
                output=raw[:MAX_LOG_BYTES].decode("utf-8", errors="replace"),
                timed_out=timed_out, output_limited=len(raw) > MAX_LOG_BYTES or exit_code == 125,
                oom_killed=state.get("OOMKilled", False),
            )
        except (docker.errors.DockerException, RequestException, OSError) as exc:
            raise SandboxError("Docker execution unavailable. Start Docker Desktop and build the configured runner image.") from exc
        finally:
            for container in reversed(containers):
                try:
                    container.remove(force=True)
                except Exception:
                    self.cleanup_errors.append("Container removal failed; operator cleanup required.")
            if volume is not None:
                try:
                    volume.remove(force=True)
                except Exception:
                    self.cleanup_errors.append("Input volume removal failed; operator cleanup required.")
            if client is not None:
                try:
                    client.close()
                except Exception:
                    self.cleanup_errors.append("Docker client close failed.")

    @staticmethod
    def recover(settings: Settings) -> None:
        """Remove only this application's abandoned resources before accepting new runs."""
        client = docker.from_env(timeout=15)
        try:
            filters: dict[str, str | list[str] | bool] = {
                "label": f"four-agent.owner={DockerRunner.owner(settings)}"
            }
            for container in client.containers.list(all=True, filters=filters):
                container.remove(force=True)
            for volume in client.volumes.list(filters=filters):
                volume.remove(force=True)
        finally:
            client.close()
