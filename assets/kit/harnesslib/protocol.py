"""Versioned subprocess envelope; all operation semantics remain in cli/core."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
from . import cli
from .storage import redact

PROTOCOL_VERSION = 1
ENGINE_VERSION = '0.4.4'


def metadata(root):
    commands = next(a for a in cli.parser()._actions if a.dest == 'command').choices
    return {'protocolVersion': PROTOCOL_VERSION, 'engineVersion': ENGINE_VERSION,
            'operations': sorted(commands), 'target': str(root), 'cwd': str(Path.cwd().resolve()),
            'engineRoot': str(Path(__file__).resolve().parents[1])}


def main():
    result = {'protocolVersion': PROTOCOL_VERSION, 'engineVersion': ENGINE_VERSION,
              'exitCode': 2, 'data': None, 'error': None}
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or set(request) != {'protocolVersion', 'target', 'argv'}:
            raise ValueError('Invalid engine request fields')
        if request['protocolVersion'] != PROTOCOL_VERSION:
            raise ValueError('Incompatible protocol version; upgrade the project engine and CLI together')
        root = Path(request['target']).resolve(strict=True)
        argv = request['argv']
        if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or '\x00' in a for a in argv):
            raise ValueError('argv must be a nonempty string array')
        if any(a == '--root' or a.startswith('--root=') for a in argv):
            raise ValueError('Use public --target; engine root overrides are forbidden')
        if Path.cwd().resolve() != root:
            raise ValueError('Working directory does not match target identity')
        result.update(metadata(root))
        if argv == ['contract']:
            result.update(exitCode=0, data=metadata(root))
        else:
            out, err = io.StringIO(), io.StringIO()
            original = sys.argv
            try:
                sys.argv = ['harness', '--root', str(root), *argv]
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        code = cli.main()
                    except SystemExit as exc:
                        code = exc.code if isinstance(exc.code, int) else 2
            finally:
                sys.argv = original
            raw = out.getvalue()
            try:
                data = json.loads(raw) if raw.strip() else None
            except ValueError:
                data = {'text': raw}
            result.update(exitCode=code or 0, data=data)
            if err.getvalue():
                # Existing CLI redaction also applies to validation errors/help diagnostics.
                print(redact(err.getvalue()), file=sys.stderr, end='')
            if code:
                result['error'] = {'code': 'OPERATION_FAILED', 'message': 'Engine operation failed; inspect diagnostics and structured data.'}
    except (ValueError, TypeError, OSError, KeyError):
        result['error'] = {'code': 'INVALID_REQUEST', 'message': 'Invalid request, incompatible protocol, or target identity.'}
    except Exception:
        result['exitCode'] = 1
        result['error'] = {'code': 'ENGINE_FAILURE', 'message': 'Engine failed; inspect project recovery state before retrying.'}
    print(json.dumps(redact(result), sort_keys=True))
    return result['exitCode']


if __name__ == '__main__':
    sys.exit(main())
