"""Read-only access to role instructions, independent of agent discovery support."""
import re
from pathlib import Path
from .storage import HarnessError, safe_path


def catalog(root, name=None):
    root = Path(root).resolve()
    directory = safe_path(root, '.agents/skills')
    entries = []
    paths = {p.parent.name:p for p in directory.glob('*/SKILL.md')}
    paths.update({p.parent.name:p for p in safe_path(root, '.harness/skills').glob('*/SKILL.md')})
    for path in sorted(paths.values()):
        rel = path.relative_to(root).as_posix()
        safe_path(root, rel)
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', path.parent.name):
            raise HarnessError(f'Invalid skill directory name: {path.parent.name}')
        if not path.is_file():
            raise HarnessError(f'Skill instructions are not a file: {rel}')
        entries.append({'name': path.parent.name, 'path': rel})
    if name is not None:
        match = next((item for item in entries if item['name'] == name), None)
        if match is None:
            raise HarnessError(f'Unknown skill: {name}; use ./harness skills to list available roles.')
        content = safe_path(root, match['path']).read_text(encoding='utf-8')
        if not content.strip():
            raise HarnessError(f'Empty skill instructions: {match["path"]}')
        from .assessment import current
        report = current(root)
        supplements = []
        for rel in report.get('role_skills', {}).get(name, []):
            if rel != match['path']:
                supplements.append({'path':rel, 'instructions':safe_path(root, rel).read_text(encoding='utf-8')})
        return {'result': 'PASS', **match, 'instructions': content,
                'project_skills':supplements, 'assessment_status':report['status'],
                'notice': 'Reading instructions does not execute a role or grant permissions.'}
    return {'result': 'PASS' if entries else 'BLOCKED', 'skills': entries,
            'notice': 'Read a selected role with ./harness skills NAME; no agent is launched.'}
