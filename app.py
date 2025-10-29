import os
import tempfile
import mimetypes
from fastapi import FastAPI, HTTPException, Response, Query
from telethon import TelegramClient
from telethon.sessions import StringSession

# === Environment variables (set these in Render) ===
# API_ID: int from my.telegram.org
# API_HASH: str from my.telegram.org
# STRING_SESSION: str generated with Telethon (DO NOT COMMIT)
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
STRING_SESSION = os.environ["STRING_SESSION"]

app = FastAPI(title="TG MTProto Fetcher", version="1.1.0")

# MTProto client (user session, no 20MB limit)
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

@app.get("/health")
async def health():
    me = await client.get_me()
    return {"ok": True, "user": me.username or me.first_name or me.id}

@app.get("/download")
async def download(
    chat_id: str = Query(..., description="Numeric id like -100123... or @channel username"),
    message_id: int = Query(..., description="Telegram message id containing media"),
):
    try:
        # 1) Resolve the entity (supports @username or numeric id like -100...)
        entity = await client.get_entity(chat_id)

        # 2) Fetch the message
        msg = await client.get_messages(entity, ids=message_id)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Media not found in that message")

        # 3) Download to a temp file
        tmpdir = tempfile.mkdtemp()
        path = await client.download_media(msg, file=tmpdir)
        if not path:
            raise HTTPException(status_code=404, detail="Unable to download media")

        # 4) Return binary
        name, mime = _name_mime(path)
        with open(path, "rb") as f:
            data = f.read()
        headers = {"Content-Disposition": f'attachment; filename="{name}"'}
        return Response(content=data, media_type=mime, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        # Bubble up real error text to help debugging in Render logs
        raise HTTPException(status_code=500, detail=f"Download error: {e}")
