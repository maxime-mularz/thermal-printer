import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException, Header, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from .config import settings
from .printer import printer, PrintJob
from .channels import telegram_bot
from . import scheduler
from .history import get_history
from .scheduler import print_weather_now

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("telegram.ext.Updater").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await printer.start()
    if settings.telegram_bot_token:
        await telegram_bot.start()
    await scheduler.start()
    logger.info(f"Service pret sur {settings.api_host}:{settings.api_port}")
    yield
    await scheduler.stop()
    if settings.telegram_bot_token:
        await telegram_bot.stop()
    await printer.stop()


app = FastAPI(title="Thermal Printer Service", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, limit: int = 50):
    items = get_history(min(limit, 200))
    return templates.TemplateResponse("history.html", {"request": request, "items": items})


@app.post("/print", response_class=HTMLResponse)
async def web_print(
    request: Request,
    text: str = Form(""),
    title: str = Form(""),
    caption: str = Form(""),
    bold: bool = Form(False),
    underline: bool = Form(False),
    align: str = Form("left"),
    size: str = Form("normal"),
    qr_data: str = Form(""),
    image: UploadFile | None = File(None),
):
    client_ip = request.client.host if request.client else "unknown"
    source = f"web/{client_ip}"

    if qr_data.strip():
        job = PrintJob(kind="qr", qr_data=qr_data.strip(), title=title or None,
                       caption=caption or None, source=source)
    elif image and image.filename:
        image_bytes = await image.read()
        if not image_bytes:
            return templates.TemplateResponse("index.html", {"request": request, "error": "Image vide."})
        job = PrintJob(kind="image", image_bytes=image_bytes, title=title or None,
                       caption=caption or text or None, source=source)
    elif text.strip():
        job = PrintJob(kind="text", text=text, title=title or None, source=source,
                       bold=bold, underline=underline, align=align, size=size)
    else:
        return templates.TemplateResponse("index.html", {"request": request,
                                                          "error": "Renseigne un message, une image ou un QR."})

    accepted, msg = await printer.submit(job)
    if accepted:
        return templates.TemplateResponse("index.html", {"request": request, "success": "Envoye !"})
    return templates.TemplateResponse("index.html", {"request": request, "error": msg})


class PrintRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    title: str | None = None
    bold: bool = False
    underline: bool = False
    align: str = Field("left", pattern="^(left|center|right)$")
    size: str = Field("normal", pattern="^(normal|double_height|double_width|double)$")
    source: str = "api"


class QRRequest(BaseModel):
    data: str = Field(..., min_length=1, max_length=2000)
    title: str | None = None
    caption: str | None = None
    source: str = "api"


def _check_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Token manquant")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.api_token:
        raise HTTPException(403, "Token invalide")


@app.post("/api/print")
async def api_print(req: PrintRequest, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    job = PrintJob(kind="text", text=req.text, title=req.title, source=req.source,
                   bold=req.bold, underline=req.underline, align=req.align, size=req.size)
    accepted, msg = await printer.submit(job)
    if not accepted:
        raise HTTPException(429, msg)
    return JSONResponse({"status": "queued"})


@app.post("/api/print-image")
async def api_print_image(image: UploadFile = File(...), title: str = Form(""),
                          caption: str = Form(""), source: str = Form("api"),
                          authorization: str | None = Header(default=None)):
    _check_token(authorization)
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Image vide")
    accepted, msg = await printer.submit(PrintJob(
        kind="image", image_bytes=image_bytes, title=title or None,
        caption=caption or None, source=source))
    if not accepted:
        raise HTTPException(429, msg)
    return JSONResponse({"status": "queued"})


@app.post("/api/print-qr")
async def api_print_qr(req: QRRequest, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    accepted, msg = await printer.submit(PrintJob(
        kind="qr", qr_data=req.data, title=req.title, caption=req.caption, source=req.source))
    if not accepted:
        raise HTTPException(429, msg)
    return JSONResponse({"status": "queued"})


@app.post("/api/weather")
async def api_weather(authorization: str | None = Header(default=None)):
    _check_token(authorization)
    await print_weather_now(source="scheduled/meteo-api")
    return JSONResponse({"status": "queued"})


@app.get("/api/history")
async def api_history(limit: int = 20):
    return {"items": get_history(min(limit, 200))}


@app.get("/api/health")
async def health():
    return {"status": "ok", "printer_type": settings.printer_type}
