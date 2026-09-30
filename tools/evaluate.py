"""Ukur kualitas otak pada set held-out.   python -m tools.evaluate [-v]

Keluaran: skor total + daftar kasus yang gagal (beserta balasan sebenarnya)."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.dialogue import Bot
import importlib


def flat(out):
    parts = []
    for b in out["blocks"]:
        if b["type"] == "text": parts.append(b["text"])
        elif b["type"] == "products": parts += [f'{i["name"]} {i["price"]} stok{i["stock"]}' for i in b["items"]]
        elif b["type"] == "quick_replies": parts += ["[" + x + "]" for x in b["items"]]
    return " | ".join(parts)


def judge(out, exp):
    why, txt = [], flat(out)
    def oneof(v): return v if isinstance(v, tuple) else (v,)
    if "intent" in exp and out["intent"] not in oneof(exp["intent"]): why.append(f'intent={out["intent"]}')
    if "action" in exp and out["action"] not in oneof(exp["action"]): why.append(f'action={out["action"]}')
    if "handoff" in exp and out["handoff"] != exp["handoff"]: why.append(f'handoff={out["handoff"]}')
    for s in exp.get("has", []):
        if s.lower() not in txt.lower(): why.append(f'tak ada "{s}"')
    only_text = " ".join(b["text"] for b in out["blocks"] if b["type"] == "text")
    for s in exp.get("no_text", []):
        if s.lower() in only_text.lower(): why.append(f'teks memuat "{s}"')
    for s in exp.get("no", []):
        if s.lower() in txt.lower(): why.append(f'ada "{s}"')
    return why


def run(verbose=False, module="tests.heldout"):
    CASES = importlib.import_module(module).CASES
    ok, bad = 0, []
    for name, turns, exp in CASES:
        b = Bot(); out = None
        for t in turns: out = b.reply("e", t)
        why = judge(out, exp)
        if why: bad.append((name, turns, why, out))
        else: ok += 1
    print(f"SKOR: {ok}/{len(CASES)} ({100*ok/len(CASES):.0f}%)")
    for name, turns, why, out in bad:
        print(f"  GAGAL {name}: {turns} -> {'; '.join(why)}")
        if verbose: print(f"        balasan: {out['intent']}/{out['confidence']}/{out['action']} {flat(out)[:160]}")
    return ok, len(CASES)


if __name__ == "__main__":
    mod = next((a for a in sys.argv[1:] if not a.startswith("-")), "tests.heldout")
    run("-v" in sys.argv, mod)
