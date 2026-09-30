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


def test_handoff_emits_webhook_with_history_and_masks_contacts():
    from app.dialogue import Bot
    events = []
    b = Bot(notifier=events.append)
    b.reply("h1", "kontak saya budi@mail.com 081234567890")
    b.reply("h1", "panggil admin dong")
    assert events and events[-1]["event"] == "handoff" and events[-1]["conversation_id"] == "h1"
    blob = str(events[-1]["history"])
    assert "budi@mail.com" not in blob and "081234567890" not in blob and "<email>" in blob


def test_customer_messages_forwarded_while_agent_owns_chat():
    from app.dialogue import Bot
    events = []
    b = Bot(notifier=events.append)
    b.set_mode("c", "AGENT")
    out = b.reply("c", "kok belum dibalas?")
    assert out["silent"] is True and events[-1]["event"] == "customer_message" and events[-1]["text"] == "kok belum dibalas?"


def test_notifier_failure_never_breaks_reply():
    from app.dialogue import Bot
    def boom(e): raise RuntimeError("panel mati")
    assert Bot(notifier=boom).reply("x", "panggil admin dong")["handoff"] is True


def test_signature_matches_hmac():
    import hmac, hashlib
    from app.notify import sign
    assert sign("k", b"{}") == "sha256=" + hmac.new(b"k", b"{}", hashlib.sha256).hexdigest()


def test_admin_conversation_endpoints(monkeypatch, tmp_path):
    H = {"Authorization": "Bearer t"}
    c = TestClient(load_app(monkeypatch, tmp_path, ADMIN_TOKEN="t").app)
    c.post("/reply", json={"conversation_id": "z9", "message": "panggil admin dong"})
    assert c.get("/conversations").status_code == 401
    items = c.get("/conversations", headers=H).json()["items"]
    assert [i["conversation_id"] for i in items] == ["z9"]
    assert c.get("/conversations/z9", headers=H).json()["history"][0]["role"] == "user"
    assert c.get("/conversations/tidakada", headers=H).status_code == 404
    c.post("/conversations/z9/mode", json={"mode": "AI"}, headers=H)          # admin selesai
    assert c.get("/conversations", headers=H).json()["items"] == []
