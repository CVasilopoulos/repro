import asyncio
import json
import os
import sqlite3
import threading
import time
import uuid

SCHEMA = """
create table if not exists jobs (
  id text primary key,
  issue_url text not null,
  status text not null,
  verdict text,
  created real not null,
  finished real,
  client text,
  summary text
);
create table if not exists events (
  job_id text not null,
  seq integer not null,
  ts real not null,
  kind text not null,
  data text not null,
  primary key (job_id, seq)
);
create table if not exists usage (
  day text primary key,
  tokens integer not null
);
"""


class Store:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("pragma journal_mode=wal")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.subscribers: dict[str, list[asyncio.Queue]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def create_job(self, issue_url: str, client: str) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self.lock:
            self.db.execute(
                "insert into jobs (id, issue_url, status, created, client) values (?, ?, 'queued', ?, ?)",
                (job_id, issue_url, time.time(), client),
            )
        return job_id

    def update_job(self, job_id: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.lock:
            self.db.execute(f"update jobs set {cols} where id = ?", (*fields.values(), job_id))

    def job(self, job_id: str) -> dict | None:
        cur = self.db.execute("select id, issue_url, status, verdict, created, finished, summary from jobs where id = ?", (job_id,))
        row = cur.fetchone()
        if not row:
            return None
        keys = ["id", "issue_url", "status", "verdict", "created", "finished", "summary"]
        return dict(zip(keys, row))

    def recent_jobs(self, limit: int = 20) -> list[dict]:
        cur = self.db.execute(
            "select id, issue_url, status, verdict, created, finished from jobs order by created desc limit ?", (limit,)
        )
        keys = ["id", "issue_url", "status", "verdict", "created", "finished"]
        return [dict(zip(keys, r)) for r in cur.fetchall()]

    def jobs_from_client_since(self, client: str, since: float) -> int:
        cur = self.db.execute("select count(*) from jobs where client = ? and created > ?", (client, since))
        return cur.fetchone()[0]

    def emit(self, job_id: str, kind: str, **data) -> dict:
        with self.lock:
            cur = self.db.execute("select coalesce(max(seq), 0) + 1 from events where job_id = ?", (job_id,))
            seq = cur.fetchone()[0]
            event = {"seq": seq, "ts": time.time(), "kind": kind, "data": data}
            self.db.execute(
                "insert into events (job_id, seq, ts, kind, data) values (?, ?, ?, ?, ?)",
                (job_id, seq, event["ts"], kind, json.dumps(data)),
            )
        for queue in list(self.subscribers.get(job_id, [])):
            if self.loop:
                self.loop.call_soon_threadsafe(queue.put_nowait, event)
        return event

    def events(self, job_id: str, after: int = 0) -> list[dict]:
        cur = self.db.execute(
            "select seq, ts, kind, data from events where job_id = ? and seq > ? order by seq", (job_id, after)
        )
        return [{"seq": s, "ts": t, "kind": k, "data": json.loads(d)} for s, t, k, d in cur.fetchall()]

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self.subscribers.setdefault(job_id, []).append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        subs = self.subscribers.get(job_id, [])
        if queue in subs:
            subs.remove(queue)

    def add_tokens(self, tokens: int) -> int:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self.lock:
            self.db.execute(
                "insert into usage (day, tokens) values (?, ?) on conflict(day) do update set tokens = tokens + excluded.tokens",
                (day, tokens),
            )
            return self.db.execute("select tokens from usage where day = ?", (day,)).fetchone()[0]

    def tokens_today(self) -> int:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        row = self.db.execute("select tokens from usage where day = ?", (day,)).fetchone()
        return row[0] if row else 0
