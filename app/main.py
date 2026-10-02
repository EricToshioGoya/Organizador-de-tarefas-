"""Aplicação FastAPI: API REST + front end estático (PWA) servido pelo mesmo processo."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import routes_accounts, routes_metrics, routes_tasks, routes_tools
from .config import WEB_DIR, get_settings
from .domain.rules import DomainError
from .integrations.scheduler import run_scheduler
from .store.db import init_db

log = logging.getLogger("organizador")

FIELD_LABELS = {
    "title": "título",
    "name": "nome",
    "difficulty": "dificuldade",
    "priority": "prioridade",
    "due_date": "data de entrega",
    "target_date": "data-alvo",
    "phase": "fase",
    "due_reason": "motivo do adiamento",
    "role": "perfil",
    "text": "texto",
    "task_ids": "tarefas",
    "period": "período",
}


def _inline_script_hashes() -> list[str]:
    """Hash CSP dos scripts inline do index.html (o import map precisa ser inline)."""
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        return []
    index = index_file.read_text(encoding="utf-8")
    hashes = []
    for body in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", index, flags=re.S):
        digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        hashes.append(f"'sha256-{digest}'")
    return hashes


def _precache_manifest() -> tuple[list[str], str]:
    """Arquivos do app para o service worker e uma versão que muda quando qualquer um deles muda."""
    files = ["/"]
    digest = hashlib.sha256()
    for path in sorted(WEB_DIR.rglob("*")):
        if not path.is_file() or path.name == "sw.js" or "licenses" in path.parts:
            continue
        relative = path.relative_to(WEB_DIR).as_posix()
        files.append("/" + relative)
        stat = path.stat()
        digest.update(f"{relative}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return files, digest.hexdigest()[:12]


def _csp() -> str:
    scripts = " ".join(["'self'", *_inline_script_hashes()])
    return (
        "default-src 'self'; "
        f"script-src {scripts}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "worker-src 'self'; "
        "manifest-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.db_path)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler(settings, stop)) if settings.scheduler_enabled else None
    log.info("Dados em %s", settings.data_dir)
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            await task


def create_app() -> FastAPI:
    app = FastAPI(
        title="Organizador de Tarefas — API",
        version=__version__,
        description=(
            "API REST do Organizador de Tarefas. Não há autenticação por decisão de projeto (RNF18): "
            "a conta em uso é informada no cabeçalho `X-Account-Id`. Toda alteração é gravada como evento "
            "imutável (RNF22); reenvios com o mesmo `Idempotency-Key` não duplicam efeitos."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    csp = _csp()

    @app.middleware("http")
    async def security_and_cache_headers(request: Request, call_next):
        response: Response = await call_next(request)
        path = request.url.path
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif path.startswith("/vendor/"):
            response.headers.setdefault("Cache-Control", "public, max-age=604800")
        else:
            response.headers.setdefault("Cache-Control", "no-cache")
        if path in ("/", "/index.html"):
            response.headers["Content-Security-Policy"] = csp
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        fields = []
        for error in errors:
            location = [str(p) for p in error.get("loc", []) if p not in ("body", "query", "path")]
            if location:
                fields.append(FIELD_LABELS.get(location[-1], location[-1]))
        message = "Dados inválidos" + (f": verifique {', '.join(dict.fromkeys(fields))}." if fields else ".")
        return JSONResponse({"detail": message, "code": "validacao", "errors": errors}, status_code=422)

    app.include_router(routes_accounts.router)
    app.include_router(routes_tasks.router)
    app.include_router(routes_metrics.router)
    app.include_router(routes_tools.router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_not_found(path: str):
        return JSONResponse({"detail": "Rota não encontrada.", "code": "nao_encontrado"}, status_code=404)

    @app.get("/sw.js", include_in_schema=False)
    async def service_worker():
        files, version = _precache_manifest()
        body = (WEB_DIR / "sw.js").read_text(encoding="utf-8")
        body = body.replace("__VERSION__", version).replace("__PRECACHE__", json.dumps(files))
        return Response(
            body,
            media_type="text/javascript",
            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
        )

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest():
        return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
