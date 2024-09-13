import asyncio
import pathlib

import toml
import filetype
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class State:
    def __init__(self):
        self.paths: dict[str, dict[str, list[pathlib.Path | str]]]  = {}
        self.observers = []


def process_file(file_path):
    kind = filetype.guess(file_path)
    if kind is None:
        return None
    return str(kind.mime)


async def process_files_in_thread(file_path):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, process_file, file_path)


async def generate_paths(path_list: list[str]) -> dict[str, dict[str, dict[pathlib.Path, str]]]:
    file_dict = {}
    tasks = []

    for path in path_list:
        root_path = pathlib.Path(path)
        if root_path.stem not in file_dict:
            file_dict[root_path.stem] = {}
        for file_path in root_path.rglob('*'):
            if file_path.is_file():
                tasks.append(asyncio.create_task(process_files_in_thread(file_path)))
                file_dict[root_path.stem][str(file_path.relative_to(root_path))] = file_path
    results = await asyncio.gather(*tasks)
    task_idx = 0
    for path in path_list:
        root_path = pathlib.Path(path)
        for file_path in root_path.rglob('*'):
            if file_path.is_file():
                mime_type = results[task_idx]
                if mime_type and "dng" not in mime_type:
                    file_dict[root_path.stem][str(file_path.relative_to(root_path))] = [file_path, mime_type]
                else:
                    del file_dict[root_path.stem][str(file_path.relative_to(root_path))]
                task_idx += 1

    return file_dict


async def generate_root_paths(root_path_list: list[str]):
    paths_list = []
    for path in root_path_list:
        root_path = pathlib.Path(path)
        for subpath in root_path.iterdir():
            paths_list.append(str(subpath))
    return await generate_paths(paths_list)


class Handler(FileSystemEventHandler):
    def __init__(self, paths):
        self.paths = paths

    def on_modified(self, event):
        print(f"Arquivo {event.src_path} foi modificado!")
        self.paths.update(asyncio.run(generate_paths([event.src_path])))


def start_observers(paths_strings, paths_dict):
    observers = []
    for path in paths_strings:
        event_handler = Handler(paths_dict)
        observer = Observer()
        observer.schedule(event_handler, path=path, recursive=True)
        observer.start()
        observers.append(observer)
    return observers


def stop_observers(observers):
    for observer in observers:
        observer.stop()
        observer.join()


async def update_paths(logger, state: State):
    logger.info("Start path cleaner.")

    while True:
        await asyncio.sleep(10)
        logger.info("Updating paths.")
        # logger.info(state.observers)
        stop_observers(state.observers)
        config = toml.load('config.toml')

        state.paths = await generate_paths(config.get("paths"))
        state.observers = start_observers(config.get("paths"), state.paths)

        root_paths = config.get("root_paths")
        if root_paths:
            state.paths.update(await generate_root_paths(config.get("root_paths")))
            state.observers.append(start_observers(config.get("root_paths"), state.paths))







