import argparse
import asyncio
import json
from uuid import UUID

from app.config import Settings
from app.schemas import RunRequest
from app.service import RunService
from app.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="Four Agent Engineering Team")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Execute a task and print its final report")
    run.add_argument("task")
    status = sub.add_parser("status", help="Read a persisted run")
    status.add_argument("run_id", type=UUID)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "status":
        print(json.dumps(Store(settings.root).get(str(args.run_id)), indent=2))
        return

    async def execute():
        service = RunService(settings)
        try:
            await service.start()
        except RuntimeError as exc:
            parser.error(str(exc))
        try:
            created = service.submit(RunRequest(task=args.task))
            print(f"Run: {created['id']}", flush=True)
            await service.queue.join()
            result = service.store.get(created["id"])
            print(json.dumps(result, indent=2))
            return 0 if result["state"] == "SUCCEEDED" else 1
        finally:
            await service.close()

    raise SystemExit(asyncio.run(execute()))


if __name__ == "__main__":
    main()
