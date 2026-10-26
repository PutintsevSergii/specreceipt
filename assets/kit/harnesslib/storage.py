"""Validated JSON, process serialization, recoverable transactions and redaction."""
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

class HarnessError(Exception):
    pass

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def uid():
    return str(uuid.uuid4())

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise HarnessError(f'Cannot read JSON {path}: {exc}') from exc

def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + uid())
    try:
        with tmp.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(data, indent=2, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        # Windows cannot open directories through os.open. The file is flushed
        # before replacement; POSIX additionally persists the directory entry.
        if os.name != 'nt':
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        tmp.unlink(missing_ok=True)

def redact(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if re.search(r'password|secret|token|credential|api.key', k, re.I)
                else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[REDACTED KEY]', value, flags=re.S)
    value = re.sub(r'(?i)((?:password|secret|token|api[_-]?key)\s*[=:]\s*)[^\s,;]+', r'\1[REDACTED]', value)
    value = re.sub(r'(?i)(bearer\s+)\S+', r'\1[REDACTED]', value)
    value = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9_]{10,})', '[REDACTED]', value)
    value = re.sub(r'(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[REDACTED]@', value)
    return value

def validate_schema(value, schema, location='$'):
    """Deliberate JSON Schema subset used by our checked-in schemas. Fail closed."""
    supported = {'$schema', 'title', 'description', 'type', 'required', 'properties',
                 'additionalProperties', 'items', 'enum', 'minLength', 'minItems', 'pattern', 'minimum'}
    if set(schema) - supported:
        raise HarnessError(f'Unsupported schema keywords: {set(schema) - supported}')
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int,
             'boolean': bool, 'null': type(None), 'number': (int, float)}
    allowed = kind if isinstance(kind, list) else [kind] if kind else []
    if allowed and not any(isinstance(value, types[k]) and not (k in ('integer', 'number') and isinstance(value, bool)) for k in allowed):
        raise HarnessError(f'{location}: expected {kind}')
    if 'enum' in schema and value not in schema['enum']:
        raise HarnessError(f'{location}: invalid value {value!r}')
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                raise HarnessError(f'{location}: missing {key}')
        props = schema.get('properties', {})
        for key, item in value.items():
            if key in props:
                validate_schema(item, props[key], f'{location}.{key}')
            elif schema.get('additionalProperties') is False:
                raise HarnessError(f'{location}: unexpected {key}')
            elif isinstance(schema.get('additionalProperties'), dict):
                validate_schema(item, schema['additionalProperties'], f'{location}.{key}')
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            raise HarnessError(f'{location}: too few items')
        for i, item in enumerate(value):
            validate_schema(item, schema.get('items', {}), f'{location}[{i}]')
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or ('pattern' in schema and not re.search(schema['pattern'], value)):
            raise HarnessError(f'{location}: invalid string')
    if isinstance(value, (int, float)) and 'minimum' in schema and value < schema['minimum']:
        raise HarnessError(f'{location}: below minimum')

def is_link(path):
    """Include Windows junctions/reparse points in the existing no-link boundary."""
    path = Path(path)
    if path.is_symlink(): return True
    if os.name == 'nt':
        try:
            return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except FileNotFoundError:
            return False
    return False


def safe_path(root, rel):
    root = Path(root).resolve()
    if os.name == 'nt' and (Path(rel).drive or ':' in str(rel) or any(
            part != part.rstrip(' .') or re.fullmatch(r'(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part)
            for part in Path(rel).parts)):
        raise HarnessError(f'Unsafe repository path: {rel}')
    path = root / rel
    if Path(rel).is_absolute() or '..' in Path(rel).parts or not path.resolve().is_relative_to(root.resolve()):
        raise HarnessError(f'Unsafe repository path: {rel}')
    if any(is_link(p) for p in [path, *path.parents] if p != root.parent):
        raise HarnessError(f'Symlink path disallowed: {rel}')
    return path

@contextlib.contextmanager
def lock(root):
    directory = safe_path(root, '.harness')
    directory.mkdir(exist_ok=True)
    guard = safe_path(root, '.harness/installation.lock')
    if safe_path(root, '.harness/installation-pending.json').exists():
        raise HarnessError('Installation or upgrade recovery required before lifecycle writes.')
    try:
        handle = guard.open('x', encoding='utf-8')
    except FileExistsError as exc:
        raise HarnessError('Another harness writer or installer is active; inspect stale locks before retrying.') from exc
    try:
        with safe_path(root, '.harness/write.lock').open('a+b') as stream:
            try:
                if os.name == 'nt':
                    if stream.seek(0, os.SEEK_END) == 0:
                        stream.write(b'\0')
                        stream.flush()
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise HarnessError('Another harness writer is active; retry after it exits.') from exc
            try:
                yield
            finally:
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)
    finally:
        handle.close()
        guard.unlink()

def events(root):
    path = safe_path(root, '.harness/events.jsonl')
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
    except ValueError as exc:
        raise HarnessError('Journal has a torn/invalid record; preserve it and use resume.') from exc

def finish_transaction(root):
    pending = safe_path(root, '.harness/transaction.json')
    if not pending.exists():
        return False
    txn = read(pending)
    event = txn['event']
    path = safe_path(root, '.harness/events.jsonl')
    # Only repair a torn final append when it is a byte prefix of this WAL event.
    encoded = (json.dumps(event, sort_keys=True) + '\n').encode()
    raw = path.read_bytes() if path.exists() else b''
    if raw and not raw.endswith(b'\n'):
        cut = raw.rfind(b'\n') + 1
        if not encoded.startswith(raw[cut:]):
            raise HarnessError('Unrecognized journal corruption; manual recovery required.')
        with path.open('r+b') as stream:
            stream.truncate(cut)
            stream.flush()
            os.fsync(stream.fileno())
    for rel, data in txn['writes'].items():
        if not (rel in {'.harness/state.json','.harness/onboarding.json','.harness/runner-state.json'} or re.fullmatch(r'specs/[a-z0-9-]+/tasks.json', rel) or rel.startswith('.harness/evidence/')):
            raise HarnessError(f'Unexpected transaction target {rel}')
        atomic(safe_path(root, rel), data)
    if event['id'] not in {e['id'] for e in events(root)}:
        with path.open('ab') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    pending.unlink()
    return True

def transaction(root, writes, event):
    pending = safe_path(root, '.harness/transaction.json')
    if pending.exists():
        raise HarnessError('Interrupted transaction; run resume before modifying state.')
    atomic(pending, {'writes': writes, 'event': redact(event)})
    finish_transaction(root)
