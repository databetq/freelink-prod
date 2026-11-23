import logging
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.admin import router as admin_router
from app.admin_auth import router as admin_auth_router
from app.auth import router as auth_router
from app.config import get_settings
from app.db import get_engine
from app.disputes import router as disputes_router
from app.escrow import router as escrow_router
from app.marketplace import router as marketplace_router
from app.messages import router as messages_router
from app.notifications import router as notifications_router
from app.password_auth import router as password_auth_router
from app.profiles import router as profiles_router
from app.support import router as support_router
from app.transactions import router as transactions_router
from app.wallet import router as wallet_router


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]


app = FastAPI(title="Freelink REST API")
settings = get_settings()
logger = logging.getLogger("uvicorn.error")
if settings.session_secret.get_secret_value():
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie="freelink_oauth",
        max_age=600,
        https_only=settings.session_cookie_secure,
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)
app.include_router(auth_router)
app.include_router(password_auth_router)
app.include_router(wallet_router)
app.include_router(admin_auth_router)
app.include_router(admin_router)
app.include_router(disputes_router)
app.include_router(marketplace_router)
app.include_router(escrow_router)
app.include_router(profiles_router)
app.include_router(notifications_router)
app.include_router(messages_router)
app.include_router(transactions_router)
app.include_router(support_router)


@app.middleware("http")
async def log_request(request: Request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        # Replies depend on the session, so the CDN in front of the API must not keep them.
        response.headers.setdefault("Cache-Control", "no-store")
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", "<unmatched>")
        logger.info(
            "request_id=%s method=%s route=%s status=%s duration_ms=%.1f",
            request_id, request.method, route, status, (perf_counter() - started) * 1000,
        )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    payload = exc.detail if isinstance(exc.detail, dict) else {
        "message": exc.detail, "code": f"HTTP_{exc.status_code}",
    }
    return JSONResponse(payload, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = {".".join(map(str, item["loc"])): item["msg"] for item in exc.errors()}
    return JSONResponse({
        "message": "ข้อมูลที่ส่งมาไม่ถูกต้อง", "code": "VALIDATION_ERROR", "errors": errors,
    }, status_code=422)


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logger.error("database_operation_failed error_type=%s", type(exc).__name__)
    return JSONResponse({
        "message": "ดำเนินการกับฐานข้อมูลไม่สำเร็จ", "code": "DATABASE_ERROR",
    }, status_code=503)


@app.get("/health", response_model=Health, responses={503: {"model": Health}})
def health(response: Response) -> Health:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return Health(status="unavailable", database="unavailable")

    return Health(status="ok", database="ok")
