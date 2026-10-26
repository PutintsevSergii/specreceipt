"""Native command resolution and bounded process-tree cleanup, without a shell."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess


def environment(extra=()):
    """Keep native OS locations and command discovery, never arbitrary secrets."""
    names = ('PATH', 'HOME', 'TMPDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA',
             'APPDATA', 'LANG', 'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC',
             'PATHEXT', 'PROCESSOR_ARCHITECTURE', 'PROCESSOR_ARCHITEW6432',
             'PROGRAMDATA', 'ALLUSERSPROFILE', 'PROGRAMFILES', 'PROGRAMFILES(X86)',
             'PROGRAMW6432', 'COMMONPROGRAMFILES', 'COMMONPROGRAMFILES(X86)',
             'COMMONPROGRAMW6432', 'PUBLIC', 'HOMEDRIVE', 'HOMEPATH',
             'HARNESS_REQUIRE_SYMLINK_TESTS')
    result = {name: os.environ[name] for name in (*names, *extra) if name in os.environ}
    result['PYTHONUTF8'] = '1'
    return result


def argv(values):
    values = list(map(str, values))
    if os.name != 'nt':
        return values
    executable = shutil.which(values[0]) or values[0]
    path = Path(executable)
    # npm shims cannot be passed to CreateProcess. Resolve the package's
    # declared JS entry rather than interpolating arbitrary arguments in cmd.
    if path.suffix.lower() in ('.cmd', '.bat') or path.suffix == '':
        name = path.stem
        packages = {'npm': 'npm', 'npx': 'npm', 'codegraph': '@colbymchenry/codegraph',
                    'openspec': '@fission-ai/openspec'}
        if name in packages:
            base = path.parent.parent if path.parent.name == '.bin' else path.parent / 'node_modules'
            package = base / packages[name]
            manifest = package / 'package.json'
            if manifest.is_file():
                bins = json.loads(manifest.read_text(encoding='utf-8'))['bin']
                entry = package / (bins if isinstance(bins, str) else bins[name])
                if not entry.resolve().is_relative_to(package.resolve()) or not entry.is_file():
                    raise OSError('Invalid package executable: ' + name)
                node = shutil.which('node')
                if not node:
                    raise OSError('Node is required for ' + name)
                return [node, str(entry), *values[1:]]
        if path.suffix.lower() in ('.cmd', '.bat'):
            raise OSError('Use a native executable or explicit interpreter instead of a batch shim: ' + str(path))
    return [executable, *values[1:]]


def stop(process):
    if os.name == 'nt':
        taskkill = Path(os.environ.get('SYSTEMROOT', r'C:\Windows')) / 'System32/taskkill.exe'
        result = subprocess.run([str(taskkill), '/PID', str(process.pid), '/T', '/F'],
                                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and process.poll() is None:
            raise OSError('Unable to terminate timed-out process tree')
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=30)


def run(values, **kwargs):
    """Bounded subprocess.run equivalent with tree cleanup and no shell."""
    if kwargs.get('text') and 'encoding' not in kwargs:
        kwargs['encoding'] = 'utf-8'
    env = dict(os.environ if kwargs.get('env') is None else kwargs['env'])
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    kwargs['env'] = env
    timeout = kwargs.pop('timeout', None)
    check = kwargs.pop('check', False)
    data = kwargs.pop('input', None)
    if kwargs.pop('capture_output', False):
        if 'stdout' in kwargs or 'stderr' in kwargs:
            raise ValueError('capture_output cannot be combined with stdout/stderr')
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if data is not None:
        if 'stdin' in kwargs: raise ValueError('input cannot be combined with stdin')
        kwargs['stdin'] = subprocess.PIPE
    kwargs['start_new_session'] = True
    if os.name == 'nt': kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    command = argv(values)
    with subprocess.Popen(command, **kwargs) as process:
        try:
            output, errors = process.communicate(data, timeout=timeout)
        except subprocess.TimeoutExpired:
            stop(process)
            output, errors = process.communicate()
            raise subprocess.TimeoutExpired(command, timeout, output=output, stderr=errors)
        except BaseException:
            stop(process)
            raise
        result = subprocess.CompletedProcess(command, process.returncode, output, errors)
        if check: result.check_returncode()
        return result
