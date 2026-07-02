import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .admin_routes import router as admin_router
from .config import get_settings
from .database import ensure_schema, wait_for_db
from .dlq_worker import run_dlq_worker
from .email_service import get_email_config, is_email_enabled
from .errors import register_exception_handlers
from .logging_filters import PIIRedactionFilter
from .metrics import setup_metrics
from .middleware import RequestContextMiddleware
from .models import Base
from .rate_limit import limiter
from .routes import router

logger = logging.getLogger("app")


def _configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()

    if settings.log_json:
        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    payload["exception"] = self.formatException(record.exc_info)
                return json.dumps(payload)

        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        )

    handler.addFilter(PIIRedactionFilter())
    root.addHandler(handler)
    root.setLevel(level)


def _configure_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn.strip():
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            environment=settings.app_env,
        )
        logger.info("Sentry initialized")
    except Exception:
        logger.exception("Sentry initialization failed")


_configure_logging()
_configure_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    for warning in settings.validate_startup():
        logger.warning("Config: %s", warning)

    logger.info("Waiting for database...")
    wait_for_db()
    logger.info("Creating database tables (if missing)...")
    ensure_schema(Base)

    email = get_email_config()
    if email["enabled"] and not email["configured"]:
        logger.warning("EMAIL_ENABLED is on but SMTP is incomplete")
    elif is_email_enabled():
        logger.info("Booking confirmation emails are enabled (SMTP: %s)", email["smtp_host"])
    else:
        logger.info("Booking confirmation emails are disabled")

    dlq_task = asyncio.create_task(run_dlq_worker())
    logger.info("Startup complete (env=%s). DLQ worker running.", settings.app_env)
    yield
    dlq_task.cancel()
    logger.info("Shutdown complete.")


settings = get_settings()

app = FastAPI(
    title="AI Receptionist Prototype API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)
setup_metrics(app)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(admin_router)
