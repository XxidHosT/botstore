"""Tag produk: menyaring dari data toko dan jujur bila tag tak ada di katalog."""
from app.dialogue import Bot
from tools.evaluate import flat


def ask(m): return flat(Bot().reply("t", m))


def test_relaxed_games_come_from_tags():
    out = ask("rekomendasi game santai")
    assert "Stardew" in out and "Minecraft" in out and "Elden" not in out


def test_two_players_maps_to_multiplayer_tag():
    out = ask("game buat main berdua")
    assert "Stardew" in out and "Elden" not in out


def test_tag_missing_from_catalog_is_admitted_not_faked():
    out = ask("game horor ada?")
    assert "horor" in out and "Belum ada" in out


def test_tag_with_budget_shows_closest_when_nothing_fits():
    out = ask("game rpg di bawah 400rb")
    assert "bertag" in out and "Elden" in out                   # Elden Ring rpg tapi Rp459.000; Cyberpunk habis


def test_tag_words_are_not_treated_as_unknown_product():
    assert Bot().reply("t", "game open world")["action"] != "not_found"


def test_indonesian_stays_indonesian():
    assert "Berdasarkan tag" in ask("game santai ada apa aja")
