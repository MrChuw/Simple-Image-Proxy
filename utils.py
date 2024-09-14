
import asyncio
import pathlib
import toml
import hashlib
from pathlib import Path

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


async def go_deeper(path: Path, folder: dict):
    for item in path.iterdir():
        if item.is_dir():
            if item.name not in folder:
                folder[item.name] = {}
            await go_deeper(item, folder[item.name])
        else:
            folder[item.name] = item

    return {k: v for k, v in folder.items() if v}


async def generate(dir_path: Path) -> dict:
    if not dir_path.is_dir():
        return {dir_path.name: dir_path}
    temp_state = {}
    for item in dir_path.iterdir():
        if item.is_dir():
            if item.name not in temp_state:
                temp_state[item.name] = {}
            await go_deeper(item, temp_state[item.name])
        else:
            temp_state[item.name] = item
    return {k: v for k, v in temp_state.items() if v}


async def generate_paths(paths: list[str], state):
    for path in paths:
        path = Path(path)
        if path.name not in state.paths:
            state.paths[path.name] = {}
        temp_state = await generate(path)
        if temp_state:
            state.paths[path.name].update(temp_state)


async def clean_root(state: State):
    state_base = state.paths.copy()
    for folder in state_base:
        if not state.paths[folder]:
            del state.paths[folder]


async def force_update(state: State, config_path: pathlib.Path):
    config = toml.load(config_path)
    await generate_paths(config.get("paths"), state)
    if config.get("root_paths"):
        await generate_root_paths(config.get("root_paths"), state)
    await clean_root(state)


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

        await generate_paths(config.get("paths"), state)
        if config.get("root_paths"):
            await generate_root_paths(config.get("root_paths"), state)
        await clean_root(state)


async def start_paths(config: pathlib.Path, state: State):
    config = toml.load(config)
    await generate_paths(config.get("paths"), state)
    if config.get("root_paths"):
        await generate_root_paths(config.get("root_paths"), state)
    await clean_root(state)


async def generate_root_paths(root_path_list: list[str], state: State):
    paths_list = []
    for path in root_path_list:
        rootpath = Path(path)
        paths_list.extend(str(subpath) for subpath in rootpath.iterdir())
    await generate_paths(paths_list, state)

