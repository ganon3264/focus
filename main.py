import hashlib
import stat
import time
from contextlib import asynccontextmanager
from email.utils import formatdate

import anyio
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from focus.core.database import get_db, init_db, init_directories
from focus.core.logger import get_logger
from focus.db.cleanup import clean_database as db_cleanup
from focus.routers import (
    backup,
    characters,
    chats,
    exchange,
    pages,
    personas,
    presets,
    providers,
    settings,
    stream,
    tools,
)


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        request_headers = Headers(scope=scope)
        if_none_match = request_headers.get("if-none-match")
        if_modified_since = request_headers.get("if-modified-since")

        if if_none_match or if_modified_since:
            try:
                full_path, stat_result = await anyio.to_thread.run_sync(self.lookup_path, path)
                if stat_result and stat.S_ISREG(stat_result.st_mode):
                    etag_base = str(stat_result.st_mtime) + "-" + str(stat_result.st_size)
                    etag = f'"{hashlib.md5(etag_base.encode(), usedforsecurity=False).hexdigest()}"'
                    last_modified = formatdate(stat_result.st_mtime, usegmt=True)

                    if (if_none_match and if_none_match == etag) or \
                       (if_modified_since and if_modified_since == last_modified):
                        return Response(
                            status_code=304,
                            headers={
                                "Cache-Control": "public, max-age=31536000, immutable",
                                "ETag": etag,
                                "Last-Modified": last_modified,
                            }
                        )
            except Exception:
                pass

        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


init_directories()

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized. Focus is ready.")
    yield
    logger.info("Focus shutting down.")


app = FastAPI(title="Focus", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    status = response.status_code
    color = "\x1b[32m" if status < 300 else "\x1b[36m" if status < 400 else "\x1b[33m" if status < 500 else "\x1b[31m"
    msg = "%s %s - Status: %s%d\x1b[0m - %.4fs"
    if status >= 500:
        logger.error(msg, request.method, request.url.path, color, status, process_time)
    elif status >= 400:
        logger.warning(msg, request.method, request.url.path, color, status, process_time)
    else:
        logger.debug(msg, request.method, request.url.path, color, status, process_time)
    return response


app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(chats.router, prefix="/api/chats", tags=["chats"])
app.include_router(presets.router, prefix="/api/presets", tags=["presets"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(personas.router, prefix="/api/personas", tags=["personas"])
app.include_router(stream.router, prefix="/api", tags=["stream"])
app.include_router(pages.router)
app.include_router(backup.router, prefix="/api/backups", tags=["backups"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(tools.router, prefix="/api", tags=["tools"])
app.include_router(exchange.router, prefix="/api", tags=["import-export"])

app.mount("/assets", CachedStaticFiles(directory="assets"), name="assets")
app.mount("/static", CachedStaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/chat")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.svg")


@app.post("/api/db/clean")
async def clean_database_endpoint(_db=Depends(get_db)):
    counts = await db_cleanup(_db)
    await _db.commit()
    return counts


if __name__ == "__main__":
    import argparse

    import uvicorn

    from focus.core.logger import UvicornFormatter

    uvicorn.config.LOGGING_CONFIG["formatters"]["default"]["()"] = UvicornFormatter

    parser = argparse.ArgumentParser(description="Focus")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, access_log=False)
