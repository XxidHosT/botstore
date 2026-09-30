"""Dasbor "belajar dari log": pesan yang bot ragu/gagal dipahami -> staf memilih intent yang benar -> jadi contoh latih.
Contoh disimpan di data/learned.json (BUKAN knowledge.yaml): terpisah, mudah dilihat, dan bisa dibatalkan satu per satu.
Bot memuat ulang otomatis lewat KB.stamp(), jadi berlaku di semua worker tanpa /admin/reload."""
import collections, fcntl, json, os, pathlib, tempfile
from .kb import DATA
from .nlu import normalize

WEAK = {"miss1", "miss2", "miss3", "clarify", "not_found"}
MAX_LEN = 200


class ReviewError(ValueError):
    pass


def _read(path, default):
    try: return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default


def _write(path, data):
    path = pathlib.Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)                                     # atomik: pembaca tak pernah melihat berkas setengah tertulis


class _Lock:
    def __enter__(self):
        self.f = open(DATA / ".review.lock", "w"); fcntl.flock(self.f, fcntl.LOCK_EX); return self
    def __exit__(self, *a): fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()


def _records():
    recs = []
    for name in ("log.jsonl.1", "log.jsonl"):
        p = DATA / name
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try: recs.append(json.loads(line))
                except ValueError: pass
    return recs


def overview(clf, min_count=1, limit=100):
    recs = _records()
    acts = collections.Counter(r.get("action") for r in recs)
    dismissed = set(_read(DATA / "review_dismissed.json", []))
    learned = {normalize(t) for per in _read(DATA / "learned.json", {}).values() for exs in per.values() for t in exs}
    groups = {}
    for r in recs:
        if r.get("action") not in WEAK or not r.get("text"): continue
        key = normalize(r["text"])
        if not key or key in dismissed or key in learned: continue
        g = groups.setdefault(key, {"text": r["text"], "count": 0, "actions": collections.Counter(), "lang": r.get("lang") or "id", "last_ts": 0})
        g["count"] += 1; g["actions"][r.get("action")] += 1; g["last_ts"] = max(g["last_ts"], r.get("ts") or 0)
    items = []
    for key, g in sorted(groups.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["last_ts"])):
        if g["count"] < min_count or len(items) >= limit: continue
        guess = [{"intent": i, "score": round(s, 2)} for i, s in clf.classify(key)[:3]]
        items.append({**g, "actions": dict(g["actions"]), "guess": guess, "masked": "<email>" in g["text"] or "<telp>" in g["text"]})
    n = len(recs)
    weak = sum(acts[k] for k in WEAK)
    stats = {"messages": n, "weak": weak, "weak_pct": round(100 * weak / n) if n else 0,
             "handoffs": acts["handoff"] + acts["handoff_order"] + acts["miss3"], "waiting_review": len(groups)}
    return {"stats": stats, "items": items}


def label(kb, text, intent):
    text = " ".join(str(text).split())
    if not text or len(text) > MAX_LEN: raise ReviewError("teks kosong atau terlalu panjang")
    if "<email>" in text or "<telp>" in text: raise ReviewError("pesan berisi data pribadi yang dimasker; jangan dijadikan contoh")
    if intent not in kb.intents: raise ReviewError(f"intent tidak dikenal: {intent}")
    from .nlu import detect_lang
    lang = detect_lang(text, "id")
    with _Lock():
        data = _read(DATA / "learned.json", {})
        exs = data.setdefault(intent, {}).setdefault(lang, [])
        if text not in exs: exs.append(text)
        _write(DATA / "learned.json", data)
    return {"intent": intent, "lang": lang, "text": text}


def dismiss(text):
    with _Lock():
        d = _read(DATA / "review_dismissed.json", [])
        key = normalize(text)
        if key and key not in d: d.append(key)
        _write(DATA / "review_dismissed.json", d)


def learned():
    return [{"intent": i, "lang": lang, "text": t} for i, per in _read(DATA / "learned.json", {}).items() for lang, exs in per.items() for t in exs]


def remove(intent, lang, text):
    with _Lock():
        data = _read(DATA / "learned.json", {})
        exs = data.get(intent, {}).get(lang, [])
        if text not in exs: raise ReviewError("contoh tidak ditemukan")
        exs.remove(text)
        _write(DATA / "learned.json", data)
