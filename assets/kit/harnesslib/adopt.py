"""Copy the reusable kit without replacing project-owned files or demonstration state."""
from pathlib import Path
import shutil
import subprocess
from .storage import HarnessError

KIT_PATHS = ['install.sh','scripts/python.sh','scripts/update-tools.py','harness','harnesslib','schemas','templates','.agents/skills','tests','docs/HARNESS.md','docs/V02.md','docs/TECH_SPEC.md',
             'docs/ARCHITECTURE.md','docs/DECISION_QUEUE.md','docs/adr','AGENTS.md','.harness/checks.json',
             '.harness/graph-config.json','.harness/environment.json','.harness/onboarding.json']
ENTRYPOINTS = {
    'AGENTS.override.md': 'codex.md',
    '.claude/rules/harness-bootstrap.md': 'claude.md',
    '.github/instructions/harness-bootstrap.instructions.md': 'copilot.md',
    '.harness/BOOTSTRAP.md': 'bootstrap.md',
}

INDEX_IGNORES = ('graphify-out/', '.codegraph/', '.codegraph-wsl/')

def git_context(destination):
    """Resolve local excludes through Git, including nested installs and worktrees."""
    probe = destination
    while not probe.exists():
        probe = probe.parent
    if not shutil.which('git'):
        return None
    result = subprocess.run(['git', '-C', str(probe), 'rev-parse', '--show-toplevel'],
                            capture_output=True, text=True)
    if result.returncode:
        return None
    root = Path(result.stdout.strip()).resolve()
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--git-path', 'info/exclude'],
                            capture_output=True, text=True, check=True)
    exclude = Path(result.stdout.strip())
    if not exclude.is_absolute():
        exclude = root / exclude
    return root, exclude


def ignore_pattern(path):
    # Literal repository-relative paths, even when the project name contains glob syntax.
    return '/' + ''.join('\\' + c if c in '\\*?[]!# ' else c for c in path)


def adopt(source, destination, dry_run=True):
    source,destination = Path(source).resolve(),Path(destination).resolve()
    if destination == source or destination.is_relative_to(source):
        raise HarnessError('Choose a target outside the kit directory')
    conflicts,files = [],[]
    preserved = []
    sources = {}
    for rel in KIT_PATHS:
        # Intake answers and sign-off belong to one project, never to a new adoption.
        path = source/('templates/onboarding.json' if rel == '.harness/onboarding.json' else rel)
        candidates = [path] if path.is_file() else sorted(path.rglob('*'))
        for candidate in candidates:
            if not candidate.is_file() or '__pycache__' in candidate.parts or candidate.is_symlink(): continue
            relative = Path(rel) if rel == '.harness/onboarding.json' else candidate.relative_to(source)
            target = destination/relative
            if target.is_file() and not target.is_symlink() and target.read_bytes() != candidate.read_bytes():
                if str(relative) == 'AGENTS.md':
                    preserved.append(str(relative))
                    relative = Path('.harness/AGENTS.md')
                elif str(relative).startswith('.agents/skills/'):
                    preserved.append(str(relative))
                    relative = Path('.harness/skills') / relative.relative_to('.agents/skills')
                target = destination/relative
            sources[str(relative)] = candidate
            if any(p.is_symlink() for p in [target,*target.parents]):
                raise HarnessError(f'Target symlink refused: {target}')
            if target.exists():
                if not target.is_file() or target.read_bytes() != candidate.read_bytes(): conflicts.append(str(relative))
            else: files.append(str(relative))
    # Preflight generated host bridges together with the kit; never overwrite corporate files.
    for rel, template in ENTRYPOINTS.items():
        candidate = source / 'templates/agent-entrypoints' / template
        if not candidate.is_file() or candidate.is_symlink():
            raise HarnessError('Missing agent entrypoint template: ' + template)
        target = destination / rel
        sources[rel] = candidate
        if any(p.is_symlink() for p in [target, *target.parents]):
            raise HarnessError(f'Target symlink refused: {target}')
        if target.exists():
            if not target.is_file() or target.read_bytes() != candidate.read_bytes():
                conflicts.append(rel)
        else:
            files.append(rel)
    context = git_context(destination)
    ignore_file = context[1] if context else destination / '.gitignore'
    if any(p.is_symlink() for p in [ignore_file, *ignore_file.parents]):
        raise HarnessError(f'Target symlink refused: {ignore_file}')
    prefix = destination.relative_to(context[0]).as_posix() if context else '.'
    prefix = '' if prefix == '.' else prefix + '/'
    owned = set(sources) | {'.harness/', *INDEX_IGNORES, 'docs/ENGINEERING_LOG.md'}
    owned.update(str(Path(rel).parent / '__pycache__') + '/' for rel in sources if rel.endswith('.py'))
    if not (destination / '.gitignore').exists():
        owned.add('.gitignore')
    ignore_targets = {destination / '.gitignore': [ignore_pattern(rel) for rel in sorted(owned)]}
    if context:
        ignore_targets[ignore_file] = [ignore_pattern(prefix + rel) for rel in sorted(owned)]
    additions = {}
    for path, patterns in ignore_targets.items():
        if any(p.is_symlink() for p in [path, *path.parents]):
            raise HarnessError(f'Target symlink refused: {path}')
        present = set(path.read_text().splitlines()) if path.exists() else set()
        additions[path] = [line for line in patterns if line not in present]
    ignore_additions = additions[destination / '.gitignore']
    tracked = []
    if context:
        result = subprocess.run(['git', '-C', str(context[0]), 'ls-files', '-z'],
                                capture_output=True, text=True, check=True)
        tracked = [rel for rel in result.stdout.split('\0') if rel and any(
            rel == prefix + name or (name.endswith('/') and rel.startswith(prefix + name))
            for name in owned)]
        conflicts.extend('Already tracked by Git: ' + rel for rel in tracked)
    if not dry_run and conflicts:
        raise HarnessError('Adoption has conflicts; no files copied. Merge these files explicitly: '+', '.join(conflicts))
    if not dry_run:
        # Write both sets of exclusions before copying so partial adoption stays ignored.
        for path, lines in additions.items():
            if not lines:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            previous = path.read_bytes() if path.exists() else b''
            with path.open('a') as stream:
                if previous and not previous.endswith(b'\n'):
                    stream.write('\n')
                stream.write('\n'.join(lines) + '\n')
        if context:
            # Project .gitignore rules have priority over local excludes. Fail visibly
            # if an explicit inclusion would expose kit files to a normal git add.
            probes = [prefix + name + ('harness-ignore-probe' if name.endswith('/') else '')
                      for name in sorted(owned)]
            result = subprocess.run(
                ['git', '-C', str(context[0]), 'check-ignore', '--no-index',
                 '--stdin', '-z', '-v', '--non-matching'],
                input='\0'.join(probes) + '\0', capture_output=True, text=True)
            fields = result.stdout.split('\0')[:-1]
            if result.returncode not in (0, 1) or len(fields) != 4 * len(probes):
                raise HarnessError('Could not verify local Git exclusions; no kit files copied.')
            exposed = [fields[i+3] for i in range(0, len(fields), 4)
                       if not fields[i+2] or fields[i+2].startswith('!')]
            if exposed:
                raise HarnessError('Project ignore rules expose harness files; no kit files copied: '
                                   + ', '.join(exposed))
        for rel in files:
            target = destination/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            # Exclusive creation prevents replacement if another process changes target after preflight.
            with target.open('xb') as stream: stream.write(sources[rel].read_bytes())
            if rel == 'harness': target.chmod(0o755)
    initialization = None
    if not dry_run:
        from .core import Harness
        initialization = Harness(destination).init()
    from .assessment import assess, current, inventory
    if dry_run:
        assessment = {'status': 'preview', 'inventory': inventory(destination)}
    elif current(destination).get('status') == 'assessed':
        assessment = {'assessment_status':'assessed', 'report':'.harness/assessment.json'}
    else:
        assessment = assess(destination)
    return {'initialization':initialization, 'agent_bootstrap':{'status':'preview' if dry_run else 'instructions_installed', 'entrypoints':list(ENTRYPOINTS), 'execution':'current_installing_agent_or_next_host_request', 'application_readiness':'not_asserted'}, 'assessment':assessment, 'preserved_project_files':preserved, 'dry_run':dry_run,'files':files,'conflicts':conflicts,'result':'BLOCKED' if conflicts else 'PASS',
            'gitignore_additions':ignore_additions, 'ignore_file':str(ignore_file),
            'exclude_additions':additions.get(context[1], []) if context else [],
            'tracked_conflicts':tracked,
            'next_action':'Installing agent: continue .harness/BOOTSTRAP.md now in the target project. Otherwise open a new local agent session and give the ordinary task; installed host instructions route bootstrap automatically. No separate setup prompt is required. Application readiness and host instruction loading are not asserted by file installation.'}
