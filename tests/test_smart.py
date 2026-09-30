"""Tes kemampuan baru: set held-out A & B sebagai regresi, entitas, dan invarian keamanan data."""
import re
import pytest
from app.dialogue import Bot
from app.entities import extract
from tools.evaluate import judge, flat
from tests import heldout, heldout_b

ALL = heldout.CASES + heldout_b.CASES


def run(turns, cid="t"):
    b, out = Bot(), None
    for t in turns: out = b.reply(cid, t)
    return out


@pytest.mark.parametrize("name,turns,exp", ALL, ids=[c[0] for c in ALL])
def test_behaviour(name, turns, exp):
    out = run(turns)
    assert not judge(out, exp), f"{turns} -> {judge(out, exp)} :: {flat(out)}"


@pytest.mark.parametrize("msg,mx,mn,sort,order", [
    ("game di bawah 150 ribu", 150_000, None, "best", None),
    ("under 100k games", 100_000, None, "best", None),
    ("harga 100.000 ke bawah", 100_000, None, "best", None),
    ("di atas Rp 200.000", None, 200_000, None, None),
    ("yang termurah dong", None, None, "cheap", None),
    ("saldo steam 100rb", None, None, None, None),          # angka tanpa pembanding = nama produk, bukan anggaran
    ("steam wallet 100", None, None, None, None),
    ("800 robux", None, None, None, None),
    ("order #55231 kok belum sampai", None, None, None, "55231"),
    ("INV-48213", None, None, None, "INV-48213"),
    ("thunder 100k", None, None, None, None),               # 'under' di dalam kata lain bukan pembanding
])
def test_entities(msg, mx, mn, sort, order):
    e = extract(msg)
    assert (e.max_price, e.min_price, e.sort, e.order_id) == (mx, mn, sort, order)


def test_every_number_comes_from_data():
    """Invarian inti: harga yang muncul di balasan hanya harga katalog atau angka yang diketik pengguna."""
    b0 = Bot()
    allowed = {p["price"] for p in b0.kb.products}
    msgs = [t for c in ALL for t in c[1]]
    for c in ALL:
        for m in c[1]:
            e = extract(m)
            allowed |= {e.max_price, e.min_price} - {None}
    for _, turns, _ in ALL:
        out = run(turns)
        for n in re.findall(r"Rp([\d.]+)", flat(out)):
            assert int(n.replace(".", "")) in allowed, (turns, n)
    assert msgs


def test_order_number_is_never_verified_only_forwarded():
    b = Bot()
    out = b.reply("o", "INV-99001 mana pesanan saya")
    assert out["handoff"] is True
    assert "belum bisa mengecek" in flat(out)              # jujur: tidak mengarang status
    assert b.reply("o", "halo")["silent"] is True           # setelah oper, bot diam


def test_social_words_do_not_hijack_price_question():
    for m in ["halo min, harga minecraft berapa", "makasih ya, stok stardew ada?", "ok deh, elden ring berapa"]:
        assert re.search(r"Rp|tersedia|habis", flat(Bot().reply("s", m))), m


def test_ack_and_deny_are_not_noise_intents():
    assert Bot().reply("a", "ok")["intent"] == "ack"
    assert Bot().reply("a", "stok")["intent"] == "stock"    # 'ok' tidak lagi 'nyangkut' ke kata 'stok'


def test_asking_if_bot_is_human_does_not_escalate():
    for m in ["are you a real person", "kamu bot ya?", "ini manusia atau bukan"]:
        o = Bot().reply("h", m)
        assert o["handoff"] is False and o["intent"] == "bot_identity", m


def test_partial_product_name_is_not_a_product():
    """'steam key' hanyalah potongan nama 'Cyberpunk 2077 (Steam Key)'; jangan dikira produk itu."""
    out = Bot().reply("p", "cheapest steam key")
    assert "Cyberpunk" not in flat(out)


def test_unknown_terms_are_disclosed_not_ignored():
    out = flat(Bot().reply("u", "rekomendasi game horor"))
    assert "horor" in out and "genre" in out


def test_out_of_stock_offers_available_alternatives_only():
    b = Bot()
    out = b.reply("x", "stok cyberpunk")
    cards = [i for blk in out["blocks"] if blk["type"] == "products" for i in blk["items"]]
    alts = [c for c in cards if "Cyberpunk" not in c["name"]]
    assert alts and all(c["stock"] > 0 for c in alts)


def test_review_log_tool(tmp_path, capsys):
    import json
    from tools import review_log
    log = tmp_path / "log.jsonl"
    rows = [{"text": "asdf qwer", "action": "miss1"}, {"text": "asdf qwer", "action": "miss2"}, {"text": "halo", "action": "answer"}]
    log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert review_log.main(["--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "2x" in out and "asdf qwer" in out
