"""Katalog jarak jauh (website jualgame): perilaku bot terhadap /api/bot/products.
Server tiruan meniru kontrak endpoint (auth token, kata AND lalu OR, genre, jenis, harga, urutan, varian per grup)."""
import json, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from app.dialogue import Bot
from app.remote_kb import derive_aliases, CatalogUnavailable
from tools.evaluate import flat

TOKEN = "t" * 32
G = lambda **k: dict(id=k["id"], name=k["name"], priceIdr=k["price"], variants=k.get("variants", 1), inStock=k.get("qty", 5) > 0, qty=k.get("qty", 5),
                     metacritic=k.get("mc"), genres=k.get("genres", []), platforms=["Steam"], url=f"/games/grup/{k['id']}", type=k.get("type", "GAME"))
CATALOG = [
    G(id="elden-ring", name="Elden Ring", price=459000, variants=2, qty=17, mc=96, genres=["Action", "RPG", "Open World"]),
    G(id="cyberpunk-2077", name="Cyberpunk 2077", price=299000, qty=0, mc=86, genres=["Action", "RPG"]),
    G(id="stardew-valley", name="Stardew Valley", price=89000, qty=25, mc=89, genres=["Simulation", "Indie", "Casual"]),
    G(id="minecraft", name="Minecraft Java & Bedrock", price=359000, qty=7, mc=93, genres=["Sandbox", "Survival"]),
    G(id="resident-evil-village", name="Resident Evil Village", price=219000, qty=40, mc=84, genres=["Action", "Horror"]),
    G(id="brand-steam-wallet", name="Steam Wallet", price=105000, qty=80, genres=["Prepaid"], type="GIFTCARD"),
]


class Stub(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a): pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        Stub.calls.append(q)
        if self.headers.get("X-Bot-Token") != TOKEN:
            self.send_response(401); self.end_headers(); return
        first = lambda k: (q.get(k) or [None])[0]
        toks = [t for t in (first("q") or "").lower().split() if t]
        items = [p for p in CATALOG if (first("all") == "1" or p["inStock"])]
        if first("type"): items = [p for p in items if p["type"] == first("type")]
        if first("maxPrice"): items = [p for p in items if p["priceIdr"] <= int(first("maxPrice"))]
        if first("minPrice"): items = [p for p in items if p["priceIdr"] >= int(first("minPrice"))]
        for grp in q.get("genre", []):
            want = [g.lower() for g in grp.split("|")]
            items = [p for p in items if any(w in g.lower() for w in want for g in p["genres"])]
        if toks:
            strict = [p for p in items if all(t in p["name"].lower() for t in toks)]
            items = strict or [p for p in items if any(t in p["name"].lower() for t in toks)]
        sort = first("sort") or "best"
        items = sorted(items, key={"cheap": lambda p: p["priceIdr"], "pricey": lambda p: -p["priceIdr"]}.get(sort, lambda p: (-(p["metacritic"] or -1), p["priceIdr"])))
        body = json.dumps({"success": True, "data": {"hadHit": bool(items) and bool(toks), "total": len(items), "items": items[: int(first("limit") or 10)]}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)


@pytest.fixture
def remote(monkeypatch):
    Stub.calls = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("CATALOG_URL", f"http://127.0.0.1:{srv.server_port}"); monkeypatch.setenv("CATALOG_TOKEN", TOKEN)
    monkeypatch.setenv("SITE_URL", "https://jualgame.id")
    yield srv
    srv.shutdown()


def ask(*turns):
    b, out = Bot(), None
    for t in turns: out = b.reply("r", t)
    return out


def test_aliases_are_name_prefixes():
    assert derive_aliases("Minecraft Java & Bedrock Edition PC") == ["minecraft", "minecraft java", "minecraft java bedrock", "minecraft java bedrock edition"]
    assert derive_aliases("Elden Ring (Steam Key) Global")[-1] == "elden ring"


def test_price_uses_from_wording_for_multi_variant_games(remote):
    out = ask("harga elden ring berapa")
    assert "mulai Rp459.000" in flat(out) and "https://jualgame.id/games/grup/elden-ring" in str(out)


def test_out_of_stock_product_is_named_not_replaced_by_previous_one(remote):
    out = ask("harga elden ring", "stok cyberpunk ada?")
    txt = " ".join(b["text"] for b in out["blocks"] if b["type"] == "text")
    assert "Cyberpunk 2077 sedang habis" in txt
    alt_cards = [i["name"] for b in out["blocks"] if b["type"] == "products" for i in b["items"]][1:]
    assert alt_cards and "Cyberpunk 2077" not in alt_cards      # alternatif ada, dan bukan produk yang habis itu sendiri


def test_unknown_product_is_not_found_even_with_slang_that_looks_like_no(remote):
    for m in ["ada zelda gak", "zelda ada?"]:
        out = ask("harga elden ring", m)
        assert out["action"] == "not_found", m


def test_genre_tags_map_to_catalog_genres(remote):
    assert "Resident Evil" in flat(ask("game horor ada?"))
    santai = flat(ask("game santai apa yang bagus"))
    assert "Stardew" in santai and "Elden" not in santai


def test_voucher_uses_product_type_not_a_tag(remote):
    out = flat(ask("voucher steam di bawah 110rb"))
    assert "Steam Wallet" in out and "Elden" not in out


def test_compare_reports_metacritic_not_fake_stars(remote):
    txt = flat(ask("minecraft vs stardew valley"))
    assert "skor Metacritic 93" in txt and "skor Metacritic 89" in txt and "rating 4.6" not in txt


def test_total_with_quantity_marks_from_price(remote):
    txt = flat(ask("harga elden ring dan minecraft, totalnya berapa"))
    assert "Total mulai dari Rp818.000" in txt
    assert "mulai Rp918.000" in flat(ask("beli 2 elden ring totalnya berapa"))


def test_wrong_token_or_dead_site_does_not_crash_the_chat(remote, monkeypatch):
    monkeypatch.setenv("CATALOG_TOKEN", "salah")
    out = ask("harga elden ring berapa")
    assert out["action"] == "error" and out["blocks"][0]["type"] == "text"
    monkeypatch.setenv("CATALOG_URL", "http://127.0.0.1:9")
    assert ask("harga elden ring berapa")["action"] == "error"


def test_catalog_error_is_typed():
    from app.remote_kb import RemoteKB
    with pytest.raises(CatalogUnavailable):
        RemoteKB("http://127.0.0.1:9", "x")._get(q="a")


def test_token_is_sent_and_only_needed_fields_are_requested(remote):
    ask("harga elden ring berapa")
    assert Stub.calls and all("q" in c or "genre" in c or "sort" in c for c in Stub.calls)


def test_unknown_name_never_falls_back_to_previous_product(remote):
    """Regresi nyata: 'stok zelda' tepat sesudah membahas Elden Ring dijawab dengan stok Elden Ring."""
    out = ask("harga elden ring", "stok zelda")
    assert out["action"] == "not_found"
    assert "Elden Ring" not in flat(out).split("|")[0]        # kalimat jawabannya bukan tentang Elden Ring
    assert "tersedia (stok" not in flat(out)
