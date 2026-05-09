import asyncio
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal
from escpos.printer import Usb, Dummy
from PIL import Image
import qrcode
from .config import settings
from .history import log_print
from .rate_limiter import check_limit

logger = logging.getLogger(__name__)


@dataclass
class PrintJob:
    kind: Literal["text", "image", "qr"] = "text"
    text: str = ""
    image_bytes: Optional[bytes] = None
    qr_data: str = ""
    source: str = "api"
    bold: bool = False
    underline: bool = False
    align: str = "left"
    size: str = "normal"
    title: Optional[str] = None
    caption: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    skip_rate_limit: bool = False  # pour les jobs systeme (cron meteo)


class ThermalPrinter:
    def __init__(self):
        self._queue: asyncio.Queue[PrintJob] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._printer = None

    def _connect(self):
        if self._printer is not None:
            return self._printer
        if settings.printer_type == "usb":
            self._printer = Usb(
                settings.printer_vendor_id, settings.printer_product_id,
                in_ep=settings.printer_in_ep, out_ep=settings.printer_out_ep,
                profile=settings.printer_profile,
            )
        elif settings.printer_type == "dummy":
            self._printer = Dummy()
        else:
            raise ValueError(f"Type inconnu: {settings.printer_type}")
        logger.info(f"Imprimante connectee: {settings.printer_type}")
        return self._printer

    async def submit(self, job: PrintJob) -> tuple[bool, str]:
        """
        Soumet un job. Retourne (accepted: bool, message: str).
        Si rate-limited, ne met pas en queue et retourne (False, raison).
        """
        if not job.skip_rate_limit:
            ok, msg = check_limit(job.source)
            if not ok:
                logger.warning(f"Rate limit atteint pour {job.source}: {msg}")
                return False, msg
        await self._queue.put(job)
        logger.info(f"Job [{job.kind}] depuis {job.source} (queue: {self._queue.qsize()})")
        return True, "queued"

    async def start(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("Worker demarre")

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._printer and settings.printer_type != "dummy":
            try:
                self._printer.close()
            except Exception:
                pass

    async def _worker(self):
        while True:
            try:
                job = await self._queue.get()
                await asyncio.to_thread(self._print_job, job)
                # Log dans l'historique
                preview = job.text or job.qr_data or ("[image]" if job.kind == "image" else "")
                try:
                    log_print(job.source, job.kind, job.title, preview)
                except Exception as e:
                    logger.exception(f"Echec log historique: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Erreur impression: {e}")

    def _print_header(self, printer, job: PrintJob):
        printer.set(align="center", bold=False, double_height=False, double_width=False)
        printer.text(job.timestamp.strftime("%d/%m/%Y %H:%M") + f"  ({job.source})\n")
        printer.text("-" * settings.printer_width + "\n")

    def _print_text_body(self, printer, job: PrintJob):
        if job.title:
            printer.set(align="center", bold=True, double_height=True, double_width=True)
            printer.text(job.title + "\n\n")
        size_map = {
            "normal": {"double_height": False, "double_width": False},
            "double_height": {"double_height": True, "double_width": False},
            "double_width": {"double_height": False, "double_width": True},
            "double": {"double_height": True, "double_width": True},
        }
        printer.set(
            align=job.align, bold=job.bold,
            underline=1 if job.underline else 0,
            **size_map.get(job.size, size_map["normal"]),
        )
        printer.text(job.text + "\n")

    def _prepare_image(self, image_bytes: bytes, max_width: int = 512) -> Image.Image:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        img = img.convert("1", dither=Image.FLOYDSTEINBERG)
        return img

    def _print_job(self, job: PrintJob):
        printer = self._connect()
        self._print_header(printer, job)

        if job.kind == "text":
            self._print_text_body(printer, job)
        elif job.kind == "image":
            if job.title:
                printer.set(align="center", bold=True, double_height=True, double_width=True)
                printer.text(job.title + "\n\n")
            try:
                img = self._prepare_image(job.image_bytes)
                printer.set(align="center")
                printer.image(img, center=True)
            except Exception as e:
                logger.exception(f"Erreur image: {e}")
                printer.text(f"[Erreur image: {e}]\n")
            if job.caption:
                printer.set(align="center", bold=False, double_height=False, double_width=False)
                printer.text("\n" + job.caption + "\n")
        elif job.kind == "qr":
            if job.title:
                printer.set(align="center", bold=True, double_height=True, double_width=True)
                printer.text(job.title + "\n\n")
            qr = qrcode.QRCode(box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(job.qr_data)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            if qr_img.width > 400:
                ratio = 400 / qr_img.width
                qr_img = qr_img.resize((400, int(qr_img.height * ratio)), Image.LANCZOS)
            qr_img = qr_img.convert("1")
            printer.set(align="center")
            printer.image(qr_img, center=True)
            printer.set(align="center", bold=False, double_height=False, double_width=False)
            printer.text("\n" + (job.caption or job.qr_data[:50]) + "\n")

        printer.set(align="left", bold=False, underline=0, double_height=False, double_width=False)
        printer.text("\n\n\n")
        try:
            printer.cut()
        except Exception:
            pass


printer = ThermalPrinter()
