import pathlib
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .dialogue import Bot

app = FastAPI(title="JG chat-brain")
bot = Bot()


class ReplyIn(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class ModeIn(BaseModel):
    mode: str = Field(pattern="^(AI|AGENT)$")


@app.get("/health")
def health(): return {"ok": True}


@app.post("/reply")
def reply(body: ReplyIn): return bot.reply(body.conversation_id, body.message.strip())


@app.post("/conversations/{cid}/mode")   # dipanggil sisi admin: ambil alih (AGENT) / kembalikan ke bot (AI)
def set_mode(cid: str, body: ModeIn): return bot.set_mode(cid, body.mode)


@app.post("/admin/reload")               # setelah menyunting knowledge.yaml / products.json
def reload(): bot.reload(); return {"reloaded": True}


static = pathlib.Path(__file__).resolve().parent.parent / "static"
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="static")
