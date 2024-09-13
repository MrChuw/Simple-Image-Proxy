import logging
import pathlib
from contextlib import asynccontextmanager
from pathlib import Path
from textwrap import dedent
from typing import Dict
import asyncio
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from custom_logging import CustomizeLogger
from utils import cleanup_routine, State, config_observer, start_paths, force_update
import magic


logger = logging.getLogger(__name__)
config_path = pathlib.Path("config.toml")
connections: Dict[str, WebSocket] = {}
state = State(5)


def identify_file(file_path: pathlib.Path):
    return magic.Magic(mime=True).from_file(str(file_path))


@asynccontextmanager
async def lifespan(app: FastAPI):  # NOQA
    asyncio.create_task(config_observer(logger, config_path, state))  # NOQA
    asyncio.create_task(start_paths(config_path, state))  # NOQA
    asyncio.create_task(cleanup_routine(logger, config_path, state))  # NOQA
    yield


app = FastAPI(lifespan=lifespan)
app.logger = CustomizeLogger.make_logger(Path(__file__).with_name("logging_config.json"))
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


@app.get("/update", response_class=RedirectResponse)
async def update_paths():
    await force_update(state, config_path)
    return RedirectResponse("/")


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
                if mime := identify_file(state.paths[folder][img_path]):
                    if "text" not in mime:
                        await websocket.send_text(f"/{folder}/{img_path}\t{mime}\n")
    except WebSocketDisconnect:
        del connections[folder]


@app.get("/{folder_str}/{path_str:path}", response_class=HTMLResponse)
@app.get("/path/{folder_str}/{path_str:path}", response_class=RedirectResponse)
async def get_files(request: Request, folder_str: str, path_str: str):
    folder = state.paths.get(folder_str)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder dont exist.")

    file = folder.get(path_str)
    if not file:
        raise HTTPException(status_code=404, detail="File dont exist.")
    elif "/path/" in request.url.path:
        return RedirectResponse(f"/{folder_str}/{path_str}")
    elif file.exists():
        return StreamingResponse(file.open("rb"), media_type=identify_file(file))
    else:
        raise HTTPException(status_code=404, detail="File or folder deleted since last time I checked.")




if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=4324, log_level="info", reload=True)
    # uvicorn.run("main:app", host="0.0.0.0", port=4324, log_level="info", workers=1)
