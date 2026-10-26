"""Prefer project-local managed tools without changing the host PATH."""
from pathlib import Path
import shutil
import os
from .storage import HarnessError, safe_path

PATHS = {'codegraph':'node_modules/.bin/codegraph', 'graphify':'bin/graphify',
         'openspec':'node_modules/.bin/openspec'}


def binary(root, name):
    if root is not None:
        base = safe_path(Path(root).resolve(), '.harness/tools/' + name)
        relative = ('Scripts/graphify.exe' if name == 'graphify' else PATHS[name] + '.cmd') if os.name == 'nt' else PATHS[name]
        path = base / relative
        if path.exists() or path.is_symlink():
            if not path.is_file() or not path.resolve().is_relative_to(base.resolve()):
                raise HarnessError('Managed tool executable is invalid or escapes its installation: '+name)
            return str(path)
    return shutil.which(name)
