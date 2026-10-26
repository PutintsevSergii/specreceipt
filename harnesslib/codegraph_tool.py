"""Local CLI adapter for colbymchenry/codegraph, independent of agent MCP setup."""
from pathlib import Path
import shutil
import subprocess

from .graph import inventory
from .tool_paths import binary as tool_binary
from .storage import HarnessError, atomic, digest, read

PACKAGE = '@colbymchenry/codegraph@1.6.2'
STATE = '.harness/graph/codegraph-state.json'
INDEXES = ('.codegraph', '.codegraph-wsl')


def _snapshot(root):
    return digest(inventory(root, text_only=True))


def _command(root, *args, timeout=120):
    binary = tool_binary(root, 'codegraph')
    if not binary:
        raise HarnessError('CodeGraph CLI is unavailable; run ./harness codegraph ensure.')
    try:
        result = subprocess.run([binary, *map(str, args)], cwd=root, capture_output=True,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f'CodeGraph command failed: {exc}') from exc
    if result.returncode:
        raise HarnessError(f'CodeGraph exited {result.returncode}: {(result.stderr or result.stdout)[-1000:]}')
    return result.stdout


def status(root):
    root = Path(root).resolve()
    indexed = any((root/name).is_dir() for name in INDEXES)
    if not tool_binary(root, 'codegraph'):
        return {'installed':False,'indexed':indexed,'freshness':'unavailable',
                'next_action':'Install locally with python3 scripts/update-tools.py --apply --only codegraph, then run ensure.'}
    if not indexed or not (root/STATE).is_file():
        return {'installed':True,'indexed':indexed,'freshness':'unavailable',
                'next_action':'Run ./harness codegraph ensure.'}
    try:
        version = _command(root, 'version', timeout=10).strip()
        meta = read(root/STATE)
        if not isinstance(meta,dict):
            raise HarnessError('CodeGraph state has invalid shape.')
        fresh = meta.get('snapshot') == _snapshot(root) and meta.get('version') == version
        if fresh:
            _command(root, 'status', '--json', timeout=15)
        return {'installed':True,'indexed':True,'version':version,
                'freshness':'fresh' if fresh else 'stale',
                'next_action':None if fresh else 'Run ./harness codegraph ensure.'}
    except (HarnessError, OSError) as exc:
        return {'installed':True,'indexed':indexed,'freshness':'unavailable',
                'error':str(exc),'next_action':'Use Graphify or targeted source search.'}


def install_binary(root=None):
    """Index refresh never changes the global environment or installs dependencies."""
    if not tool_binary(root, 'codegraph'):
        raise HarnessError('Codegraph is unavailable. Explicitly install the supported local tool with '
                           'python3 scripts/update-tools.py --apply --only codegraph, then retry ensure.')


def ensure(root):
    root = Path(root).resolve()
    install_binary(root)
    current = status(root)
    if current['freshness'] == 'fresh':
        return {'changed':False,**current}
    before = _snapshot(root)
    if not any((root/name).is_dir() for name in INDEXES):
        _command(root, 'init', root, timeout=180)
    else:
        _command(root, 'sync', root, timeout=180)
    if _snapshot(root) != before:
        raise HarnessError('Source changed during CodeGraph indexing; retry ensure.')
    if not any((root/name).is_dir() for name in INDEXES):
        raise HarnessError('CodeGraph did not create a project index.')
    _command(root, 'status', root, '--json', timeout=15)
    version = _command(root, 'version', timeout=10).strip()
    atomic(root/STATE, {'snapshot':before,'version':version})
    current = status(root)
    if current['freshness'] != 'fresh':
        raise HarnessError('CodeGraph index did not become fresh after sync.')
    return {'changed':True,**current}


def query(root, term, limit=10):
    if not 1 <= limit <= 30:
        raise HarnessError('CodeGraph query limit must be 1..30.')
    current = status(root)
    if current['freshness'] != 'fresh':
        return {'result':'BLOCKED','codegraph':current,'fallback':'Run ./harness codegraph ensure or use Graphify/source search.'}
    result = _command(Path(root).resolve(), 'query', term, '--limit', limit, '--json', timeout=30)
    return {'result':'PASS','answer':result[:16000],'limit':limit,
            'instruction':'Inspect referenced source and requirements; index results are navigation, not proof.'}
