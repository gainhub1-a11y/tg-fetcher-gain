# TG MTProto Fetcher (Render-ready)

This tiny FastAPI service uses **Telethon (MTProto)** to fetch media from Telegram
channels/groups using a normal *user* account (no 20MB limit). It exposes:

- `GET /download?chat_id=...&message_id=...`  → returns the media as binary
- `GET /health` → health check

## Deploy on Render

1. Create a new **Web Service** from this folder/repo.
2. **Environment → Add Variables:**
   - `API_ID` (from my.telegram.org)
   - `API_HASH` (from my.telegram.org)
   - `STRING_SESSION` (generated via Colab/Telethon)
3. **Build Command:**
   ```
   pip install -r requirements.txt
   ```
4. **Start Command:**
   ```
   uvicorn app:app --host 0.0.0.0 --port 10000
   ```
5. After deploy, test:
   ```
   https://YOUR-SERVICE.onrender.com/health
   ```

## Use in Make (replace "Telegram Bot → Download a file")

- Keep your **Watch Updates** step.
- Insert **HTTP → Get a file**:
  - URL:
    ```
    https://YOUR-SERVICE.onrender.com/download?chat_id={{2.object.message.chat.id}}&message_id={{2.object.message.message_id}}
    ```
    (adjust path depending on your Watch Updates mapping)
- The module returns a **Binary**; feed it into **CloudConvert → Convert a file**.

### Notes
- For **public channels**, `chat_id` can be `@channelusername`.
- For **private channels**, use the numeric id like `-1001234567890` and ensure the user
  account (the one behind STRING_SESSION) is **a member** of the channel.
- Treat `STRING_SESSION` as a secret (like a password).
