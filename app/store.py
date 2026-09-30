"""Penyimpanan state percakapan di SQLite (WAL): selamat dari restart dan aman untuk beberapa worker uvicorn.
Ganti dengan Redis bila trafik besar; antarmukanya cukup get/put."""
import json, sqlite3, time, pathlib


class StateStore:
    def __init__(self, path, ttl=7 * 24 * 3600):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path, self.ttl = str(path), ttl
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("CREATE TABLE IF NOT EXISTS state (cid TEXT PRIMARY KEY, data TEXT NOT NULL, ts INTEGER NOT NULL)")

    def _conn(self):
        return sqlite3.connect(self.path, timeout=5)

    def get(self, cid):
        with self._conn() as c:
            row = c.execute("SELECT data, ts FROM state WHERE cid=?", (cid,)).fetchone()
        if not row or time.time() - row[1] > self.ttl:
            return None
        s = json.loads(row[0])
        if s.get("last_facets") is not None: s["last_facets"] = set(s["last_facets"])
        return s

    def put(self, cid, s):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO state (cid, data, ts) VALUES (?, ?, ?)", (cid, json.dumps(s, default=sorted), int(time.time())))
            c.execute("DELETE FROM state WHERE ts < ?", (int(time.time()) - self.ttl,))
