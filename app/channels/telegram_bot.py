import logging
from typing import Set
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from ..config import settings
from ..printer import printer, PrintJob
from ..history import get_history
from ..scheduler import print_weather_now

logger = logging.getLogger(__name__)
_app: Application | None = None


def _allowed_users() -> Set[int]:
    raw = settings.telegram_allowed_user_ids.strip()
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


def _is_allowed(user_id: int) -> bool:
    allowed = _allowed_users()
    return not allowed or user_id in allowed


async def _submit_and_reply(update: Update, job: PrintJob, ok_msg: str = "Imprime"):
    accepted, msg = await printer.submit(job)
    if accepted:
        await update.message.reply_text(ok_msg)
    else:
        await update.message.reply_text(f"Refuse: {msg}")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_allowed(user.id):
        await update.message.reply_text(f"Acces refuse. Ton ID: {user.id}")
        return
    await update.message.reply_text(
        "Bot d'impression thermique pret !\n\n"
        "- Texte simple -> impression\n"
        "- Photo -> impression de la photo\n\n"
        "Commandes:\n"
        "  /bold <texte>             impression en gras\n"
        "  /title <titre>|<message>  titre + message\n"
        "  /qr <texte ou URL>        QR code\n"
        "  /meteo                    meteo du jour\n"
        "  /history [n]              n derniers tickets (defaut 10)\n"
    )


async def bold_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id): return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /bold <texte>")
        return
    sender = update.effective_user.first_name or "x"
    await _submit_and_reply(update, PrintJob(kind="text", text=text,
                                              source=f"telegram/{sender}", bold=True))


async def title_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id): return
    raw = " ".join(context.args)
    if "|" not in raw:
        await update.message.reply_text("Usage: /title <titre>|<message>")
        return
    title, _, body = raw.partition("|")
    sender = update.effective_user.first_name or "x"
    await _submit_and_reply(update, PrintJob(kind="text", text=body.strip(),
                                              title=title.strip(), source=f"telegram/{sender}"))


async def qr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id): return
    data = " ".join(context.args)
    if not data:
        await update.message.reply_text("Usage: /qr <texte ou URL>")
        return
    sender = update.effective_user.first_name or "x"
    await _submit_and_reply(update, PrintJob(kind="qr", qr_data=data,
                                              source=f"telegram/{sender}"),
                            ok_msg="QR code en cours d'impression")


async def meteo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id): return
    await update.message.reply_text("Recuperation de la meteo...")
    sender = update.effective_user.first_name or "x"
    await print_weather_now(source=f"scheduled/meteo-{sender}")
    await update.message.reply_text("Meteo imprimee !")


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id): return
    try:
        n = int(context.args[0]) if context.args else 10
        n = max(1, min(n, 50))
    except (ValueError, IndexError):
        n = 10
    items = get_history(n)
    if not items:
        await update.message.reply_text("Historique vide.")
        return
    lines = [f"{n} derniers tickets:\n"]
    for item in items:
        ts = item["timestamp"][:16].replace("T", " ")
        preview = (item["preview"] or "")[:40]
        lines.append(f"{ts} [{item['source']}] {preview}")
    await update.message.reply_text("\n".join(lines))


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text(f"Acces refuse. Ton ID: {update.effective_user.id}")
        return
    text = update.message.text
    sender = update.effective_user.first_name or "x"
    await _submit_and_reply(update, PrintJob(kind="text", text=text,
                                              source=f"telegram/{sender}"),
                            ok_msg="Recu et envoye a l'impression")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id): return
    sender = update.effective_user.first_name or "x"
    photo = update.message.photo[-1]
    try:
        file = await photo.get_file(read_timeout=60, connect_timeout=30)
        image_bytes = bytes(await file.download_as_bytearray(read_timeout=60, connect_timeout=30))
    except Exception as e:
        await update.message.reply_text(f"Echec telechargement: {e}")
        return
    await _submit_and_reply(update, PrintJob(kind="image", image_bytes=image_bytes,
                                              caption=update.message.caption,
                                              source=f"telegram/{sender}"),
                            ok_msg="Photo recue, impression en cours...")


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_user.id): return
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Je ne sais imprimer que les images")
        return
    sender = update.effective_user.first_name or "x"
    file = await doc.get_file(read_timeout=60, connect_timeout=30)
    image_bytes = bytes(await file.download_as_bytearray(read_timeout=60, connect_timeout=30))
    await _submit_and_reply(update, PrintJob(kind="image", image_bytes=image_bytes,
                                              caption=update.message.caption,
                                              source=f"telegram/{sender}"),
                            ok_msg="Image recue, impression en cours...")


async def start():
    global _app
    if not settings.telegram_bot_token:
        logger.info("Token Telegram absent: bot desactive")
        return
    request = HTTPXRequest(connect_timeout=30, read_timeout=60, write_timeout=60, pool_timeout=30)
    _app = (Application.builder().token(settings.telegram_bot_token)
            .request(request).get_updates_request(request).build())
    _app.add_handler(CommandHandler("start", start_cmd))
    _app.add_handler(CommandHandler("bold", bold_cmd))
    _app.add_handler(CommandHandler("title", title_cmd))
    _app.add_handler(CommandHandler("qr", qr_cmd))
    _app.add_handler(CommandHandler("meteo", meteo_cmd))
    _app.add_handler(CommandHandler("history", history_cmd))
    _app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    _app.add_handler(MessageHandler(filters.Document.IMAGE, document_handler))
    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling()
    logger.info("Bot Telegram demarre")


async def stop():
    global _app
    if _app is None: return
    await _app.updater.stop()
    await _app.stop()
    await _app.shutdown()
    logger.info("Bot Telegram arrete")
