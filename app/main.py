"""FastAPI application entry point.

Architecture:
    Telegram -> FastAPI -> Business services -> MongoDB
                              |
                              +-> AI services (Sarvam / Gemini / Groq / GPT-OSS)

FastAPI is the backend and also serves the small HTML auth pages. There is no
React or Next.js front-end.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth as auth_api
from app.api import demand as demand_api
from app.api import health as health_api
from app.api import requests as requests_api
from app.api import shops as shops_api
from app.bot.bot import start_bot, stop_bot
from app.config.settings import settings
from app.database.indexes import create_indexes
from app.database.mongo import close_mongo_connection, connect_to_mongo, mongo
from app.services.scheduler import start_scheduler, stop_scheduler
from app.utils.logging import bind_request_id, get_logger, new_request_id, setup_logging

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (demo_mode=%s)", settings.APP_NAME, settings.DEMO_MODE)

    connected = await connect_to_mongo()
    if connected:
        await create_indexes()
    else:
        logger.error("Running WITHOUT a database — most features will be unavailable")

    bot_task = None
    if settings.RUN_BOT:
        try:
            bot_task = await start_bot()
        except Exception as exc:
            logger.error("Telegram bot failed to start: %s", exc)

    scheduler = None
    try:
        scheduler = start_scheduler()
    except Exception as exc:
        logger.warning("Scheduler failed to start: %s", exc)

    yield

    if bot_task is not None:
        await stop_bot()
    if scheduler is not None:
        stop_scheduler()
    await close_mongo_connection()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered hyperlocal commerce without mandatory inventory.",
    version="1.0.0",
    lifespan=lifespan,
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(health_api.router)
app.include_router(auth_api.router)
app.include_router(shops_api.router)
app.include_router(requests_api.router)
app.include_router(demand_api.router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = new_request_id("HTTP")
    bind_request_id(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/auth/login")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Never leak internals; HTML pages get an HTML error, the API gets JSON.
    if request.url.path.startswith("/auth"):
        from app.api.deps import templates
        return templates.TemplateResponse(
            request=request, name="error.html",
            context={"message": str(exc.detail), "app_name": settings.APP_NAME},
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Some fields were invalid. Please check and try again."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error: %s", exc.__class__.__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again."},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.APP_HOST, port=settings.APP_PORT,
        reload=settings.DEMO_MODE, log_level=settings.LOG_LEVEL.lower(),
    )
