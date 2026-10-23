import asyncio
import json
import logging
import os
import uuid
from datetime import datetime

import httpx
import redis.asyncio as aioredis
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/tasks")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_KEY = os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")

QUEUE_NAME = "transcription_queue"
MAX_DURATION_S = 120
MAX_FILE_BYTES = 5 * 1024 * 1024

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# timeout per request; the client itself retries 429/5xx/connection errors with backoff
openai_client = AsyncOpenAI(api_key=OPENAI_KEY, timeout=30, max_retries=2)


async def tg_call(http: httpx.AsyncClient, method: str, payload: dict) -> bool:
    try:
        r = await http.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}", json=payload)
        return r.status_code == 200
    except httpx.HTTPError as e:
        log.warning("Telegram %s failed: %s", method, e)
        return False


async def notify(http, chat_id, message_id, text_):
    """Edit the 'Transcribing...' message if we have its id, otherwise send a new one."""
    if not chat_id or not TELEGRAM_BOT_TOKEN:
        return
    if message_id and await tg_call(
        http, "editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text_}
    ):
        return
    await tg_call(http, "sendMessage", {"chat_id": chat_id, "text": text_})


async def download_audio(http, file_path: str, dest: str):
    url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    r = await http.get(url)
    r.raise_for_status()
    if len(r.content) > MAX_FILE_BYTES:
        raise ValueError("file_too_large")
    with open(dest, "wb") as f:
        f.write(r.content)


async def transcribe(path: str) -> str:
    with open(path, "rb") as f:
        result = await openai_client.audio.transcriptions.create(model="whisper-1", file=f)
    return result.text.strip()


async def save_task(transcript: str):
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "INSERT INTO tasks (title, description, status, source, created_at) "
                "VALUES (:title, :desc, 'PENDING', 'telegram_voice', :time)"
            ),
            {"title": transcript[:50], "desc": transcript, "time": datetime.utcnow()},
        )
        await session.commit()


async def handle_job(http: httpx.AsyncClient, data: dict):
    chat_id = data.get("chat_id")
    msg_id = data.get("status_message_id")
    file_id = data.get("telegram_file_id", "unknown")
    job_id = uuid.uuid4().hex[:8]
    local_audio = f"/tmp/{file_id}-{job_id}.ogg"
    log.info("[%s] job started chat=%s file=%s", job_id, chat_id, file_id)

    try:
        duration = data.get("duration")
        if duration and duration > MAX_DURATION_S:
            await notify(http, chat_id, msg_id, f"⚠️ Voice message too long (max {MAX_DURATION_S}s).")
            return

        await download_audio(http, data["file_path"], local_audio)
        transcript = await transcribe(local_audio)

        if not transcript:
            await notify(http, chat_id, msg_id, "🤔 Couldn't understand the audio. Please try again.")
            return

        await save_task(transcript)
        await notify(http, chat_id, msg_id, f'✅ Task created:\n"{transcript}"')
        log.info("[%s] task created", job_id)

    except ValueError as e:
        if str(e) == "file_too_large":
            await notify(http, chat_id, msg_id, "⚠️ Audio file is too large.")
        else:
            raise
    except (APITimeoutError, APIConnectionError, RateLimitError):
        log.exception("[%s] transcription service unavailable", job_id)
        await notify(http, chat_id, msg_id, "⏳ Transcription service is busy. Please try again in a minute.")
    except httpx.HTTPError:
        log.exception("[%s] audio download failed", job_id)
        await notify(http, chat_id, msg_id, "❌ Couldn't download your voice message. Please resend it.")
    except Exception:
        log.exception("[%s] unexpected failure", job_id)
        await notify(http, chat_id, msg_id, "❌ Something went wrong processing your voice message.")
    finally:
        if os.path.exists(local_audio):
            os.remove(local_audio)


async def process_transcription_queue():
    if not OPENAI_KEY:
        raise SystemExit("Missing OPEN_AI_KEY / OPENAI_API_KEY")

    redis = aioredis.from_url(REDIS_URL)
    log.info("Worker listening on Redis queue '%s'", QUEUE_NAME)

    async with httpx.AsyncClient(timeout=30) as http:
        while True:
            try:
                item = await redis.brpop(QUEUE_NAME, timeout=5)
                if not item:
                    continue
                await handle_job(http, json.loads(item[1]))
            except Exception:
                log.exception("Worker loop error")
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(process_transcription_queue())