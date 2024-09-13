import logging
import pathlib
from contextlib import asynccontextmanager
from pathlib import Path
from textwrap import dedent
from typing import Dict
import asyncio
import toml
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from custom_logging import CustomizeLogger
from utils import generate_paths, start_observers, stop_observers, generate_root_paths, update_paths, State


class URLListSchema(BaseModel):
    urls: list[str]


logger = logging.getLogger(__name__)
config_path = Path(__file__).with_name("logging_config.json")

# paths: dict[str, dict[str, list[pathlib.Path | str]]] = {}
connections: Dict[str, WebSocket] = {}
# observers = []

state = State()

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = toml.load('config.toml')

    # Inicializa paths e observers no estado compartilhado
    state.paths = await generate_paths(config.get("paths"))
    state.observers = start_observers(config.get("paths"), state.paths)

    root_paths = config.get("root_paths")
    if root_paths:
        state.paths.update(await generate_root_paths(config.get("root_paths")))
        state.observers.append(start_observers(config.get("root_paths"), state.paths))

    # Cria uma task assíncrona de update_paths
    asyncio.create_task(update_paths(logger, state))

    yield
    stop_observers(state.observers)


app = FastAPI(lifespan=lifespan)
app.logger = CustomizeLogger.make_logger(config_path)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico")
async def get_favicon():
    return app.url_path_for('static', path='favicon.gif')


@app.get("/robots.txt", response_class=PlainTextResponse)
async def get_robot():
    return dedent("""
    User-agent: *
    Disallow: /
    """).lstrip("\n")


async def link_stream(folder: str):
    for img_path in state.paths[folder]:
        img, file_type = state.paths[folder][img_path]
        yield f"/{folder}/{img_path}\t{file_type}\n"


@app.get("/", response_class=HTMLResponse)
async def gallery(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "paths": state.paths})


@app.get("/path/{folder}", response_class=HTMLResponse)
async def path_view(request: Request, folder: str):
    return templates.TemplateResponse("gallery.html", {"request": request})


@app.websocket("/ws/{folder}")
async def websocket_endpoint(websocket: WebSocket, folder: str):
    await websocket.accept()
    connections[folder] = websocket
    try:
        if folder in state.paths:
            for img_path in state.paths[folder]:
                img, file_type = state.paths[folder][img_path]
                await websocket.send_text(f"/{folder}/{img_path}\t{file_type}\n")
    except WebSocketDisconnect:
        del connections[folder]


@app.get("/{folder_str}/{path_str:path}", response_class=HTMLResponse)
@app.get("/path/{folder_str}/{path_str:path}", response_class=HTMLResponse)
async def get_files(request: Request, folder_str: str, path_str: str):
    folder = state.paths.get(folder_str)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder dont exist.")
    file = folder.get(path_str)
    if not file:
        raise HTTPException(status_code=404, detail="File dont exist.")

    if "/path/" in request.url.path:
        return RedirectResponse(f"/{folder_str}/{path_str}")
    
    return StreamingResponse(file[0].open("rb"), media_type=file[1])


if __name__ == "__main__":
    # uvicorn.run("main:app", host="0.0.0.0", port=5000, log_level="info", reload=True)
    uvicorn.run("main:app", host="0.0.0.0", port=5000, log_level="info", workers=4)
