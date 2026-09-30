"""Dasbor review: pengelompokan pesan gagal, pelabelan aman, pembatalan, dan bot benar-benar belajar."""
import json, shutil
from fastapi.testclient import TestClient
import app.kb as kbm, app.dialogue as d, app.review as review
from tests.test_production import load_app

H = {"Authorization": "Bearer t"}


def setup(monkeypatch, tmp_path):
    shutil.copytree(kbm.DATA, tmp_path / "data", ignore=shutil.ignore_patterns("log.jsonl*", "state.db*", "learned.json"))
    for m in (kbm, d, review): monkeypatch.setattr(m, "DATA", tmp_path / "data")
    return TestClient(load_app(monkeypatch, tmp_path, ADMIN_TOKEN="t").app)


def log(tmp_path, rows):
    (tmp_path / "data" / "log.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_api_and_page_protection(monkeypatch, tmp_path):
    c = setup(monkeypatch, tmp_path)
    assert c.get("/admin/api/review").status_code == 401
    assert c.post("/admin/api/review/label", json={"text": "x", "intent": "refund"}).status_code == 401
    page = c.get("/admin/review")
    assert page.status_code == 200 and "default-src 'self'" in page.headers["content-security-policy"]
    assert "<script>" not in page.text                       # skrip di berkas terpisah, jadi CSP tanpa unsafe-inline


def test_groups_weak_messages_and_hides_labeled(monkeypatch, tmp_path):
    c = setup(monkeypatch, tmp_path)
    log(tmp_path, [{"ts": 1, "text": "duit balik dong", "action": "miss1", "lang": "id"}, {"ts": 2, "text": "Duit balik dong!", "action": "clarify", "lang": "id"},
                   {"ts": 3, "text": "halo", "action": "answer"}, {"ts": 4, "text": "hubungi <email>", "action": "miss1"}])
    ov = c.get("/admin/api/review", headers=H).json()
    top = ov["items"][0]
    assert top["count"] == 2 and "duit balik" in top["text"].lower() and ov["stats"]["messages"] == 4
    assert any(i["masked"] for i in ov["items"])
    assert c.post("/admin/api/review/label", json={"text": "hubungi <email>", "intent": "refund"}, headers=H).status_code == 400   # data pribadi
    assert c.post("/admin/api/review/label", json={"text": top["text"], "intent": "bukan_intent"}, headers=H).status_code == 400
    assert c.post("/admin/api/review/label", json={"text": "duit balik dong", "intent": "refund"}, headers=H).status_code == 200
    assert all("duit balik" not in i["text"].lower() for i in c.get("/admin/api/review", headers=H).json()["items"])


def test_bot_learns_from_label_and_undo_restores(monkeypatch, tmp_path):
    c = setup(monkeypatch, tmp_path)
    ask = lambda cid: c.post("/reply", json={"conversation_id": cid, "message": "kembaliin duit gw dong"}).json()
    assert ask("a")["intent"] != "refund"
    r = c.post("/admin/api/review/label", json={"text": "kembaliin duit gw dong", "intent": "refund"}, headers=H).json()
    assert ask("b")["intent"] == "refund"                     # dipakai langsung tanpa /admin/reload
    c.post("/admin/api/learned/remove", json=r, headers=H)
    assert ask("c")["intent"] != "refund"
    assert c.post("/admin/api/learned/remove", json=r, headers=H).status_code == 400


def test_dismiss_hides_message(monkeypatch, tmp_path):
    c = setup(monkeypatch, tmp_path)
    log(tmp_path, [{"ts": 1, "text": "asdf qwer", "action": "miss1"}])
    assert len(c.get("/admin/api/review", headers=H).json()["items"]) == 1
    c.post("/admin/api/review/dismiss", json={"text": "asdf qwer"}, headers=H)
    assert c.get("/admin/api/review", headers=H).json()["items"] == []
