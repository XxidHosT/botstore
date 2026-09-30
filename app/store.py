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

    def list_handoffs(self, limit=100):
        """Percakapan yang sedang dipegang/menunggu admin, terbaru dulu. Cukup untuk skala kecil; pakai indeks/kolom sendiri bila besar."""
        with self._conn() as c:
            rows = c.execute("SELECT cid, data, ts FROM state ORDER BY ts DESC").fetchall()
        out = []
        for cid, data, ts in rows:
            s = json.loads(data)
            if s.get("handoff") and s.get("mode") == "AGENT":
                out.append({"conversation_id": cid, "ts": ts, "lang": s.get("lang"), "last": (s.get("history") or [{}])[-1].get("text", "")})
                if len(out) >= limit: break
        return out
