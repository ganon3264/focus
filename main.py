from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from focus.database import init_db, init_directories
from focus.routers import characters, chats, presets, providers, stream, personas, pages, backup, exchange
from focus.logger import get_logger
import time


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

# Ensure directories exist before mounting static files
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
    logger.info(f"{request.method} {request.url.path} - Status: {color}{status}\x1b[0m - {process_time:.4f}s")
    return response

app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(chats.router,      prefix="/api/chats",      tags=["chats"])
app.include_router(presets.router,    prefix="/api/presets",     tags=["presets"])
app.include_router(providers.router,  prefix="/api/providers",   tags=["providers"])
app.include_router(personas.router,   prefix="/api/personas",    tags=["personas"])
app.include_router(stream.router,     prefix="/api",             tags=["stream"])
app.include_router(pages.router)
app.include_router(backup.router,   prefix="/api/backups",  tags=["backups"])
app.include_router(exchange.router, prefix="/api",           tags=["import-export"])

app.mount("/assets",  CachedStaticFiles(directory="assets"),  name="assets")
app.mount("/static",  StaticFiles(directory="static"),  name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.svg")


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="Focus")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, access_log=False)
