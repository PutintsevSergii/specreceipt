"""Provider-neutral manifest boundary, with a local Python AST/file index."""
import ast
import fnmatch
import hashlib
import os
from pathlib import Path
from .storage import is_link, HarnessError, atomic, digest, now, read, safe_path, validate_schema

EXCLUDED_DIRS = {'.git', '.harness', 'graphify-out', '.codegraph', '.codegraph-wsl', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next', '.pytest_cache'}
SECRET_NAMES = {'.env', '.npmrc', '.pypirc', 'credentials.json', 'secrets.json'}
TEXT_SUFFIXES = {'.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.md', '.yaml', '.yml', '.toml', '.txt', '.sh', '.sql', '.go', '.rs', '.java', '.lock', '.css', '.html', '.vue', '.astro'}
LIMITATIONS = ['Partial coverage: Python AST definitions and static import syntax only; other languages have file nodes only.',
 'No call graph, runtime import resolution, routes, persistence analysis, or LLM inference.',
 'Test relationships are naming heuristics; imports may remain external or unresolved.',
 'Secret-like files, symlinks, binaries, generated/dependency directories and oversized files are excluded.']

def inventory(root, exclusions=(), max_bytes=None, text_only=False):
    found = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not is_link(base/d)
                         and not any(fnmatch.fnmatch((base/d).relative_to(root).as_posix(), p) for p in exclusions))
        for name in sorted(files):
            path = base/name
            rel = path.relative_to(root).as_posix()
            if is_link(path) or name in SECRET_NAMES or name.startswith('.env.') or path.suffix in {'.pem', '.key', '.p12', '.pfx'} or any(fnmatch.fnmatch(rel, p) for p in exclusions):
                continue
            if max_bytes and path.stat().st_size > max_bytes:
                continue
            if text_only and path.suffix not in TEXT_SUFFIXES and name not in {'harness', 'Dockerfile', 'Makefile'}:
                continue
            found[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found

class LocalProvider:
    name = 'local-python-ast'
    version = '1'

    def index(self, root, rel):
        node = {'id':rel,'kind':'file','path':rel,'provenance':'filesystem','confidence':'exact'}
        result = {'nodes':[node],'edges':[],'limitations':[]}
        if rel.endswith('.py'):
            try:
                tree = ast.parse((root/rel).read_text(encoding='utf-8'), filename=rel)
            except (SyntaxError, UnicodeError) as exc:
                result['limitations'].append(f'Parse unavailable: {type(exc).__name__}')
                return result
            for item in ast.walk(tree):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbol = f'{rel}:{item.lineno}:{item.name}'
                    result['nodes'].append({'id':symbol,'kind':'symbol','name':item.name,'line':item.lineno,'path':rel,'provenance':'parser','confidence':'exact'})
                    result['edges'].append({'from':rel,'to':symbol,'kind':'defines','provenance':'parser','confidence':'exact'})
                if isinstance(item, (ast.Import, ast.ImportFrom)):
                    targets = [n.name for n in item.names] if isinstance(item, ast.Import) else ['.'*item.level+(item.module or '')]
                    for target in targets:
                        result['edges'].append({'from':rel,'to':'module:'+target,'kind':'imports','line':item.lineno,'provenance':'parser','confidence':'syntax-only'})
        return result

PROVIDERS = {LocalProvider.name: LocalProvider}

def configuration(root):
    config = read(root/'.harness/graph-config.json')
    validate_schema(config, read(root/'schemas/graph-config.schema.json'))
    return config

def inputs(root, config):
    return inventory(root, config['exclude'], config['max_bytes'], text_only=True)

def status(root):
    try:
        cfg = configuration(root)
        if cfg['provider'] not in PROVIDERS or cfg['version'] != PROVIDERS[cfg['provider']].version:
            raise HarnessError('Configured provider/version unavailable')
        path = root/'.harness/graph/manifest.json'
        if not path.exists():
            return {'freshness':'unavailable','coverage':'partial','limitations':LIMITATIONS,'fallback':'Use targeted source search.'}
        graph = read(path)
        validate_schema(graph, read(root/'schemas/graph.schema.json'))
        fresh = graph['hashes'] == inputs(root,cfg) and graph['config_hash'] == digest(cfg) and not (root/'.harness/graph/updating.json').exists()
        return {'freshness':'fresh' if fresh else 'stale','coverage':'partial','provider':graph['provider'],
                'limitations':graph['limitations'],'parse_limitations':{p:f['limitations'] for p,f in graph['files'].items() if f['limitations']}}
    except (HarnessError, OSError) as exc:
        return {'freshness':'unavailable','coverage':'partial','limitations':[str(exc)],'fallback':'Use targeted source search; all required verification remains mandatory.'}

def update(root):
    cfg = configuration(root)
    if cfg['provider'] not in PROVIDERS or cfg['version'] != PROVIDERS[cfg['provider']].version:
        raise HarnessError('Graph provider unavailable; use source search. Verification gates remain unchanged.')
    if status(root)['freshness'] == 'fresh':
        return {'changed':False,**status(root)}
    marker = safe_path(root,'.harness/graph/updating.json')
    atomic(marker, {'started_at':now()})
    path = safe_path(root,'.harness/graph/manifest.json')
    old = {}
    if path.exists():
        try:
            old = read(path)
            validate_schema(old, read(root/'schemas/graph.schema.json'))
        except HarnessError:
            old = {}
    hashes = inputs(root,cfg)
    compatible = old.get('config_hash') == digest(cfg)
    changed = [p for p,h in hashes.items() if not compatible or old.get('hashes',{}).get(p) != h]
    deleted = sorted(set(old.get('hashes',{}))-set(hashes))
    provider = PROVIDERS[cfg['provider']]()
    files = {p: provider.index(root,p) if p in changed else old['files'][p] for p in hashes}
    # Derived test links are recomputed cheaply; parsing remains incremental.
    for p, data in files.items():
        data['edges'] = [e for e in data['edges'] if e['kind'] != 'may-test']
        stem = Path(p).stem
        if stem.startswith('test_'):
            for candidate in hashes:
                if Path(candidate).stem == stem[5:]:
                    data['edges'].append({'from':p,'to':candidate,'kind':'may-test','provenance':'heuristic','confidence':'low'})
    manifest = {'schema_version':1,'provider':provider.name,'provider_version':provider.version,'config_hash':digest(cfg),
                'status':'complete','coverage':'partial','limitations':LIMITATIONS,'updated_at':now(),'indexed_paths':sorted(hashes),
                'hashes':hashes,'files':files,'last_update':{'reindexed':changed,'deleted':deleted}}
    if inputs(root,cfg) != hashes:
        raise HarnessError('Files changed during graph indexing; retry update.')
    validate_schema(manifest,read(root/'schemas/graph.schema.json'))
    atomic(path,manifest)
    marker.unlink()
    return {'changed':True,'reindexed':changed,'deleted':deleted,**status(root)}

def query(root, term, limit=30):
    current = status(root)
    if current['freshness'] != 'fresh':
        try:
            update(root)
        except (HarnessError,OSError) as exc:
            return {'result':'BLOCKED','graph':current,'fallback':f'Search source directly: {exc}','nodes':[],'edges':[]}
    manifest = read(root/'.harness/graph/manifest.json')
    nodes = [n for f in manifest['files'].values() for n in f['nodes'] if term.lower() in n['id'].lower()][:limit]
    ids = {n['id'] for n in nodes}
    edges = [e for f in manifest['files'].values() for e in f['edges'] if e['from'] in ids or e['to'] in ids][:limit*2]
    return {'result':'PASS','graph':status(root),'nodes':nodes,'edges':edges,'limit':limit,
            'instruction':'Inspect referenced source and canonical specs. This bounded neighborhood is not behavioral evidence.'}
