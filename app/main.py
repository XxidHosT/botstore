import os, pathlib, secrets, time, collections
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .dialogue import Bot
from .kb import DATA
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


static = pathlib.Path(__file__).resolve().parent.parent / "static"
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="static")
