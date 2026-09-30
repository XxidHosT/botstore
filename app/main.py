import os, pathlib, secrets, time, collections
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .dialogue import Bot
from .kb import DATA
from . import review
from .store import StateStore
from .notify import make_notifier

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")                       # kosong = endpoint admin nonaktif (aman secara default)
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
TRUST_PROXY = os.getenv("TRUST_PROXY", "") == "1"                # hanya nyalakan bila di belakang reverse proxy tepercaya
IP_LIMIT = int(os.getenv("IP_RATE_PER_MIN", "60"))

app = FastAPI(title="JG chat-brain")
if ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["POST", "GET"], allow_headers=["Content-Type", "Authorization"])
store = StateStore(os.getenv("STATE_DB", str(DATA / "state.db")))
bot = Bot(store=store, notifier=make_notifier())
_ip_hits = collections.defaultdict(collections.deque)


def client_ip(req: Request) -> str:
    if TRUST_PROXY and req.headers.get("x-forwarded-for"):
        return req.headers["x-forwarded-for"].split(",")[-1].strip()      # entri terakhir = yang ditambahkan proxy kita
    return req.client.host if req.client else "?"


@app.middleware("http")
async def ip_rate_limit(request: Request, call_next):
    if request.url.path == "/reply":
        q, now = _ip_hits[client_ip(request)], time.time()
        while q and now - q[0] > 60: q.popleft()
        q.append(now)
        if len(q) > IP_LIMIT:
            return JSONResponse({"detail": "too many requests"}, status_code=429)
        if len(_ip_hits) > 10_000:                                          # cegah dict tumbuh tanpa batas
            for k in [k for k, v in _ip_hits.items() if not v or now - v[-1] > 60]: _ip_hits.pop(k, None)
    return await call_next(request)


def admin(authorization: str = Header(default="")):
    if not ADMIN_TOKEN:
        raise HTTPException(503, "admin disabled: set ADMIN_TOKEN")
    if not secrets.compare_digest(authorization, f"Bearer {ADMIN_TOKEN}"):
        raise HTTPException(401, "unauthorized")


class ReplyIn(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class ModeIn(BaseModel):
    mode: str = Field(pattern="^(AI|AGENT)$")


@app.get("/health")
def health(): return {"ok": True}


@app.post("/reply")
def reply(body: ReplyIn): return bot.reply(body.conversation_id, body.message.strip())


@app.get("/conversations", dependencies=[Depends(admin)])              # daftar percakapan yang menunggu/dipegang admin
def handoffs(): return {"items": store.list_handoffs()}


@app.get("/conversations/{cid}", dependencies=[Depends(admin)])         # riwayat singkat (email/telepon dimasker) untuk panel admin
def conversation(cid: str):
    s = store.get(cid)
    if not s: raise HTTPException(404, "not found")
    return {"conversation_id": cid, "mode": s["mode"], "handoff": s["handoff"], "lang": s["lang"], "history": s["history"]}


@app.post("/conversations/{cid}/mode", dependencies=[Depends(admin)])   # sisi admin: ambil alih (AGENT) / kembalikan ke bot (AI)
def set_mode(cid: str, body: ModeIn): bot.set_mode(cid, body.mode); return {"conversation_id": cid, "mode": body.mode}


@app.post("/admin/reload", dependencies=[Depends(admin)])              # setelah menyunting knowledge.yaml / products.json
def reload(): bot.reload(); return {"reloaded": True}


# ---- dasbor review (halaman statis tanpa data; semua data lewat API yang butuh token) ----
UI = pathlib.Path(__file__).resolve().parent / "admin_ui"
CSP = {"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'", "Cache-Control": "no-store"}


@app.get("/admin/review", include_in_schema=False)
def review_page(): return FileResponse(UI / "review.html", headers=CSP)


@app.get("/admin/review.js", include_in_schema=False)
def review_js(): return FileResponse(UI / "review.js", media_type="text/javascript", headers=CSP)


@app.get("/admin/review.css", include_in_schema=False)
def review_css(): return FileResponse(UI / "review.css", media_type="text/css", headers=CSP)


class LabelIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    intent: str = Field(min_length=1, max_length=64)


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class LearnedIn(BaseModel):
    intent: str
    lang: str
    text: str


def _guard(fn, *a):
    try: return fn(*a)
    except review.ReviewError as e: raise HTTPException(400, str(e))


@app.get("/admin/api/intents", dependencies=[Depends(admin)])
def intents_api(): return {"items": [{"name": n, "label": (v.get("label") or {}).get("id", "")} for n, v in bot.kb.intents.items()]}


@app.get("/admin/api/review", dependencies=[Depends(admin)])
def review_api(min_count: int = 1): return review.overview(bot.clf, min_count)


@app.post("/admin/api/review/label", dependencies=[Depends(admin)])
def review_label(b: LabelIn): return _guard(review.label, bot.kb, b.text, b.intent)


@app.post("/admin/api/review/dismiss", dependencies=[Depends(admin)])
def review_dismiss(b: TextIn): review.dismiss(b.text); return {"ok": True}


@app.get("/admin/api/learned", dependencies=[Depends(admin)])
def learned_api(): return {"items": review.learned()}


@app.post("/admin/api/learned/remove", dependencies=[Depends(admin)])
def learned_remove(b: LearnedIn): return _guard(review.remove, b.intent, b.lang, b.text)


static = pathlib.Path(__file__).resolve().parent.parent / "static"
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="static")
