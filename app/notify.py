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


def make_notifier(url=None, secret=None):
    """None bila HANDOFF_WEBHOOK_URL kosong (fitur mati)."""
    url = url if url is not None else os.getenv("HANDOFF_WEBHOOK_URL", "")
    secret = secret if secret is not None else os.getenv("HANDOFF_WEBHOOK_SECRET", "")
    if not url: return None
    def notify(event: dict):
        _pool.submit(_post, url, secret, json.dumps({**event, "ts": int(time.time())}, ensure_ascii=False).encode())
    return notify
