from pathlib import Path


def pre_find_module_path(hook_api):
    # Freeze the package, rather than the root compatibility shim's dynamic __path__.
    hook_api.search_dirs.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
