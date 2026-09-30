"""Pengamanan produksi: autentikasi admin, rate limit per IP, state persisten, rotasi log."""
import importlib, sys
import pytest
from fastapi.testclient import TestClient


def load_app(monkeypatch, tmp_path, **env):
    for k, v in {"STATE_DB": str(tmp_path / "s.db"), "ADMIN_TOKEN": "", "IP_RATE_PER_MIN": "60", **env}.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main")


def test_admin_disabled_without_token(monkeypatch, tmp_path):
    c = TestClient(load_app(monkeypatch, tmp_path).app)
    assert c.post("/admin/reload").status_code == 503


def test_admin_requires_bearer_token(monkeypatch, tmp_path):
    c = TestClient(load_app(monkeypatch, tmp_path, ADMIN_TOKEN="s3cret").app)
    assert c.post("/admin/reload").status_code == 401
    assert c.post("/admin/reload", headers={"Authorization": "Bearer salah"}).status_code == 401
    assert c.post("/admin/reload", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.post("/conversations/x/mode", json={"mode": "AGENT"}).status_code == 401


def test_public_reply_needs_no_token(monkeypatch, tmp_path):
    c = TestClient(load_app(monkeypatch, tmp_path).app)
    assert c.post("/reply", json={"conversation_id": "a", "message": "harga minecraft"}).status_code == 200


def test_ip_rate_limit_cannot_be_dodged_with_new_conversation_ids(monkeypatch, tmp_path):
    c = TestClient(load_app(monkeypatch, tmp_path, IP_RATE_PER_MIN="3").app)
    codes = [c.post("/reply", json={"conversation_id": f"id{i}", "message": "halo"}).status_code for i in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]


def test_state_and_agent_mode_survive_restart(monkeypatch, tmp_path):
    m = load_app(monkeypatch, tmp_path, ADMIN_TOKEN="t")
    c = TestClient(m.app)
    c.post("/reply", json={"conversation_id": "p", "message": "harganya berapa"})            # bot menunggu slot produk
    m2 = load_app(monkeypatch, tmp_path, ADMIN_TOKEN="t")                                   # "restart": proses baru, DB sama
    out = TestClient(m2.app).post("/reply", json={"conversation_id": "p", "message": "elden ring"}).json()
    assert "459.000" in str(out)                                                             # konteks slot terbawa
    TestClient(m2.app).post("/conversations/p/mode", json={"mode": "AGENT"}, headers={"Authorization": "Bearer t"})
    m3 = load_app(monkeypatch, tmp_path, ADMIN_TOKEN="t")
    assert TestClient(m3.app).post("/reply", json={"conversation_id": "p", "message": "halo"}).json()["silent"] is True


def test_log_is_rotated(monkeypatch, tmp_path):
    import app.dialogue as d
    monkeypatch.setattr(d, "DATA", tmp_path); monkeypatch.setattr(d, "LOG_MAX", 200)
    b = d.Bot()
    for i in range(10): b.reply(f"l{i}", "halo")
    assert (tmp_path / "log.jsonl.1").exists()
