import hashlib
import shutil
import stat
import time
from contextlib import asynccontextmanager
from email.utils import formatdate
from pathlib import Path

import anyio
import aiosqlite
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from focus.core.database import get_db, init_db, init_directories
from focus.core.logger import get_logger
from focus.core.paths import CHARACTERS_DIR, PERSONAS_DIR
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
async def clean_database(db: aiosqlite.Connection = Depends(get_db)):
    counts = {}

    deleted_char_ids = {r[0] async for r in await db.execute("SELECT id FROM characters WHERE is_deleted = 1")}
    deleted_persona_ids = {r[0] async for r in await db.execute("SELECT id FROM personas WHERE is_deleted = 1")}

    counts["chats"] = (
        await db.execute(
            "DELETE FROM chats WHERE is_deleted = 1 OR character_id IN (SELECT id FROM characters WHERE is_deleted = 1)"
        )
    ).rowcount

    counts["characters"] = (await db.execute("DELETE FROM characters WHERE is_deleted = 1")).rowcount

    counts["personas"] = (await db.execute("DELETE FROM personas WHERE is_deleted = 1")).rowcount

    counts["block_images"] = (
        await db.execute(
            """
        DELETE FROM block_images WHERE block_id NOT IN (
            SELECT id FROM preset_blocks
        ) AND block_id NOT IN (
            SELECT id FROM char_blocks
        ) AND block_id NOT IN (
            SELECT id FROM characters
        ) AND block_id NOT IN (
            SELECT id FROM personas
        )
    """
        )
    ).rowcount

    counts["attachments"] = (await db.execute("DELETE FROM message_attachments WHERE message_id IS NULL")).rowcount

    await db.commit()

    dirs_purged = 0
    for char_id in deleted_char_ids:
        char_dir = CHARACTERS_DIR / char_id
        if char_dir.exists():
            shutil.rmtree(char_dir, ignore_errors=True)
            dirs_purged += 1
    counts["char_dirs_purged"] = dirs_purged

    dirs_purged = 0
    for persona_id in deleted_persona_ids:
        persona_dir = PERSONAS_DIR / persona_id
        if persona_dir.exists():
            shutil.rmtree(persona_dir, ignore_errors=True)
            dirs_purged += 1
    counts["persona_dirs_purged"] = dirs_purged

    orphaned_dirs = 0
    if CHARACTERS_DIR.exists():
        for entry in CHARACTERS_DIR.iterdir():
            if entry.is_dir() and len(entry.name) == 36:
                async with db.execute("SELECT 1 FROM characters WHERE id = ?", (entry.name,)) as cur:
                    if not await cur.fetchone():
                        shutil.rmtree(entry, ignore_errors=True)
                        orphaned_dirs += 1
    if PERSONAS_DIR.exists():
        for entry in PERSONAS_DIR.iterdir():
            if entry.is_dir() and len(entry.name) == 36:
                async with db.execute("SELECT 1 FROM personas WHERE id = ?", (entry.name,)) as cur:
                    if not await cur.fetchone():
                        shutil.rmtree(entry, ignore_errors=True)
                        orphaned_dirs += 1
    counts["orphaned_dirs_purged"] = orphaned_dirs

    nested = Path("assets") / "assets"
    if nested.exists():
        shutil.rmtree(nested, ignore_errors=True)
        counts["nested_assets_purged"] = 1

    await db.execute("VACUUM")
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
