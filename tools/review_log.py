"""Bahan belajar dari log percakapan.   python -m tools.review_log [--log data/log.jsonl] [--top 30] [--min-count 1]

Mengelompokkan pesan yang membuat bot ragu/gagal (miss/clarify/not_found), menebak intent terdekat, dan
mencetak kerangka YAML untuk ditempel ke data/knowledge.yaml (lalu POST /admin/reload).
TIDAK mengubah file apa pun: manusia yang memutuskan contoh mana yang layak masuk (agar data tak teracuni)."""
import argparse, collections, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.kb import KB, DATA
from app.nlu import IntentClassifier, normalize

WEAK = {"miss1", "miss2", "miss3", "clarify", "not_found"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=str(DATA / "log.jsonl"))
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--min-count", type=int, default=1)
    a = ap.parse_args(argv)
    path = pathlib.Path(a.log)
    if not path.exists():
        print(f"Belum ada log di {path}"); return 1
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not recs:
        print("Log kosong."); return 1

    acts = collections.Counter(r.get("action") for r in recs)
    weak_n = sum(acts[k] for k in WEAK)
    print(f"{len(recs)} pesan | dijawab langsung: {100 * (len(recs) - weak_n - acts['handoff'] - acts['miss3']) / len(recs):.0f}% "
          f"| ragu/gagal: {100 * weak_n / len(recs):.0f}% | eskalasi ke admin: {acts['handoff'] + acts['handoff_order'] + acts['miss3']}")

    kb = KB(); clf = IntentClassifier(kb.intents)
    groups = collections.Counter(normalize(r["text"]) for r in recs if r.get("action") in WEAK and r.get("text"))
    print(f"\nPesan yang paling sering membuat bot ragu (maks {a.top}):")
    by_intent = collections.defaultdict(list)
    for text, n in groups.most_common(a.top):
        if n < a.min_count: continue
        ranked = clf.classify(text)
        guess = ", ".join(f"{i} {s:.2f}" for i, s in ranked[:2]) or "-"
        print(f"  {n:3}x  {text[:60]!r:64} tebakan: {guess}")
        if ranked: by_intent[ranked[0][0]].append(text)
    if by_intent:
        print("\nKerangka untuk knowledge.yaml (periksa dulu; hapus yang salah tebak):")
        for intent, texts in by_intent.items():
            print(f"  # intents.{intent}.examples.id  <-  [{', '.join(texts)}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
