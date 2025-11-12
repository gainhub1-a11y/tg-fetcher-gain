import os
import tempfile
import mimetypes
from fastapi import FastAPI, HTTPException, Response, Query, Header
from telethon import TelegramClient
from telethon.sessions import StringSession

# === Environment variables (set these in Render) ===
# API_ID: int from my.telegram.org
# API_HASH: str from my.telegram.org
# STRING_SESSION: str generated with Telethon (DO NOT COMMIT)
# API_KEY: optional secret to protect endpoints (pass via X-API-Key header)
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
STRING_SESSION = os.environ["STRING_SESSION"]
API_KEY = os.environ.get("API_KEY")  # optional

app = FastAPI(title="TG MTProto Fetcher", version="1.3.0")

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

def _coerce_chat_id(v: str | None):
    """
    Keep @username as str; convert numeric ids (including -100...) to int.
    Returns None if v is None/empty.
    """
    if v is None:
        return None
    s = v.strip()
    if not s:
        return None
    if s.startswith("@"):
        return s
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except Exception:
            pass
    return s

@app.get("/health")
async def health():
    me = await client.get_me()
    return {"ok": True, "user": me.username or me.first_name or me.id}

# NEW: debug helper (safe to keep in prod)
@app.get("/resolve")
async def resolve(
    chat_id: str | None = Query(None, description="For channels/groups: -100... or @username"),
    peer: str | None = Query(None, description="For private chats: @BotUsername or @username"),
    x_api_key: str | None = Header(default=None, convert_underscores=False),
):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        target = peer or _coerce_chat_id(chat_id)
        if not target:
            raise HTTPException(status_code=400, detail="Specify chat_id or peer")
        entity = await client.get_entity(target)
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
    # Backward compatibility: existing flows still pass chat_id & message_id.
    chat_id: str | None = Query(None, description="Numeric id like -100... or @channel username"),
    message_id: int = Query(..., description="Telegram message id containing media"),
    # NEW: support private chats by passing the explicit peer (e.g., @MyTranslatorBot)
    peer: str | None = Query(None, description="For private chats: @BotUsername or @username"),
    x_api_key: str | None = Header(default=None, convert_underscores=False),
):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Choose target: if 'peer' provided (private chat), use it; else use chat_id (as before)
        target = peer or _coerce_chat_id(chat_id)
        if not target:
            raise HTTPException(status_code=400, detail="Provide either 'peer' (private) or 'chat_id' (channel/group)")

        # 1) Resolve entity
        entity = await client.get_entity(target)

        # 2) Fetch message
        msg = await client.get_messages(entity, ids=message_id)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Media not found in that message")

        # 3) Download to temp file
        tmpdir = tempfile.mkdtemp()
        path = await client.download_media(msg, file=tmpdir)
        if not path:
            raise HTTPException(status_code=404, detail="Unable to download media")

        # 4) Return binary (works with Make → HTTP Get a file)
        name, mime = _name_mime(path)
        with open(path, "rb") as f:
            data = f.read()
        headers = {"Content-Disposition": f'attachment; filename="%s"' % name}
        return Response(content=data, media_type=mime, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download error: {e}")
        
from telethon.tl import types as tl_types

@app.get("/recent_media")
async def recent_media(
    peer: str = Query(..., description="Chat privata: @BotUsername"),
    limit: int = Query(20, ge=1, le=200, description="Quanti messaggi scandire"),
    x_api_key: str | None = Header(default=None, convert_underscores=False),
):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        entity = await client.get_entity(peer)
        out = []
        async for msg in client.iter_messages(entity, limit=limit):
            kind = None
            if msg.photo:
                kind = "photo"
            elif isinstance(msg.media, tl_types.MessageMediaDocument):
                mime = None
                try:
                    mime = msg.document.mime_type
                except Exception:
                    pass
                if mime and mime.startswith("video/"):
                    kind = "video"
                else:
                    kind = "document"
            if msg.media:
                out.append({
                    "id": msg.id,
                    "date": str(msg.date),
                    "kind": kind,
                    "caption": (msg.message or "")[:80],
                })
        return {"ok": True, "count": len(out), "items": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"recent_media error: {e}")


@app.get("/lookup_message")
async def lookup_message(
    peer: str = Query(..., description="Chat privata: @BotUsername"),
    short_id: int = Query(..., description="Message ID del bot (corto)"),
):
    """
    Cerca di trovare il messaggio corrispondente a quello del Bot API (es. message_id=634)
    scorrendo i messaggi recenti nella chat privata con il bot.
    """
    try:
        entity = await client.get_entity(peer)
        async for msg in client.iter_messages(entity, limit=100):
            if msg.id == short_id or (msg.reply_to and msg.reply_to.reply_to_msg_id == short_id):
                return {"ok": True, "found": True, "real_id": msg.id, "date": str(msg.date)}
        return {"ok": True, "found": False, "detail": "Not found in last 100 messages"}
    except Exception as e:
        raise HTTPException(500, f"lookup_message error: {e}")

