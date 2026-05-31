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


async def search_and_download_song(query: str) -> tuple[Path | None, str]:
    """YouTube'dan qo'shiq qidirish va yuklash"""
    out_id = uuid.uuid4().hex
    out_template = str(DOWNLOAD_DIR / f"{out_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--max-filesize", "50m",
        "-f", "bestaudio[ext=m4a]/bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", out_template,
        f"ytsearch1:{query}",
        "--print", "title",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("yt-dlp qo'shiq yuklamadi: %s", stderr.decode())
        return None, ""

    title = stdout.decode().strip().split("\n")[0] if stdout else query
    matches = list(DOWNLOAD_DIR.glob(f"{out_id}.*"))
    if not matches:
        return None, title

    return matches[0], title


async def handle_song_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Foydalanish: /qoshiq <qo'shiq nomi>\nMasalan: /qoshiq Shokir Yunusov")
        return

    status_msg = await update.message.reply_text(f"🔍 <b>{query}</b> qidirilmoqda...", parse_mode="HTML")

    audio_path = None
    try:
        audio_path, title = await search_and_download_song(query)

        if audio_path is None:
            await status_msg.edit_text("❌ Qo'shiq topilmadi. Boshqa nom bilan sinab ko'ring.")
            return

        await status_msg.edit_text("📤 Qo'shiq jo'natilmoqda...")
        with open(audio_path, "rb") as f:
            await update.message.reply_audio(
                audio=f,
                title=title,
                caption="🎵 YouTubedan topildi",
            )
        await status_msg.delete()

    except Exception as e:
        logger.exception("Qo'shiq yuklashda xato")
        await status_msg.edit_text(f"❌ Xato yuz berdi: {e}")
    finally:
        if audio_path and audio_path.exists():
            audio_path.unlink()


async def handle_voice_song_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ovoz xabari orqali qo'shiq qidirish"""
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    status_msg = await update.message.reply_text("🎵 Ovoz tahlil qilinmoqda, iltimos kuting...")

    voice_path = DOWNLOAD_DIR / f"{uuid.uuid4().hex}.ogg"
    audio_path = None

    try:
        file = await context.bot.get_file(voice.file_id)
        await file.download_to_drive(voice_path)

        # yt-dlp orqali ovozga o'xshash qo'shiq qidirish (SoundHound/Shazam API yo'q, shuning uchun foydalanuvchidan nom so'raymiz)
        await status_msg.edit_text(
            "🎵 Ovoz qabul qilindi!\n\n"
            "Afsuski, hozircha ovozdan avtomatik qo'shiq tanib olish imkoni yo'q.\n\n"
            "Iltimos, qo'shiq nomini yozing:\n"
            "/qoshiq <qo'shiq nomi>"
        )

    except Exception as e:
        logger.exception("Ovoz qayta ishlashda xato")
        await status_msg.edit_text(f"❌ Xato yuz berdi: {e}")
    finally:
        if voice_path.exists():
            voice_path.unlink()


async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if is_instagram_url(text):
        await handle_instagram(update, context)
    elif is_youtube_url(text):
        await handle_youtube(update, context)
    elif is_tiktok_url(text):
        await handle_tiktok(update, context)
    else:
        # Matn qo'shiq qidirish uchun
        if len(text) > 2 and not text.startswith("/"):
            status_msg = await update.message.reply_text(f"🔍 <b>{text}</b> qidirilmoqda...", parse_mode="HTML")
            audio_path = None
            try:
                audio_path, title = await search_and_download_song(text)
                if audio_path:
                    await status_msg.edit_text("📤 Qo'shiq jo'natilmoqda...")
                    with open(audio_path, "rb") as f:
                        await update.message.reply_audio(
                            audio=f,
                            title=title,
                            caption="🎵 YouTubedan topildi",
                        )
                    await status_msg.delete()
                else:
                    await status_msg.edit_text("❌ Qo'shiq topilmadi. Boshqa nom bilan sinab ko'ring.")
            except Exception as e:
                await status_msg.edit_text(f"❌ Xato: {e}")
            finally:
                if audio_path and audio_path.exists():
                    audio_path.unlink()
        else:
            await update.message.reply_text(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Salom, <b>{user.first_name}</b>! 👋\n\n"
        "Men quyidagilarni qila olaman:\n\n"
        "📥 <b>Instagram yuklovchi</b> — Instagram post/reel havolasini yuboring\n"
        "▶️ <b>YouTube yuklovchi</b> — YouTube video yoki Shorts havolasini yuboring\n"
        "🎵 <b>TikTok yuklovchi</b> — TikTok video havolasini yuboring\n"
        "🎶 <b>Qo'shiq qidirish</b> — Qo'shiq nomini yozing yoki /qoshiq buyrug'ini ishlating\n\n"
        "/start — xush kelibsiz xabarini ko'rsatish\n"
        "/help — barcha buyruqlar ro'yxati\n"
        "/qoshiq &lt;nom&gt; — qo'shiq qidirish\n"
        "/time — joriy sana va vaqtni ko'rsatish\n"
        "/info — Telegram hisob ma'lumotlarini ko'rsatish"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(
        "<b>Mavjud buyruqlar:</b>\n\n"
        "/start — xush kelibsiz xabari\n"
        "/help — yordam ko'rsatish\n"
        "/qoshiq &lt;nom&gt; — qo'shiq qidirish va yuklash\n"
        "/time — joriy sana va vaqt\n"
        "/info — hisob ma'lumotlari\n\n"
        "📥 <b>Instagram yuklovchi:</b>\n"
        "Istalgan Instagram post yoki reel havolasini yuboring.\n\n"
        "▶️ <b>YouTube yuklovchi:</b>\n"
        "Istalgan YouTube video yoki Shorts havolasini yuboring.\n\n"
        "🎵 <b>TikTok yuklovchi:</b>\n"
        "Istalgan TikTok video havolasini yuboring.\n\n"
        "🎶 <b>Qo'shiq qidirish:</b>\n"
        "Qo'shiq nomini yozing yoki /qoshiq &lt;nom&gt; buyrug'ini ishlating."
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
    app.add_handler(CommandHandler("qoshiq", handle_song_search))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_song_search))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
    
