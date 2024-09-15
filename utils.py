import asyncio
import hashlib
import json
import pathlib
import subprocess
from collections import defaultdict
from pathlib import Path
import datetime
import toml
import pickle


class State:
    def __init__(self, cooldown_time: float, logger):
        self.paths: dict | None = None
        self.config_hash: str = ""
        self.found_files: defaultdict = defaultdict(list)
        self.root_folder_files: defaultdict = defaultdict(list)
        self.recursive_folders: defaultdict = defaultdict(list)
        self.logger = logger
        self.cooldown_time = cooldown_time
        self._last_call_times = {}

    async def init_paths(self, json_data):
        self.paths = json.loads(json_data) if isinstance(json_data, str) else json_data
        self._initialize()

    def _initialize(self):
        for root in self.paths:
            root_path = Path(root)
            for path in self._iterate_recursive(self.paths[root], root_path):
                self.found_files[path.name].append(path)
                self.root_folder_files[root].append(path)
                self.recursive_folders[path.parent.name].append(path)

    def iterate(self):
        return self._iterate_recursive(self.paths, Path(''))

    def _iterate_recursive(self, current_data: dict[str, str | dict[str, str]], current_path: Path):
        for key, value in current_data.items():
            if isinstance(value, dict):
                for key2, value2 in value.items():
                    if isinstance(value2, dict):
                        new_path = current_path / key
                        yield from self._iterate_recursive(value, new_path)
                    else:
                        yield Path(value2).resolve()
            else:
                yield Path(value).resolve()

    def find_files(self, filename) -> list[Path] | None:
        return self.found_files.get(filename, [])

    async def _cooldown(self, func_name: str):
        last_call_time = self._last_call_times.get(func_name)
        if last_call_time is not None:
            elapsed_time = asyncio.get_event_loop().time() - last_call_time
            self.logger.info(f"{func_name} is on cooldown until {datetime.datetime.now() + datetime.timedelta(seconds=elapsed_time)}.")
            if elapsed_time < self.cooldown_time:
                await asyncio.sleep(self.cooldown_time - elapsed_time)
        self._last_call_times[func_name] = asyncio.get_event_loop().time()

    async def call_function_with_cooldown(self, func, *args, **kwargs):
        func_name = func.__name__  # Nome da função para associar ao cooldown
        await self._cooldown(func_name)
        return await func(*args, **kwargs)


async def generate_paths(config_path: pathlib.Path, state: State):
    config = toml.load(config_path)
    paths_list = []

    if paths := config.get("paths"):
        for path in paths:
            rootpath = Path(path)
            paths_list.extend(str(subpath) for subpath in rootpath.iterdir())

    if root_paths := config.get("root_paths"):
        for path in root_paths:
            rootpath = Path(path)
            paths_list.extend(str(subpath) for subpath in rootpath.iterdir())

    def generate_hash(paths):
        hash_object = hashlib.md5()
        for path in sorted(paths):
            hash_object.update(path.encode('utf-8'))
        return hash_object.hexdigest()

    hash_file = Path('path_hash.txt')
    state_file = Path('path_state.pkl')
    current_hash = generate_hash(paths_list)
    if hash_file.exists() and state_file.exists():
        with hash_file.open('r') as f:
            previous_hash = f.read().strip()
        with state_file.open('rb') as f:
            saved_state: State | None = pickle.load(f)
    else:
        previous_hash = None
        saved_state = None


    if current_hash != previous_hash:
        command = ['./path_generator'] + [str(Path(path).absolute()) for path in paths_list]
        state.paths = json.loads(subprocess.run(command, capture_output=True, text=True).stdout)
        await state.init_paths(state.paths)

        # Salva o novo hash e o estado
        with hash_file.open('w') as f:
            f.write(current_hash)
        with state_file.open('wb') as f:
            pickle.dump(state, f)
    else:
        if saved_state:
            state.paths = saved_state.paths
            state.found_files = saved_state.found_files
            state.root_folder_files = saved_state.root_folder_files
            state.recursive_folders = saved_state.recursive_folders
        state.logger.info("Paths have not changed. Skipping path generation.")


async def clean_root(state: State):
    state_base = state.paths.copy()
    for folder in state_base:
        if not state.paths[folder]:
            del state.paths[folder]


async def config_observer(logger, config: pathlib.Path, state: State):
    state.config_hash = hashlib.md5(config.open('rb').read()).hexdigest()
    logger.info(f"Initial config hash: {state.config_hash}")
    while True:
        new_hash = hashlib.md5(config.open('rb').read()).hexdigest()
        if state.config_hash != new_hash:
            logger.info(f"Config hash updated: {new_hash}")
            state.config_hash = new_hash
            await start_paths(config, state)
        await asyncio.sleep(10)


async def cleanup_routine(logger, config_path: pathlib.Path, state: State):
    logger.info("Start path cleaner.")

    while True:
        await asyncio.sleep(60 * 30)
        logger.info("Updating paths.")
        await state.call_function_with_cooldown(generate_paths, config_path, state)

        await clean_root(state)


async def start_paths(config: pathlib.Path, state: State):
    await state.call_function_with_cooldown(generate_paths, config, state)
    await clean_root(state)


def generate_table_html(state: State) -> str:
    def generate_file_rows(file_data: dict, current_path: str = "") -> str:
        rows = ""
        for key, value in file_data.items():
            if isinstance(value, dict):
                rows += generate_file_rows(value, current_path + key + "/")
                continue
            else:
                rows += f"""
                <tr>
                    <td>{Path(value).name}</td>
                    <td><a href="{Path(value).resolve()}">{Path(value).resolve()}</a></td>
                </tr>
                """
        return rows

    def generate_root_tables(current_data: dict) -> str:
        root_tables_html = ""
        for root, sub_data in current_data.items():
            root_id = root.replace("/", "_").replace(" ", "_")
            root_table = f"""
            <div class="accordion-item">
            <h2 class="accordion-header">
                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#{root_id}"  aria-controls="{root_id}">
                {root}
                </button>
            </h2>
            <div id="{root_id}" class="accordion-collapse collapse" data-bs-parent="#accordionExample">
                <div class="accordion-body">
                    <div class="container tbl-header">
                        <table class="file-table display table-container">
                            <thead>
                                <tr>
                                    <th>File Name</th>
                                    <th>Path</th>
                                </tr>
                            </thead>
                            <tbody>
                                {generate_file_rows(sub_data, root)}
                            </tbody>
                        </table>
                    </div> 
                </div>
            </div>
            </div>

            """
            root_tables_html += root_table
            active = False
        return root_tables_html

    # Gerar o HTML completo para as tabelas dos roots
    root_tables_html = generate_root_tables(state.paths)

    return root_tables_html

