from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import audio, dictionaries, health, options, rules, synthesize, transform
from app.config import PROJECT_ROOT, Settings, load_settings
from app.core.audio_cache import AudioCache
from app.core.dictionary_store import DictionaryStore
from app.core.gnani_tts import TimbreClient
from app.errors import AppError, InternalError, NotFound, ValidationError

logger = logging.getLogger("app")

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = settings or load_settings()
    app = FastAPI(
        title="Timbre Pronunciation Studio",
        version=__version__,
        description=(
            "Application-side pronunciation rules, preview and before/after audio "
            "for Gnani Timbre. Not native phoneme control."
        ),
    )

    app.state.settings = settings
    app.state.store = DictionaryStore(settings.data_dir)
    app.state.cache = AudioCache(settings.data_dir / "audio")
    app.state.tts = TimbreClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    _register_error_handlers(app)
    _register_routes(app, settings)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "issue": error["type"],
            }
            for error in exc.errors()
        ]
        payload = {
            "success": False,
            "error": {
                "type": "VALIDATION_ERROR",
                "message": "The request body is invalid.",
                "details": details,
            },
        }
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code == 404:
            error: AppError = NotFound("Not found.")
        elif exc.status_code in (401, 403, 405, 409, 429):
            error = ValidationError(str(exc.detail))
            error.status_code = exc.status_code
        else:
            error = InternalError("An unexpected error occurred.")
            error.status_code = exc.status_code
        return JSONResponse(status_code=error.status_code, content=error.to_payload())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        error = InternalError("An unexpected error occurred.")
        return JSONResponse(status_code=error.status_code, content=error.to_payload())


def _register_routes(app: FastAPI, settings: Settings) -> None:
    for module in (health, options, dictionaries, rules, transform, synthesize, audio):
        app.include_router(module.router, prefix="/api")

    if not FRONTEND_DIST.is_dir():
        return

    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index_file = FRONTEND_DIST / "index.html"
    if not index_file.is_file():
        return

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        # The SPA catch-all is registered last, but it would otherwise swallow
        # an unknown /api path and answer it with index.html and a 200. The
        # documented contract is a 404 with the JSON error envelope, so API
        # paths never fall through to the shell.
        if full_path == "api" or full_path.startswith("api/"):
            raise NotFound("Not found.")

        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index_file)


if __name__ == "__main__":  # pragma: no cover - manual entry point
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
