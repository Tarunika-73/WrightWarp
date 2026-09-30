"""Consistent API errors.

Every error response has the same shape::

    {"detail": "<human-readable message>",
     "error": {"code": "NOT_FOUND", "message": "...", "request_id": "…", "details": …}}

``detail`` is kept at the top level for compatibility with FastAPI's
default shape (and existing clients/tests). Stack traces never reach the
client: unexpected exceptions are logged with a request id and answered
with a generic 500. Database errors are logged by exception class only,
since some driver messages echo connection details.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from starlette.exceptions import HTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class IndexNotAvailableError(AppError):
    status_code = 503
    code = "INDEX_NOT_COMPUTED"


class IndexCalculationFailed(AppError):
    status_code = 500
    code = "INDEX_CALCULATION_ERROR"


class SourceUnavailableError(AppError):
    status_code = 409
    code = "SOURCE_UNAVAILABLE"


class CollectionFailedError(AppError):
    status_code = 502
    code = "COLLECTION_ERROR"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ServiceMisconfiguredError(AppError):
    status_code = 503
    code = "NOT_CONFIGURED"


_HTTP_CODES = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 409: "CONFLICT", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED"}


def _request_id(request: Request) -> str:
    return request.headers.get("x-vercel-id") or request.headers.get("x-request-id") or uuid.uuid4().hex[:16]


def _body(code: str, message: str, request: Request, details: object = None) -> dict:
    error = {"code": code, "message": message, "request_id": _request_id(request)}
    if details is not None:
        error["details"] = details
    return {"detail": message, "error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, request, exc.details))

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_body(code, message, request), headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse(status_code=422, content=_body("VALIDATION_ERROR", "Request validation failed", request, details))

    @app.exception_handler(PyMongoError)
    async def _db_error(request: Request, exc: PyMongoError):
        logger.error("database_error path=%s error=%s request_id=%s", request.url.path, type(exc).__name__, _request_id(request))
        return JSONResponse(status_code=503, content=_body("DATABASE_ERROR", "Database temporarily unavailable", request))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        request_id = _request_id(request)
        logger.exception("unhandled_error path=%s request_id=%s", request.url.path, request_id)
        return JSONResponse(status_code=500, content=_body("INTERNAL_ERROR", "Internal server error", request))
