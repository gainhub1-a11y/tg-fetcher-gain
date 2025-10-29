import os
import tempfile
import mimetypes
from fastapi import FastAPI, HTTPException, Response, Query
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
STRING_SESSION = os.environ["STRING_SESSION"]

app = FastAPI(title="TG MTProto Fetcher", version="1.2.0")
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

@app.on_event("startup")
async def startup():
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon session not authorized. Regenerate STRING_SESSION.")

def _name_mime(path: str):
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    name = os.path.basename(path) or "file.bin"
    return name, mime

def _coerce_chat_id(v: str):
    """Se è un id numerico (anche con -100...), convertilo a int; altrimenti tienilo stringa (username @...)."""
    s = v.strip()
    if s.startswith("@"):
        return s
    # numerico? (togli eventuale segno -)
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except Exception:
            pass
    return s  # resta stringa (username, link, ecc.)

@app.get("/health")
async def health():
    me = await client.get_me()
    return {"ok": True, "user": me.username or me.first_name or me.id}

@app.get("/resolve")
async def resolve(chat_id: str = Query(...)):
    try:
        entity = await client.get_entity(_coerce_chat_id(chat_id))
        return {
            "ok": True,
            "title": getattr(entity, "title", None),
            "id": getattr(entity, "id", None),
            "username": getattr(entity, "username", None),
            "class": entity.__class__.__name__,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Resolve error: {e}")

@app.get("/download")
async def download(
    chat_id: str = Query(..., description="Numeric id like -100123... or @channel username"),
    message_id: int = Query(..., description="Telegram message id containing media"),
):
    try:
        # 1) Risolvi correttamente l'entità
        entity = await client.get_entity(_coerce_chat_id(chat_id))

        # 2) Recupera il messaggio
        msg = await client.get_messages(entity, ids=message_id)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Media not found in that message")

        # 3) Scarica su file temporaneo
        tmpdir = tempfile.mkdtemp()
        path = await client.download_media(msg, file=tmpdir)
        if not path:
            raise HTTPException(status_code=404, detail="Unable to download media")

        # 4) Ritorna binario
        name, mime = _name_mime(path)
        with open(path, "rb") as f:
            data = f.read()
        return Response(
            content=data,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename=\"%s\"' % name},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download error: {e}")
