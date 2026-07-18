from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pyvern.database import init_db, init_directories
from pyvern.routers import characters, chats, presets, providers, stream, personas, pages
from pyvern.logger import get_logger, DEBUG_MODE
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
    logger.info("Database initialized. Pyvern is ready.")
    yield
    logger.info("Pyvern shutting down.")


app = FastAPI(title="Pyvern", version="0.1.0", lifespan=lifespan)

if DEBUG_MODE:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.debug(f"{request.method} {request.url.path} - Status: {response.status_code} - {process_time:.4f}s")
        return response

app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(chats.router,      prefix="/api/chats",      tags=["chats"])
app.include_router(presets.router,    prefix="/api/presets",     tags=["presets"])
app.include_router(providers.router,  prefix="/api/providers",   tags=["providers"])
app.include_router(personas.router,   prefix="/api/personas",    tags=["personas"])
app.include_router(stream.router,     prefix="/api",             tags=["stream"])
app.include_router(pages.router)

app.mount("/assets",  CachedStaticFiles(directory="assets"),  name="assets")
app.mount("/static",  StaticFiles(directory="static"),  name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="Pyvern")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port)
