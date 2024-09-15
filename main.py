import asyncio
import logging
import pathlib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from textwrap import dedent

import magic
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from custom_logging import CustomizeLogger
from utils import cleanup_routine, config_observer, generate_table_html, start_paths, State

logger = logging.getLogger(__name__)
config_path = pathlib.Path("config.toml")
connections = {}
state = State(10, logger)


def identify_file(file_path: str):
    return magic.Magic(mime=True).from_file(file_path)


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
    """
                  ).lstrip("\n")


@app.get("/update", response_class=RedirectResponse)
async def update_paths():
    await start_paths(config_path, state)
    return RedirectResponse("/")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    dropdown = generate_table_html(state)
    return templates.TemplateResponse("index.html", {"request": request, "table_rows": dropdown})


@app.get("/gallery/{folder}", response_class=HTMLResponse)
async def gallery(request: Request, folder: str):  # NOQA
    return templates.TemplateResponse("gallery.html", {"request": request})


@app.websocket("/ws/{folder}")
async def websocket_endpoint(websocket: WebSocket, folder: str):
    await websocket.accept()
    client_id = str(uuid.uuid4())
    connections[client_id] = websocket
    try:
        root_folder = state.root_folder_files.get(folder)
        recursive_folder = state.recursive_folders.get(folder)
        if root_folder or recursive_folder:
            folder_files = root_folder or recursive_folder
            for file in folder_files:
                if mime := identify_file(str(file.resolve())):
                    if "text" not in mime:
                        await asyncio.sleep(0.5)
                        await websocket.send_text(f"{file.resolve()}\t{mime}\n")

    except WebSocketDisconnect:
        del connections[client_id]


@app.get("/{folder_str}/{path_str:path}", response_class=HTMLResponse)
async def get_files(request: Request, folder_str: str, path_str: str):
    folder = state.root_folder_files.get(folder_str) or state.recursive_folders.get(folder_str)
    if not folder:
        files = state.find_files(request.url.path.split("/")[-1])
        if files:
            return StreamingResponse(files[0].open("rb"), media_type=identify_file(str(files[0].resolve())))
        raise HTTPException(status_code=404, detail="Folder does not exist.")

    files = state.find_files(path_str)
    if not files:
        raise HTTPException(status_code=404, detail="File does not exist.")
    if len(files) > 1:
        files_html = "\n".join([
                f"""<li><a href='{file.resolve()}'>
                <img src=\"{str(request.base_url)}{str(file.resolve()).replace("/", "", 1)}\" style=\"width: 200;\">
                </a></li>""" for file in files])
        return HTMLResponse(f"<p>More than one file found with name \"{path_str}\".</p><ul>{files_html}</ul>")
    file = files[0]
    if file.exists():
        return RedirectResponse(str(file.resolve()))
    else:
        raise HTTPException(status_code=404, detail="File or folder deleted since last time I checked.")


if __name__ == "__main__":
    # uvicorn.run("main:app", host="0.0.0.0", port=4324, log_level="info", reload=True)
    uvicorn.run("main:app", host="0.0.0.0", port=4324, log_level="info", workers=4)
