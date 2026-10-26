"""Optional local Graphify CLI adapter for bounded code navigation."""
import json
from pathlib import Path
import shutil
import subprocess

from .graph import inventory
from .tool_paths import binary as tool_binary
from .storage import HarnessError, atomic, digest, read, safe_path

PACKAGE = 'graphifyy==0.9.27'
STATE = '.harness/graph/graphify-state.json'
GRAPH = 'graphify-out/graph.json'
EXCLUDES = ('graphify-out', 'graphify-out/*')


class EmptyCodeIndex(HarnessError):
    """The pinned CLI explicitly found no eligible code, not an extraction error."""


def _snapshot(root):
    return digest(inventory(root, EXCLUDES, text_only=True))


def _command(root, *args, timeout=120):
    binary = tool_binary(root, 'graphify')
    if not binary:
        raise HarnessError('Graphify is unavailable. Install it locally through scripts/update-tools.py, then run ensure.')
    try:
        result = subprocess.run([binary, *map(str, args)], cwd=root, capture_output=True,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f'Graphify command failed: {exc}') from exc
    if result.returncode:
        if (args and args[0]=='update' and result.returncode==1 and
                '[graphify watch] No code files found - nothing to rebuild.' in result.stdout.splitlines()):
            raise EmptyCodeIndex('No eligible code files were found by Graphify.')
        raise HarnessError(f'Graphify exited {result.returncode}: {(result.stderr or result.stdout)[-1000:]}')
    return result.stdout


def status(root):
    root = Path(root).resolve()
    binary = tool_binary(root, 'graphify')
    graph = root/GRAPH
    state = root/STATE
    if not binary:
        return {'installed':False,'indexed':graph.is_file(),'freshness':'unavailable',
                'next_action':'Install locally with python3 scripts/update-tools.py --apply --only graphify, then run ensure.'}
    try:
        version = _command(root, '--version', timeout=10).strip()
        if not graph.is_file() or not state.is_file():
            return {'installed':True,'version':version,'indexed':graph.is_file(),'freshness':'unavailable',
                    'next_action':'Run ./harness graphify ensure to build or verify the local index.'}
        meta = read(state)
        if not isinstance(meta,dict):
            raise HarnessError('Graphify state has invalid shape.')
        fresh = meta.get('snapshot') == _snapshot(root) and meta.get('version') == version
        return {'installed':True,'version':version,'indexed':True,
                'freshness':'fresh' if fresh else 'stale',
                'coverage':'empty' if meta.get('empty') else 'code',
                'next_action':None if fresh else 'Run ./harness graphify ensure to refresh the index.'}
    except (HarnessError, OSError) as exc:
        return {'installed':True,'indexed':graph.is_file(),'freshness':'unavailable',
                'error':str(exc),'next_action':'Use ./harness graph or targeted source search.'}


def install_binary(root=None):
    """Index refresh never changes the global environment or installs dependencies."""
    if not tool_binary(root, 'graphify'):
        raise HarnessError('Graphify is unavailable. Explicitly install the supported local tool with '
                           'python3 scripts/update-tools.py --apply --only graphify, then retry ensure.')


def ensure(root):
    root = Path(root).resolve()
    install_binary(root)
    current = status(root)
    if current['freshness'] == 'fresh':
        return {'changed':False,**current}
    before = _snapshot(root)
    empty=False
    try:
        _command(root, 'update', root, '--force', '--no-cluster', timeout=180)
    except EmptyCodeIndex:
        empty=True
        atomic(safe_path(root,GRAPH), {'nodes':[], 'links':[]})
    graph = root/GRAPH
    try:
        data = json.loads(graph.read_text())
    except (OSError, ValueError) as exc:
        raise HarnessError(f'Graphify did not produce valid graph.json: {exc}') from exc
    if not isinstance(data, dict) or not isinstance(data.get('nodes'), list) or not isinstance(data.get('links'), list):
        raise HarnessError('Graphify graph.json has an unsupported shape.')
    if _snapshot(root) != before:
        raise HarnessError('Source changed during Graphify indexing; retry ensure.')
    version = _command(root, '--version', timeout=10).strip()
    atomic(root/STATE, {'snapshot':before,'version':version,'empty':empty})
    current = status(root)
    if current['freshness'] != 'fresh':
        raise HarnessError('Graphify index did not become fresh after update.')
    return {'changed':True,'nodes':len(data['nodes']),'edges':len(data['links']),**current}


def query(root, question, budget=800):
    if not 100 <= budget <= 2000:
        raise HarnessError('Graphify query budget must be 100..2000 tokens.')
    current = status(root)
    if current['freshness'] != 'fresh':
        return {'result':'BLOCKED','graphify':current,
                'fallback':'Run ./harness graphify ensure or use targeted source search.'}
    if current.get('coverage')=='empty':
        return {'result':'PASS','answer':'No eligible source code is indexed yet.', 'budget':budget,
                'coverage':'empty','instruction':'Add application source and refresh indexes before querying code.'}
    answer = _command(Path(root).resolve(), 'query', question, '--budget', budget,
                      '--graph', Path(root).resolve()/GRAPH, timeout=30)
    return {'result':'PASS','answer':answer[:16000], 'budget':budget,
            'instruction':'Verify referenced source and requirements; graph answers are navigation, not proof.'}
