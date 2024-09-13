
import asyncio
import pathlib
import toml
import filetype
import hashlib

pathtype = dict[str, dict[str, pathlib.Path]]


class State:
    def __init__(self, cooldown_time: float):
        self.paths: pathtype = {}
        self.config_hash: str = ""

        self.cooldown_time = cooldown_time
        self._last_call_time = None

    async def _cooldown(self):
        if self._last_call_time is not None:
            elapsed_time = asyncio.get_event_loop().time() - self._last_call_time
            if elapsed_time < self.cooldown_time:
                await asyncio.sleep(self.cooldown_time - elapsed_time)
        self._last_call_time = asyncio.get_event_loop().time()

    async def call_function_with_cooldown(self, func, *args, **kwargs):
        await self._cooldown()
        return await func(*args, **kwargs)


async def generate_paths(path_list: list[str]):
    file_dict: pathtype = {}

    for path in path_list:
        root_path = pathlib.Path(path)
        if root_path.stem not in file_dict and not root_path.is_file():
            file_dict[root_path.stem] = {}
        if not root_path.is_file():
            for file_path in root_path.rglob('*'):
                if file_path.is_file():
                    file_dict[root_path.stem][str(file_path.relative_to(root_path))] = file_path
        else:
            if root_path.parent.stem not in file_dict:
                file_dict[root_path.parent.stem] = {}
            file_dict[root_path.parent.stem][str(root_path.relative_to(root_path.parent))] = root_path
    return file_dict


async def force_update(state: State, config_path: pathlib.Path):
    config = toml.load(config_path)
    state.paths = await generate_paths(config.get("paths"))
    if config.get("root_paths"):
        await generate_root_paths(config.get("root_paths"), state)


async def config_observer(logger, config: pathlib.Path, state):
    state.config_hash = hashlib.md5(config.open('rb').read()).hexdigest()
    logger.info(f"Initial config hash: {state.config_hash}")
    while True:
        new_hash = hashlib.md5(config.open('rb').read()).hexdigest()
        if state.config_hash != new_hash:
            logger.info(f"Config hash updated: {new_hash}")
            state.config_hash = new_hash
            await force_update(state, config)
        await asyncio.sleep(10)


async def cleanup_routine(logger, config_path: pathlib.Path, state: State):
    logger.info("Start path cleaner.")

    while True:
        await asyncio.sleep(60*30)
        logger.info("Updating paths.")

        config = toml.load(config_path)

        state.paths = await generate_paths(config.get("paths"))
        if config.get("root_paths"):
            await generate_root_paths(config.get("root_paths"), state)


async def start_paths(config: pathlib.Path, state: State):
    config = toml.load(config)
    state.paths = await generate_paths(config.get("paths"))
    if config.get("root_paths"):
        await generate_root_paths(config.get("root_paths"), state)


def process_file(file_path):
    kind = filetype.guess(file_path)
    return None if kind is None else str(kind.mime)


async def process_files_in_thread(file_path):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, process_file, file_path)


async def generate_root_paths(root_path_list: list[str], state: State):
    paths_list = []
    for path in root_path_list:
        root_path = pathlib.Path(path)
        paths_list.extend(str(subpath) for subpath in root_path.iterdir())
    paths = await generate_paths(paths_list)
    state.paths.update(paths)

