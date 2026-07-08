from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from src.config import settings
from src.lib.logging import configure_logging
from src.routers import admin_auth, admin_works, auth, oauth


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(debug=settings.debug)
    log = structlog.get_logger(__name__)
    if settings.env == "production" and not settings.resend_api_key.get_secret_value():
        log.warning("resend_api_key_missing_in_production")
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[
                StarletteIntegration(),
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
    yield


app = FastAPI(
    title="dweb API",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(admin_auth.router)
app.include_router(admin_works.router)


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI"}
