"""User-local prerequisite provisioning; never replaces system installations."""
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

from . import processes
from .storage import HarnessError, atomic, now


def directory():
    if os.name == 'nt':
        return Path(os.environ.get('HARNESS_RUNTIME_DIR') or
                    str(Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'harness/runtime')).expanduser().resolve()
    return Path(os.environ.get('HARNESS_RUNTIME_DIR') or
                str(Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'harness/runtime')).expanduser().resolve()


def activate():
    base = directory()
    additions = [str(base/'bin'), str(base/('node' if os.name == 'nt' else 'node/bin'))]
    existing = os.environ.get('PATH','').split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join(additions + [p for p in existing if p not in additions])


def command(argv, timeout=300, env=None):
    try:
        result = processes.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError('Runtime provisioning command failed: ' + str(exc)) from exc
    if result.returncode:
        raise HarnessError('Runtime provisioning failed: ' + (result.stderr or result.stdout)[-2000:])
    return result.stdout.strip()


def download(url, path, limit):
    # All callers supply fixed official HTTPS origins. Do not accept project URLs.
    with urllib.request.urlopen(url, timeout=60) as response, path.open('wb') as output:
        if not response.geturl().startswith('https://'):
            raise HarnessError('Refusing a non-HTTPS runtime download.')
        size = 0
        while chunk := response.read(1024*1024):
            size += len(chunk)
            if size > limit: raise HarnessError('Runtime download exceeds its size limit.')
            output.write(chunk)


def ensure_uv():
    found = shutil.which('uv')
    if found:
        command([found,'--version'],15)
        return found
    base = directory(); (base/'bin').mkdir(parents=True,exist_ok=True)
    if os.name == 'nt':
        command(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                 '-File', str(Path(__file__).resolve().parents[1]/'scripts/uv.ps1'),
                 '-Destination', str(base/'bin')])
        activate()
        found = shutil.which('uv')
        if not found: raise HarnessError('uv installation did not provide an executable.')
        command([found, '--version'], 15)
        return found
    with tempfile.TemporaryDirectory(prefix='harness-uv-') as folder:
        extension = 'ps1' if os.name == 'nt' else 'sh'
        installer = Path(folder)/('uv-install.' + extension)
        download('https://astral.sh/uv/install.' + extension, installer, 2*1024*1024)
        env = dict(os.environ, UV_UNMANAGED_INSTALL=str(base/'bin'))
        command((['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File']
                 if os.name == 'nt' else ['sh']) + [str(installer)],env=env)
    activate()
    found = shutil.which('uv')
    if not found: raise HarnessError('uv installation did not provide an executable.')
    command([found,'--version'],15)
    return found


def node_compatible():
    node, npm = shutil.which('node'), shutil.which('npm')
    if not node or not npm: return False
    try:
        version = command([node,'--version'],15)
        match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)',version)
        if not match: return False
        number = tuple(map(int,match.groups()))
        if not (20,19,0) <= number < (25,0,0): return False
        command([npm,'--version'],15)
        return True
    except HarnessError:
        return False


def node_platform():
    system = {'Darwin':'darwin','Linux':'linux','Windows':'win'}.get(platform.system())
    arch = {'x86_64':'x64','AMD64':'x64','arm64':'arm64','aarch64':'arm64'}.get(platform.machine())
    if not system or not arch or (system == 'win' and arch != 'x64'):
        raise HarnessError('Automatic Node installation supports Windows x64 and macOS/Linux x64/arm64.')
    return system, arch


def ensure_node():
    if node_compatible(): return
    system, arch = node_platform()
    base=directory();base.mkdir(parents=True,exist_ok=True)
    destination=base/'node'
    if destination.exists() or destination.is_symlink():
        raise HarnessError('Managed Node exists but is unusable. Inspect it before retrying; it was not overwritten.')
    with tempfile.TemporaryDirectory(prefix='node-stage-',dir=base) as folder:
        stage=Path(folder); checks=stage/'SHASUMS256.txt'
        url='https://nodejs.org/dist/latest-v22.x/'
        download(url+'SHASUMS256.txt',checks,1024*1024)
        suffix = '.zip' if system == 'win' else '.tar.gz'
        pattern=re.compile(r'([a-f0-9]{64})\s+(node-v22\.\d+\.\d+-'+system+'-'+arch+re.escape(suffix)+')')
        matches=[m for line in checks.read_text(encoding='utf-8').splitlines() if (m:=pattern.fullmatch(line))]
        if len(matches)!=1: raise HarnessError('Cannot select a unique official Node 22 distribution.')
        checksum, name=matches[0].groups(); archive=stage/name
        download(url+name,archive,150*1024*1024)
        with archive.open('rb') as stream:
            observed=hashlib.file_digest(stream,'sha256').hexdigest()
        if observed!=checksum:
            raise HarnessError('Node archive checksum mismatch.')
        prefix=name[:-len(suffix)]
        if system == 'win':
            with zipfile.ZipFile(archive) as zipped:
                for item in zipped.infolist():
                    parts = Path(item.filename).parts
                    if (not parts or parts[0] != prefix or '..' in parts or
                            Path(item.filename).is_absolute() or ':' in item.filename or
                            '\\' in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000):
                        raise HarnessError('Unsafe Node archive path.')
                zipped.extractall(stage)
            (stage/prefix).rename(destination)
            activate()
            if not node_compatible(): raise HarnessError('Downloaded Node/npm could not execute on this platform.')
            return
        with tarfile.open(archive,'r:gz') as tar:
            for item in tar.getmembers():
                parts=Path(item.name).parts
                if not parts or parts[0]!=prefix or '..' in parts or Path(item.name).is_absolute():
                    raise HarnessError('Unsafe Node archive path.')
                if not (item.isfile() or item.isdir() or item.issym()):
                    raise HarnessError('Unsupported Node archive entry.')
                if item.issym():
                    resolved=(stage/item.name).parent.joinpath(item.linkname).resolve()
                    if not resolved.is_relative_to(stage/prefix): raise HarnessError('Unsafe Node archive link.')
            # Extract regular entries first, links last; no writes traverse archive symlinks.
            # This also supports Python 3.11 releases before tar extraction filters existed.
            for item in tar.getmembers():
                path=stage/item.name
                if item.isdir(): path.mkdir(parents=True,exist_ok=True)
                elif item.isfile():
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with tar.extractfile(item) as source, path.open('xb') as output:
                        shutil.copyfileobj(source,output)
                    path.chmod(item.mode & 0o755)
            for item in tar.getmembers():
                if item.issym():
                    path=stage/item.name
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.symlink_to(item.linkname)
        (stage/prefix).rename(destination)
    activate()
    if not node_compatible(): raise HarnessError('Downloaded Node/npm could not execute on this platform.')


def prepare(root):
    activate()
    ensure_uv()
    ensure_node()
    report={'result':'PASS','at':now(),'runtime_directory':str(directory()),
            'python':platform.python_version(),'node':command(['node','--version'],15),
            'npm':command(['npm','--version'],15),'uv':command(['uv','--version'],15)}
    atomic(Path(root)/'.harness/runtime.json', report)
    return report
