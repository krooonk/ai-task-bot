import os
import logging
import json
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
import redis.asyncio as aioredis

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://api:8000")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
redis_client = aioredis.from_url(REDIS_URL)


@dp.message(Command("start", "help"))
async def cmd_start_help(message: Message):
    await message.answer(
        "🤖 **AI Task Bot is active!**\n\n"
        "• **Send a text message** or a **voice note** to automatically create a task.\n"
        "• Type **/tasks** to view your current list of tasks.\n"
        "• Manage your workflow live on the web dashboard!"
    )


@dp.message(Command("tasks"))
async def cmd_tasks(message: Message):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BACKEND_API_URL}/tasks") as response:
                if response.status == 200:
                    tasks = await response.json()
                    if not tasks:
                        await message.answer("📭 You have no tasks right now.")
                        return

                    msg = "📋 **Your Current Tasks:**\n\n"
                    for t in tasks:
                        status = t.get('status', 'pending')
                        status_emoji = "⏳" if status == 'pending' else "🔄" if status == 'in_progress' else "✅"
                        msg += f"{status_emoji} **{t.get('title')}** _({status})_\n"

                    await message.answer(msg, parse_mode="Markdown")
                else:
                    await message.answer("⚠️ Could not fetch tasks from the server.")
    except Exception as e:
        await message.answer(f"⚠️ Error connecting to backend: {e}")


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message):
    text = message.text

    # Send text task directly to FastAPI backend
    async with aiohttp.ClientSession() as session:
        payload = {
            "title": text[:50],
            "description": text,
            "source": "telegram_text"
        }
        async with session.post(f"{BACKEND_API_URL}/tasks", json=payload) as resp:
            if resp.status in [200, 201]:
                await message.answer(f"✅ Task created successfully:\n\"{text}\"")
            else:
                await message.answer("❌ Failed to create task. Backend error.")


@dp.message(F.voice)
async def handle_voice_message(message: Message):
    await message.answer("🎙️ Voice note received! Transcribing locally with Whisper...")

    voice = message.voice
    file_info = await bot.get_file(voice.file_id)

    # Push job data to Redis queue for the worker to pick up
    job_data = {
        "file_path": file_info.file_path,
        "chat_id": message.chat.id,
        "telegram_file_id": voice.file_id
    }
    await redis_client.lpush("transcription_queue", json.dumps(job_data))


async def main():
    print("Telegram Bot starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())