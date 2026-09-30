"""Regresi untuk pesan nyata yang dulu gagal: jumlah/total, produk tak dikenal, rentang harga, gratis, minta admin."""
import re
from app.dialogue import Bot
from app.entities import extract
from tools.evaluate import flat


def run(turns, cid="s"):
    b, out = Bot(), None
    for t in turns: out = b.reply(cid, t)
    return out


def test_quantity_total_is_computed_from_catalog_price():
    assert "Rp718.000" in flat(run(["kalo beli 2 minecraft berapa"]))
    assert "Rp1.377.000" in flat(run(["harga elden ring x3"]))
    txt = flat(run(["2 elden ring dan 1 minecraft totalnya berapa"]))
    assert "Rp918.000" in txt and "Total: Rp1.277.000" in txt


def test_total_follows_previous_products():
    out = run(["berapa harga minecraft dan elden ring", "totalnya berapa?"])
    assert "Total: Rp818.000" in flat(out)


def test_total_without_context_does_not_claim_missing_product():
    assert run(["totalnya berapa?"])["action"] != "not_found"


def test_quantity_above_stock_is_flagged():
    assert "hanya 7" in flat(run(["harga 10 minecraft"]))


def test_unknown_product_is_reported_not_guessed():
    for m in ["gta 5 ada?", "fifa 24", "free fire diamond ada?"]:
        o = run([m])
        assert o["action"] == "not_found", m
        assert not re.search(r"GTA|FIFA", flat(o), re.I)


def test_gibberish_still_uses_fallback_ladder():
    assert run(["asdfgh"])["action"] == "miss1"


def test_price_range_without_product_word():
    o = run(["diatas 100rb tapi di bawah 200rb"])
    assert o["action"] == "search" and "Steam Wallet" in flat(o) and "Minecraft" not in flat(o)


def test_free_request_is_answered_honestly():
    o = run(["game gratis ada?"])
    assert "berbayar" in flat(o) and o["action"] == "search"
    assert "berbayar" not in flat(run(["gratis ongkir ga"]))


def test_where_is_admin_escalates_but_late_delivery_does_not():
    assert run(["MANA ADMIN"])["handoff"] is True
    assert run(["admin nya mana lama banget"])["handoff"] is True
    assert run(["kok lama banget belum dikirim"])["intent"] != "human"
