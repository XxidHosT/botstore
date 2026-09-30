"""Webhook keluar ke panel admin: handoff baru dan pesan pelanggan selama admin mengambil alih.
Best-effort dan tidak pernah memblokir atau menggagalkan balasan ke pelanggan. Payload ditandatangani HMAC-SHA256
(header X-Signature: sha256=<hex>) supaya panelmu bisa memastikan asalnya dari bot."""
import hashlib, hmac, json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

_pool = ThreadPoolExecutor(max_workers=2)


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(url, secret, body, tries=3):
    headers = {"Content-Type": "application/json", "X-Signature": sign(secret, body)} if secret else {"Content-Type": "application/json"}
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status < 300: return True
        except Exception:
            pass
        time.sleep(0.5 * 2 ** i)
    return False


def _clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def discord_payload(event: dict, link_tpl: str = "", role_id: str = ""):
    """Pesan Discord untuk event handoff (None untuk event lain, agar channel tidak banjir). Tidak pernah memicu @everyone/@here:
    allowed_mentions dikosongkan, kecuali role yang sengaja diminta lewat DISCORD_MENTION_ROLE_ID."""
    if event.get("event") != "handoff": return None
    hist = event.get("history") or []
    lines = [f"**{'Pelanggan' if h.get('role') == 'user' else 'Bot'}:** {_clip(h.get('text', ''), 200)}" for h in hist[-6:]]
    cid = event.get("conversation_id", "?")
    fields = [{"name": "Percakapan", "value": _clip(f"`{cid}`", 1000), "inline": True},
              {"name": "Alasan", "value": _clip(f"{event.get('reason')} / {event.get('intent')}", 1000), "inline": True}]
    embed = {"title": "Pelanggan butuh admin", "description": _clip("\n".join(lines) or "(tanpa riwayat)", 3500), "color": 0xE67E22, "fields": fields}
    if link_tpl: embed["url"] = link_tpl.replace("{id}", str(cid))
    body = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    if role_id.isdigit():
        body["content"] = f"<@&{role_id}> handoff baru"
        body["allowed_mentions"] = {"parse": [], "roles": [role_id]}
    return body


def make_notifier(url=None, secret=None, discord_url=None, link_tpl=None, role_id=None):
    """Gabungan: webhook ke panel (HANDOFF_WEBHOOK_URL) dan/atau Discord (DISCORD_WEBHOOK_URL). None bila keduanya kosong."""
    url = url if url is not None else os.getenv("HANDOFF_WEBHOOK_URL", "")
    secret = secret if secret is not None else os.getenv("HANDOFF_WEBHOOK_SECRET", "")
    discord_url = discord_url if discord_url is not None else os.getenv("DISCORD_WEBHOOK_URL", "")
    link_tpl = link_tpl if link_tpl is not None else os.getenv("PANEL_LINK_TEMPLATE", "")      # mis. https://panel.tokomu.com/chat/{id}
    role_id = role_id if role_id is not None else os.getenv("DISCORD_MENTION_ROLE_ID", "")
    if not (url or discord_url): return None
    def notify(event: dict):
        ev = {**event, "ts": int(time.time())}
        if url: _pool.submit(_post, url, secret, json.dumps(ev, ensure_ascii=False).encode())
        if discord_url:
            body = discord_payload(ev, link_tpl, role_id)
            if body: _pool.submit(_post, discord_url, "", json.dumps(body, ensure_ascii=False).encode())
    return notify
