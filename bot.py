import os
import re
import uuid
import logging
import asyncio
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

INSTAGRAM_PATTERN = re.compile(
    r"https?://(www\.)?instagram\.com/(p|reel|tv|stories)/[\w\-]+/?(\?[^\s]*)?"
)

YOUTUBE_PATTERN = re.compile(
    r"https?://(www\.)?(youtube\.com/(watch\?[^\s]*v=[\w\-]+|shorts/[\w\-]+)|youtu\.be/[\w\-]+)[^\s]*"
)

TIKTOK_PATTERN = re.compile(
    r"https?://(www\.|vm\.|vt\.)?tiktok\.com/[\w\-@/\?=&%\.]+"
)

DOWNLOAD_DIR = Path("/tmp/tg_bot_downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Telegram video size limit: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024


def is_instagram_url(text: str) -> bool:
    return bool(INSTAGRAM_PATTERN.search(text))


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_PATTERN.search(text))


def is_tiktok_url(text: str) -> bool:
    return bool(TIKTOK_PATTERN.search(text))


async def download_instagram_video(url: str) -> Path | None:
    out_id = uuid.uuid4().hex
    out_template = str(DOWNLOAD_DIR / f"{out_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--max-filesize", "50m",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "--merge-output-format", "mp4",
        "--no-check-certificate",
        "--extractor-args", "instagram:player_client=web",
        "-o", out_template,
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("yt-dlp failed: %s", stderr.decode())
        return None

    matches = list(DOWNLOAD_DIR.glob(f"{out_id}.*"))
    if not matches:
        logger.error("yt-dlp finished but no output file found")
        return None

    return matches[0]


async def download_youtube_video(url: str) -> Path | None:
    out_id = uuid.uuid4().hex
    out_template = str(DOWNLOAD_DIR / f"{out_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--max-filesize", "50m",
        "-f", "bestvideo[ext=mp4][filesize<50M]+bestaudio[ext=m4a]/best[ext=mp4][filesize<50M]/best",
        "--merge-output-format", "mp4",
        "-o", out_template,
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("yt-dlp failed for YouTube: %s", stderr.decode())
        return None

    matches = list(DOWNLOAD_DIR.glob(f"{out_id}.*"))
    if not matches:
        logger.error("yt-dlp finished but no output file found for YouTube")
        return None

    return matches[0]


async def download_tiktok_video(url: str) -> Path | None:
    out_id = uuid.uuid4().hex
    out_template = str(DOWNLOAD_DIR / f"{out_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--max-filesize", "50m",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", out_template,
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("yt-dlp failed for TikTok: %s", stderr.decode())
        return None

    matches = list(DOWNLOAD_DIR.glob(f"{out_id}.*"))
    if not matches:
        logger.error("yt-dlp finished but no output file found for TikTok")
        return None

    return matches[0]


async def handle_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    match = INSTAGRAM_PATTERN.search(text)
    if not match:
        return

    url = match.group(0)
    status_msg = await update.message.reply_text("⏳ Video yuklanmoqda, iltimos kuting...")

    video_path: Path | None = None
    try:
        video_path = await download_instagram_video(url)

        if video_path is None:
            await status_msg.edit_text(
                "❌ Videoni yuklab bo'lmadi.\n\n"
                "Buning sabablari:\n"
                "• Post shaxsiy hisobdan\n"
                "• Instagram so'rovni blokladi\n"
                "• Havola muddati o'tgan Story"
            )
            return

        file_size = video_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Video juda katta ({file_size // (1024*1024)} MB).\n"
                "Telegram maksimal 50 MB ruxsat beradi."
            )
            return

        await status_msg.edit_text("📤 Video jo'natilmoqda...")
        with open(video_path, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="📥 Instagramdan yuklandi",
                supports_streaming=True,
            )
        await status_msg.delete()

    except Exception as e:
        logger.exception("Error handling Instagram URL")
        await status_msg.edit_text(f"❌ Kutilmagan xato yuz berdi: {e}")

    finally:
        if video_path and video_path.exists():
            video_path.unlink()


async def handle_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    match = YOUTUBE_PATTERN.search(text)
    if not match:
        return

    url = match.group(0)
    status_msg = await update.message.reply_text("⏳ YouTube video yuklanmoqda, iltimos kuting...")

    video_path: Path | None = None
    try:
        video_path = await download_youtube_video(url)

        if video_path is None:
            await status_msg.edit_text(
                "❌ Videoni yuklab bo'lmadi.\n\n"
                "Buning sabablari:\n"
                "• Video yosh chegaralangan yoki shaxsiy\n"
                "• Video hajmi 50 MB dan oshib ketdi\n"
                "• YouTube so'rovni vaqtincha blokladi"
            )
            return

        file_size = video_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Video juda katta ({file_size // (1024*1024)} MB).\n"
                "Telegram maksimal 50 MB ruxsat beradi. Qisqaroq video sinab ko'ring."
            )
            return

        await status_msg.edit_text("📤 Video jo'natilmoqda...")
        with open(video_path, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="📥 YouTubedan yuklandi",
                supports_streaming=True,
            )
        await status_msg.delete()

    except Exception as e:
        logger.exception("Error handling YouTube URL")
        await status_msg.edit_text(f"❌ Kutilmagan xato yuz berdi: {e}")

    finally:
        if video_path and video_path.exists():
            video_path.unlink()


async def handle_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    match = TIKTOK_PATTERN.search(text)
    if not match:
        return

    url = match.group(0)
    status_msg = await update.message.reply_text("⏳ TikTok video yuklanmoqda, iltimos kuting...")

    video_path: Path | None = None
    try:
        video_path = await download_tiktok_video(url)

        if video_path is None:
            await status_msg.edit_text(
                "❌ Videoni yuklab bo'lmadi.\n\n"
                "Buning sabablari:\n"
                "• Hisob shaxsiy\n"
                "• TikTok so'rovni blokladi\n"
                "• Video o'chirilgan"
            )
            return

        file_size = video_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Video juda katta ({file_size // (1024*1024)} MB).\n"
                "Telegram maksimal 50 MB ruxsat beradi."
            )
            return

        await status_msg.edit_text("📤 Video jo'natilmoqda...")
        with open(video_path, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="📥 TikTokdan yuklandi",
                supports_streaming=True,
            )
        await status_msg.delete()

    except Exception as e:
        logger.exception("Error handling TikTok URL")
        await status_msg.edit_text(f"❌ Kutilmagan xato yuz berdi: {e}")

    finally:
        if video_path and video_path.exists():
            video_path.unlink()


async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if is_instagram_url(text):
        await handle_instagram(update, context)
    elif is_youtube_url(text):
        await handle_youtube(update, context)
    elif is_tiktok_url(text):
        await handle_tiktok(update, context)
    else:
        await update.message.reply_text(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Salom, <b>{user.first_name}</b>! 👋\n\n"
        "Men quyidagilarni qila olaman:\n\n"
        "📥 <b>Instagram yuklovchi</b> — Instagram post/reel havolasini yuboring\n"
        "▶️ <b>YouTube yuklovchi</b> — YouTube video yoki Shorts havolasini yuboring\n"
        "🎵 <b>TikTok yuklovchi</b> — TikTok video havolasini yuboring\n\n"
        "/start — xush kelibsiz xabarini ko'rsatish\n"
        "/help — barcha buyruqlar ro'yxati\n"
        "/echo &lt;matn&gt; — xabaringizni qaytarish\n"
        "/time — joriy sana va vaqtni ko'rsatish\n"
        "/info — Telegram hisob ma'lumotlarini ko'rsatish"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(
        "<b>Mavjud buyruqlar:</b>\n\n"
        "/start — xush kelibsiz xabari\n"
        "/help — yordam ko'rsatish\n"
        "/echo &lt;matn&gt; — xabarni takrorlash\n"
        "/time — joriy sana va vaqt\n"
        "/info — hisob ma'lumotlari\n\n"
        "📥 <b>Instagram yuklovchi:</b>\n"
        "Istalgan Instagram post yoki reel havolasini yuboring — videoni qaytaraman.\n\n"
        "▶️ <b>YouTube yuklovchi:</b>\n"
        "Istalgan YouTube video yoki Shorts havolasini yuboring — videoni qaytaraman.\n\n"
        "🎵 <b>TikTok yuklovchi:</b>\n"
        "Istalgan TikTok video havolasini yuboring — videoni qaytaraman."
    )


async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        await update.message.reply_text(" ".join(context.args))
    else:
        await update.message.reply_text("Foydalanish: /echo <xabaringiz>")


async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now().strftime("%A, %d %B %Y, soat %H:%M:%S")
    await update.message.reply_text(f"🕐 Joriy vaqt: {now}")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    til = user.language_code or "noma'lum"
    username_line = f"Foydalanuvchi nomi: @{user.username}" if user.username else "Foydalanuvchi nomi: (mavjud emas)"
    lines = [
        "<b>Hisob ma'lumotlaringiz:</b>",
        f"Ism: {user.full_name}",
        username_line,
        f"Foydalanuvchi ID: <code>{user.id}</code>",
        f"Chat ID: <code>{chat.id}</code>",
        f"Chat turi: {chat.type}",
        f"Til: {til}",
    ]
    await update.message.reply_html("\n".join(lines))


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("echo", echo_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
    
