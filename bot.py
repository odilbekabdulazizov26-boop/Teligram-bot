import os
import re
import uuid
import json
import logging
import asyncio
import urllib.request
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
AUDD_API_TOKEN = os.environ.get("AUDD_API_TOKEN", "")

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

MAX_FILE_SIZE = 50 * 1024 * 1024


def is_instagram_url(text: str) -> bool:
    return bool(INSTAGRAM_PATTERN.search(text))


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_PATTERN.search(text))


def is_tiktok_url(text: str) -> bool:
    return bool(TIKTOK_PATTERN.search(text))


def is_any_url(text: str) -> bool:
    return bool(re.search(r"https?://", text))


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
        return None

    return matches[0]


async def download_song_by_name(query: str) -> tuple[Path | None, str]:
    """YouTube dan qo'shiq nomini qidirib audio yuklab oladi (ffmpeg shart emas)."""
    out_id = uuid.uuid4().hex
    out_template = str(DOWNLOAD_DIR / f"{out_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        f"ytsearch1:{query}",
        "--no-playlist",
        "--max-filesize", "50m",
        "-f", "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio",
        "--quiet",
        "-o", out_template,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("yt-dlp song search failed: %s", stderr.decode())
        return None, ""

    matches = list(DOWNLOAD_DIR.glob(f"{out_id}.*"))
    if not matches:
        return None, ""

    # Fayl nomidan sarlavhani olamiz
    filename_stem = matches[0].stem
    title = query

    return matches[0], title


def _build_multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """Multipart/form-data body yasaydi (tashqi kutubxonasiz)."""
    boundary = uuid.uuid4().hex
    lines = []
    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b"")
        lines.append(value.encode())
    for name, (filename, data, content_type) in files.items():
        lines.append(f"--{boundary}".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
        )
        lines.append(f"Content-Type: {content_type}".encode())
        lines.append(b"")
        lines.append(data)
    lines.append(f"--{boundary}--".encode())
    body = b"\r\n".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"


async def recognize_song(audio_path: Path) -> dict | None:
    """Ovozli faylni AudD API ga yuborib qo'shiqni taniydi."""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        fields = {"return": "apple_music,spotify"}
        if AUDD_API_TOKEN:
            fields["api_token"] = AUDD_API_TOKEN

        body, content_type = _build_multipart(
            fields=fields,
            files={"file": (audio_path.name, audio_data, "audio/ogg")},
        )

        req = urllib.request.Request(
            "https://api.audd.io/",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )

        def do_request():
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())

        data = await asyncio.get_event_loop().run_in_executor(None, do_request)

        if data.get("status") == "success" and data.get("result"):
            result = data["result"]
            return {
                "title": result.get("title", ""),
                "artist": result.get("artist", ""),
            }
        return None

    except Exception as e:
        logger.exception("AudD recognition error: %s", e)
        return None


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


async def handle_song_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    """Qo'shiq nomini qidirib topib MP3 jo'natadi."""
    status_msg = await update.message.reply_text(
        f"🔍 <b>{query}</b> qidirilmoqda...", parse_mode="HTML"
    )

    song_path: Path | None = None
    try:
        song_path, title = await download_song_by_name(query)

        if song_path is None:
            await status_msg.edit_text(
                "❌ Qo'shiq topilmadi.\n\n"
                "Boshqacha nom bilan yoki ijrochi nomini ham yozing.\n"
                "Masalan: <i>Shaxriyor Muhabbat</i>",
                parse_mode="HTML",
            )
            return

        file_size = song_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text("❌ Fayl juda katta (50 MB dan oshib ketdi).")
            return

        await status_msg.edit_text("📤 Qo'shiq jo'natilmoqda...")
        with open(song_path, "rb") as f:
            await update.message.reply_audio(
                audio=f,
                title=title,
                caption=f"🎵 <b>{title}</b>",
                parse_mode="HTML",
            )
        await status_msg.delete()

    except Exception as e:
        logger.exception("Error handling song search")
        await status_msg.edit_text(f"❌ Kutilmagan xato yuz berdi: {e}")

    finally:
        if song_path and song_path.exists():
            song_path.unlink()


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ovozli xabardan qo'shiqni tanib topib jo'natadi."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    status_msg = await update.message.reply_text("🎤 Ovoz tahlil qilinmoqda...")

    voice_path: Path | None = None
    song_path: Path | None = None
    try:
        voice_file = await context.bot.get_file(voice.file_id)
        voice_path = DOWNLOAD_DIR / f"{uuid.uuid4().hex}.ogg"
        await voice_file.download_to_drive(str(voice_path))

        await status_msg.edit_text("🔍 Qo'shiq tanib olinmoqda...")
        result = await recognize_song(voice_path)

        if result is None:
            await status_msg.edit_text(
                "❌ Qo'shiqni tanib bo'lmadi.\n\n"
                "Shovqin ko'p bo'lsa yoki ovoz sifati past bo'lsa tanib ololmayman.\n"
                "Qo'shiq nomini to'g'ridan-to'g'ri yozing!"
            )
            return

        title = result["title"]
        artist = result["artist"]
        query = f"{artist} {title}" if artist else title

        await status_msg.edit_text(
            f"✅ Topildi: <b>{title}</b> — {artist}\n\n⏳ Yuklanmoqda...",
            parse_mode="HTML",
        )

        song_path, _ = await download_song_by_name(query)

        if song_path is None:
            await status_msg.edit_text(
                f"✅ Qo'shiq aniqlandi: <b>{title}</b> — {artist}\n\n"
                "❌ Yuklab bo'lmadi. Nomini yozib qidiring.",
                parse_mode="HTML",
            )
            return

        await status_msg.edit_text("📤 Jo'natilmoqda...")
        with open(song_path, "rb") as f:
            await update.message.reply_audio(
                audio=f,
                title=title,
                performer=artist,
                caption=f"🎵 <b>{title}</b> — {artist}",
                parse_mode="HTML",
            )
        await status_msg.delete()

    except Exception as e:
        logger.exception("Error handling voice message")
        await status_msg.edit_text(f"❌ Kutilmagan xato yuz berdi: {e}")

    finally:
        if voice_path and voice_path.exists():
            voice_path.unlink()
        if song_path and song_path.exists():
            song_path.unlink()


async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if is_instagram_url(text):
        await handle_instagram(update, context)
    elif is_youtube_url(text):
        await handle_youtube(update, context)
    elif is_tiktok_url(text):
        await handle_tiktok(update, context)
    elif is_any_url(text):
        await update.message.reply_text(text)
    else:
        await handle_song_search(update, context, text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Salom, <b>{user.first_name}</b>! 👋\n\n"
        "Men quyidagilarni qila olaman:\n\n"
        "🎵 <b>Qo'shiq qidirish</b> — qo'shiq nomini yozing\n"
        "🎤 <b>Ovozdan aniqlash</b> — ovozli xabar yuboring\n"
        "📥 <b>Instagram</b> — post/reel havolasini yuboring\n"
        "▶️ <b>YouTube</b> — video yoki Shorts havolasini yuboring\n"
        "🎵 <b>TikTok</b> — video havolasini yuboring\n\n"
        "/song &lt;nom&gt; — qo'shiq qidirish\n"
        "/help — barcha buyruqlar\n"
        "/time — joriy vaqt\n"
        "/info — hisob ma'lumotlari"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(
        "<b>Mavjud buyruqlar:</b>\n\n"
        "/start — xush kelibsiz xabari\n"
        "/help — yordam\n"
        "/song &lt;nom&gt; — qo'shiq qidirish\n"
        "/echo &lt;matn&gt; — xabarni takrorlash\n"
        "/time — joriy vaqt\n"
        "/info — hisob ma'lumotlari\n\n"
        "🎵 <b>Qo'shiq qidirish:</b>\n"
        "Qo'shiq nomini yozing — MP3 jo'nataman.\n"
        "Masalan: <i>Shaxriyor Muhabbat</i>\n\n"
        "🎤 <b>Ovozdan aniqlash:</b>\n"
        "Ovozli xabar yuboring — qo'shiqni tanib topib beraman.\n\n"
        "📥 Instagram, YouTube, TikTok havolalarini yuboring — videoni yuklab beraman."
    )


async def song_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        await handle_song_search(update, context, " ".join(context.args))
    else:
        await update.message.reply_text(
            "Foydalanish: /song <qo'shiq nomi>\n"
            "Masalan: /song Shaxriyor Muhabbat"
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
    username_line = (
        f"Foydalanuvchi nomi: @{user.username}"
        if user.username
        else "Foydalanuvchi nomi: (mavjud emas)"
    )
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
    app.add_handler(CommandHandler("song", song_command))
    app.add_handler(CommandHandler("echo", echo_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("info", info_command))

    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
