import json
import logging
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

from app.schemas import TERMINAL, TRANSITIONS, RunRequest, State, now

logger = logging.getLogger("team.events")


class Store:
    """Small local store. Each operation uses its own connection; mutations are serialized."""

    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "runs.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, task TEXT NOT NULL, state TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    cancelled INTEGER NOT NULL DEFAULT 0, iteration INTEGER NOT NULL DEFAULT 0,
                    review_iteration INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '',
                    report TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL, kind TEXT NOT NULL, stage TEXT NOT NULL,
                    message TEXT NOT NULL, data TEXT NOT NULL);
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def create(self, request: RunRequest) -> dict:
        run_id = str(uuid4())
        timestamp = now()
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO runs(id,task,state,created_at,updated_at) VALUES(?,?,?,?,?)",
                       (run_id, request.task, State.QUEUED, timestamp, timestamp))
        self.event(run_id, "run.created", "Task accepted")
        return self.get(run_id)

    def get(self, run_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        result = dict(row)
        result["cancelled"] = bool(result["cancelled"])
        result["report"] = json.loads(result["report"])
        return result

    def recent(self, limit: int = 50) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id,task,state,created_at,updated_at,cancelled,iteration,review_iteration,summary FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        # Dashboard polling must not repeatedly transfer every historical execution log.
        return [{**dict(row), "cancelled": bool(row["cancelled"]), "report": {}} for row in rows]

    def update(self, run_id: str, **fields) -> None:
        allowed = {"iteration", "review_iteration", "summary", "report"}
        if not fields.keys() <= allowed:
            raise ValueError("Invalid update fields")
        if "report" in fields:
            fields["report"] = json.dumps(fields["report"])
        fields["updated_at"] = now()
        with self.lock, self.connect() as db:
            db.execute(f"UPDATE runs SET {','.join(f'{k}=?' for k in fields)} WHERE id=?",
                       (*fields.values(), run_id))

    def transition(self, run_id: str, target: State) -> None:
        with self.lock, self.connect() as db:
            current = State(self.get(run_id)["state"])
            if current in TERMINAL or (
                target not in {State.FAILED, State.CANCELLED, State.TIMED_OUT}
                and target not in TRANSITIONS.get(current, set())
            ):
                raise ValueError(f"Invalid state transition: {current} -> {target}")
            db.execute("UPDATE runs SET state=?,updated_at=? WHERE id=?", (target, now(), run_id))
        self.event(run_id, "stage.started", target.value)

    def cancel(self, run_id: str) -> dict:
        requested = False
        with self.lock, self.connect() as db:
            if State(self.get(run_id)["state"]) not in TERMINAL:
                db.execute("UPDATE runs SET cancelled=1,updated_at=? WHERE id=?", (now(), run_id))
                requested = True
        if requested:
            self.event(run_id, "run.cancel_requested", "Cancellation requested")
            if self.get(run_id)["state"] == State.QUEUED:
                self.transition(run_id, State.CANCELLED)
                self.update(run_id, summary="Cancelled before execution.")
        return self.get(run_id)

    def event(self, run_id: str, kind: str, message: str, **data) -> None:
        stage = self.get(run_id)["state"]
        timestamp = now()
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO events(run_id,timestamp,kind,stage,message,data) VALUES(?,?,?,?,?,?)",
                       (run_id, timestamp, kind, stage, message[:2000], json.dumps(data)))
        logger.info(json.dumps({"run_id": run_id, "stage": stage, "event": kind, "message": message}))

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        self.get(run_id)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 1000",
                              (run_id, after)).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def recover(self) -> None:
        with self.connect() as db:
            rows = db.execute("SELECT id,state FROM runs").fetchall()
        for row in rows:
            if State(row["state"]) not in TERMINAL:
                self.update(row["id"], summary="Interrupted by server restart; submit a new run.")
                self.transition(row["id"], State.FAILED)
                self.event(row["id"], "run.failed", "Recovered interrupted run after restart")
