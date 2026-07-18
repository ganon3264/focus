from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pyvern.database import init_db
from pyvern.routers import characters, chats, presets, providers, stream, personas, pages


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Pyvern", version="0.1.0", lifespan=lifespan)

app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(chats.router,      prefix="/api/chats",      tags=["chats"])
app.include_router(presets.router,    prefix="/api/presets",     tags=["presets"])
app.include_router(providers.router,  prefix="/api/providers",   tags=["providers"])
app.include_router(personas.router,   prefix="/api/personas",    tags=["personas"])
app.include_router(stream.router,     prefix="/api",             tags=["stream"])
app.include_router(pages.router)

app.mount("/assets",  StaticFiles(directory="assets"),  name="assets")
app.mount("/static",  StaticFiles(directory="static"),  name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")
