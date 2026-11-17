"""Project-local quality profiles, using the existing command/evidence lifecycle.

Discovery and planning never execute repository code or install tools. Applying a
plan registers unapproved checks; consumer authorization remains project-owned.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from . import processes, verification
from .storage import (
    HarnessError,
    atomic,
    digest,
    is_link,
    read,
    safe_path,
    validate_schema,
)

EXCLUDED = {
    ".git",
    ".harness",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "bin",
    "obj",
    "dist",
    "build",
    "coverage",
    "vendor",
    "target",
    "assets",
}
PROFILES = {
    "python": {
        "format": ["ruff", "format", "--no-cache", "--check", "."],
        "lint": ["ruff", "check", "--no-cache", "."],
        "types": ["{python}", "-m", "mypy", "--cache-dir", "{cache}", "."],
        "tests": ["{python}", "-m", "pytest", "-p", "no:cacheprovider", "."],
    },
    "javascript": {
        "format": ["node", "node_modules/prettier/bin/prettier.cjs", "--check", "."],
        "lint": [
            "node",
            "node_modules/eslint/bin/eslint.js",
            ".",
            "--max-warnings",
            "0",
        ],
        "tests": ["npm", "test"],
    },
    "typescript": {
        "format": ["node", "node_modules/prettier/bin/prettier.cjs", "--check", "."],
        "lint": [
            "node",
            "node_modules/eslint/bin/eslint.js",
            ".",
            "--max-warnings",
            "0",
        ],
        "types": ["node", "node_modules/typescript/bin/tsc", "--noEmit"],
        "tests": ["npm", "test"],
    },
    "csharp": {
        "format": ["dotnet", "format", "--verify-no-changes", "--no-restore"],
        "lint": [
            "dotnet",
            "build",
            "--no-restore",
            "-warnaserror",
            "--artifacts-path",
            "{cache}",
        ],
        "tests": ["dotnet", "test", "--no-restore", "--artifacts-path", "{cache}"],
    },
    "shell": {"lint": ["shellcheck", "--severity=style", "--"]},
    "powershell": {
        "lint": [
            "pwsh",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "$ErrorActionPreference='Stop'; Import-Module PSScriptAnalyzer -ErrorAction Stop; "
                "$items=@(Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error,Warning); "
                "$items | Format-List; if ($items.Count -gt 0) { exit 1 }"
            ),
        ]
    },
    "go": {"lint": ["go", "vet", "./..."], "tests": ["go", "test", "./..."]},
    "rust": {
        "format": ["cargo", "fmt", "--all", "--check"],
        "lint": [
            "cargo",
            "clippy",
            "--offline",
            "--target-dir",
            "{cache}",
            "--all-targets",
            "--",
            "-D",
            "warnings",
        ],
        "tests": ["cargo", "test", "--offline", "--target-dir", "{cache}"],
    },
    "security": {
        "sast": [
            "semgrep",
            "scan",
            "--error",
            "--strict",
            "--metrics=off",
            "--disable-version-check",
            "--config",
            "{rules}",
            ".",
        ],
        "secrets": ["gitleaks", "dir", "--redact", "."],
        "dependencies": ["osv-scanner", "scan", "source", "--recursive", "."],
    },
}
DEFAULTS = {
    p: [k for k in checks if k in {"format", "lint"}] for p, checks in PROFILES.items()
}
DEFAULTS["security"] = ["sast", "secrets"]
RULE_NAMES = {
    "pyproject.toml",
    "ruff.toml",
    ".ruff.toml",
    ".editorconfig",
    ".semgrepignore",
    ".gitleaksignore",
    ".gitleaks.toml",
    ".gitignore",
    ".shellcheckrc",
    ".eslintignore",
    ".prettierignore",
    "mypy.ini",
    ".mypy.ini",
    "setup.cfg",
    "pytest.ini",
    "Cargo.toml",
    "clippy.toml",
    ".clippy.toml",
    "rustfmt.toml",
    ".rustfmt.toml",
    "Directory.Build.props",
    "Directory.Build.targets",
    "PSScriptAnalyzerSettings.psd1",
    "package.json",
}


def files(root, relative="."):
    """Bounded inventory; never traverse symlinks or dependency/build trees."""
    base = safe_path(root, relative)
    if not base.is_dir():
        raise HarnessError("Quality module must be an existing directory: " + relative)
    count = 0
    for directory, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs if d not in EXCLUDED and not is_link(Path(directory) / d)
        )
        for name in sorted(names):
            path = Path(directory) / name
            if is_link(path):
                continue
            count += 1
            if count > 100000:
                raise HarnessError(
                    "Quality discovery exceeds 100000 files; select a smaller module"
                )
            yield path


def catalog():
    return {
        "result": "PASS",
        "profiles": {
            name: {"checks": list(checks), "defaults": DEFAULTS[name]}
            for name, checks in PROFILES.items()
        },
        "notice": "Tools must already be installed. Tests/types and dependency network scans are explicit opt-ins. Profiles do not grant task or execution approval.",
    }


def detect(root):
    modules = {}
    suffixes = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".cs": "csharp",
        ".sh": "shell",
        ".bash": "shell",
        ".ps1": "powershell",
        ".psm1": "powershell",
        ".go": "go",
        ".rs": "rust",
    }
    manifests = {
        "pyproject.toml": "python",
        "setup.py": "python",
        "requirements.txt": "python",
        "package.json": "javascript",
        "tsconfig.json": "typescript",
        "go.mod": "go",
        "Cargo.toml": "rust",
    }
    inventory = list(files(root))
    anchors = {}
    for path in inventory:
        profile = (
            "csharp"
            if path.suffix in {".csproj", ".sln", ".slnx"}
            else manifests.get(path.name)
        )
        if profile:
            anchors.setdefault(path.parent, set()).add(profile)
    for path in inventory:
        profile = suffixes.get(path.suffix)
        if profile:
            owner = next(
                (
                    p
                    for p in [path.parent, *path.parents]
                    if profile in anchors.get(p, set())
                ),
                path.parent,
            )
            modules.setdefault(
                (owner.relative_to(root).as_posix(), profile), set()
            ).add(path.relative_to(root).as_posix())
    for directory, profiles in anchors.items():
        for profile in profiles:
            modules.setdefault((directory.relative_to(root).as_posix(), profile), set())
    return {
        "result": "PASS",
        "modules": [
            {"path": p, "profile": profile, "examples": sorted(examples)[:3]}
            for (p, profile), examples in sorted(modules.items())
        ],
        "notice": "Suggestions only; select module boundaries explicitly, especially script-only directories.",
    }


def _node_entry(root, module, entry):
    # Reuse workspace-installed tools; never invoke npx or download packages.
    for directory in [module, *module.parents]:
        if not directory.is_relative_to(root):
            break
        candidate = directory / entry
        if candidate.is_file():
            safe_path(root, candidate.relative_to(root).as_posix())
            return os.path.relpath(candidate, module).replace(os.sep, "/")
    return entry


def plan(
    root, profile, path=".", categories=None, apply=False, expected=None, rules=None
):
    root = Path(root).resolve()
    module = safe_path(root, path)
    if not module.is_dir():
        raise HarnessError("Quality module must be an existing directory")
    if profile not in PROFILES:
        raise HarnessError("Unknown quality profile: " + profile)
    path = module.relative_to(root).as_posix()
    if path != ".":
        verification.validate_scope(root, [path + "/"])
    selected = list(dict.fromkeys(categories or DEFAULTS[profile]))
    if not selected or set(selected) - set(PROFILES[profile]):
        raise HarnessError("Unsupported check category for " + profile)
    config_path = safe_path(root, ".harness/checks.json")
    config = read(config_path)
    validate_schema(config, read(root / "schemas/checks.schema.json"))
    checks = {}
    for category in selected:
        argv = list(PROFILES[profile][category])
        if "{cache}" in argv:
            cache = safe_path(
                root, ".harness/quality-artifacts/" + digest(path)[:12] + "/" + profile
            )
            argv[argv.index("{cache}")] = os.path.relpath(cache, module).replace(
                os.sep, "/"
            )
        if "{rules}" in argv:
            rules = rules or "templates/quality/semgrep.json"
            verification.validate_scope(root, [rules])
            rules_path = safe_path(root, rules)
            if not rules_path.is_file():
                raise HarnessError("SAST requires a checked-in local rules file")
            argv[argv.index("{rules}")] = os.path.relpath(rules_path, module).replace(
                os.sep, "/"
            )
        if argv[0] == "node":
            argv[1] = _node_entry(root, module, argv[1])
        if argv[:3] == ["{python}", "-m", "mypy"] or argv[:3] == [
            "{python}",
            "-m",
            "pytest",
        ]:
            version = [*argv[:3], "--version"]
        elif argv[0] == "node":
            version = [*argv[:2], "--version"]
        elif argv[0] == "go":
            version = ["go", "version"]
        elif argv[0] == "semgrep":
            version = [
                "semgrep",
                "scan",
                "--version",
                "--disable-version-check",
                "--metrics=off",
            ]
        elif profile == "powershell":
            version = [
                "pwsh",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "$ErrorActionPreference='Stop'; Import-Module PSScriptAnalyzer -ErrorAction Stop; "
                    "(Get-Module PSScriptAnalyzer).Version.ToString()"
                ),
            ]
        else:
            version = [argv[0], "--version"]
        # Generic output redaction treats dictionary keys containing "secret"
        # as sensitive. Keep this public check definition reviewable.
        suffix = "leak-scan" if category == "secrets" else category
        name = f"quality-{profile}-{digest(path)[:12]}-{suffix}"
        check = {
            "kind": "command",
            "argv": argv,
            "cwd": path,
            "timeout_seconds": 600,
            "approved": False,
            "approval_reference": "",
            "purpose": f"{profile} {category} for module {path}; fail on reported violations",
            "quality_profile": profile,
            "version_argv": version,
        }
        if profile == "shell":
            check["file_extensions"] = [".sh", ".bash"]
        checks[name] = check
    conflicts = [
        n
        for n, c in checks.items()
        if n in config["checks"]
        and {
            k: v
            for k, v in config["checks"][n].items()
            if k not in {"approved", "approval_reference"}
        }
        != {k: v for k, v in c.items() if k not in {"approved", "approval_reference"}}
    ]
    signature = digest({"configuration": config, "checks": checks})
    if apply:
        if expected != signature:
            raise HarnessError(
                "Quality plan changed or --expected is missing; preview the current plan"
            )
        if conflicts:
            raise HarnessError(
                "Existing checks differ; refusing to overwrite project configuration: "
                + ", ".join(conflicts)
            )
        for name, check in checks.items():
            config["checks"].setdefault(name, check)
        validate_schema(config, read(root / "schemas/checks.schema.json"))
        atomic(config_path, config)
    return {
        "result": "BLOCKED" if conflicts else "PASS",
        "profile": profile,
        "path": path,
        "expected": signature,
        "checks": checks,
        "conflicts": conflicts,
        "applied": apply,
        "required_checks": list(checks),
        "preparation": (
            {
                "restore_argv": [
                    "dotnet",
                    "restore",
                    "--artifacts-path",
                    os.path.relpath(
                        root
                        / ".harness/quality-artifacts"
                        / digest(path)[:12]
                        / profile,
                        module,
                    ).replace(os.sep, "/"),
                ],
                "cwd": path,
                "automatic": False,
            }
            if profile == "csharp"
            else None
        ),
        "next_action": "Review commands/configuration and record real execution authorization in checks.json. Add check IDs to the approved task required_checks (or workflow policy). Run verify through the normal lifecycle.",
        "notice": "Registration is not execution, task enrollment, tool installation, or a passing quality result.",
    }


def prepare(root, check):
    """Resolve module and dynamic script inventory without executing anything."""
    cwd = safe_path(root, check.get("cwd", "."))
    if not cwd.is_dir():
        raise HarnessError("Check working directory is unavailable")
    argv = [sys.executable if v == "{python}" else v for v in check["argv"]]
    extensions = check.get("file_extensions")
    if extensions:
        if any(not re.fullmatch(r"\.[A-Za-z0-9]+", ext) for ext in extensions):
            raise HarnessError("Invalid script extension")
        selected = [
            p for p in files(root, check.get("cwd", ".")) if p.suffix in extensions
        ]
        if not selected:
            raise HarnessError("No matching scripts; refusing an empty quality check")
        # Prefix ./ so filenames beginning with '-' cannot become tool options.
        argv += ["./" + p.relative_to(cwd).as_posix() for p in selected]
    return cwd, argv


def version(root, check):
    cwd, _ = prepare(root, check)
    argv = [sys.executable if v == "{python}" else v for v in check["version_argv"]]
    try:
        result = processes.run(
            argv,
            cwd=cwd,
            env=environment(root, check),
            capture_output=True,
            text=True,
            timeout=min(10, check["timeout_seconds"]),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError("Quality tool unavailable: " + str(exc)) from exc
    output = (result.stdout + result.stderr).strip()
    if result.returncode or not output:
        raise HarnessError("Quality tool version probe failed: " + output[-1500:])
    if check.get("expected_version") and output != check["expected_version"]:
        raise HarnessError(
            "Quality tool version differs from the approved expected_version"
        )
    return output[:4096]


def environment(root, check):
    env = processes.environment()
    if check.get("quality_profile") == "csharp":
        directory = safe_path(root, ".harness/quality-artifacts/dotnet-cli")
        directory.mkdir(parents=True, exist_ok=True)
        env.update(
            DOTNET_CLI_HOME=str(directory),
            DOTNET_CLI_TELEMETRY_OPTOUT="1",
            DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
        )
        module = (
            safe_path(root, check.get("cwd", "."))
            .relative_to(Path(root).resolve())
            .as_posix()
        )
        env.update(
            UseArtifactsOutput="true",
            ArtifactsPath=str(
                safe_path(
                    root,
                    ".harness/quality-artifacts/" + digest(module)[:12] + "/csharp",
                )
            ),
        )
    if check.get("quality_profile") == "security" and check["argv"][0] == "semgrep":
        directory = safe_path(root, ".harness/quality-artifacts/semgrep")
        directory.mkdir(parents=True, exist_ok=True)
        env.update(
            SEMGREP_LOG_FILE=str(
                safe_path(root, ".harness/quality-artifacts/semgrep/tool.log")
            ),
            SEMGREP_SETTINGS_FILE=str(
                safe_path(root, ".harness/quality-artifacts/semgrep/settings.yml")
            ),
            SEMGREP_SEND_METRICS="off",
        )
        # Honor explicit trust-store locations without inheriting credentials.
        for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"):
            if name in os.environ:
                env[name] = os.environ[name]
    return env


def repair_context(h, task):
    if not task.get("evidence"):
        return None
    config = read(h.root / ".harness/checks.json")["checks"]
    if not any(
        config.get(n, {}).get("quality_profile")
        for dependency in h.check_closure(task)
        for n in dependency["required_checks"]
    ):
        return None
    evidence = h.evidence(task["evidence"][-1])
    failures = [
        r
        for r in evidence["results"]
        if r["result"] != "PASS" and config.get(r["check"], {}).get("quality_profile")
    ]
    if not failures:
        return None
    return {
        "evidence": task["evidence"][-1],
        "checks": failures,
        "instructions": "Read the referenced full logs and existing module rules. Fix root causes only inside approved task scope. Do not weaken rules, suppress findings, alter checks/thresholds, or treat missing tools as code defects. Out-of-scope defects and policy changes require a developer decision. Re-run all required verification after repairs.",
    }


def context(h, task):
    config = read(h.root / ".harness/checks.json")["checks"]
    selected = {
        n: config[n]
        for t in h.check_closure(task)
        for n in t["required_checks"]
        if config.get(n, {}).get("quality_profile")
    }
    if not selected:
        return None
    return {
        "checks": selected,
        "instructions": "Before editing, read the existing analyzer, formatter and architecture rules for each check cwd (including inherited workspace configuration). Follow these standards while implementing. Checks run without auto-fix. Do not add suppressions or weaken rules to obtain PASS. Quality checks supplement functional acceptance tests and security review.",
    }


def policy_snapshot(h):
    """Keep analyzer policy fixed during automatic repair, including new ignores."""
    paths = {
        p.relative_to(h.root).as_posix()
        for p in files(h.root)
        if p.name in RULE_NAMES
        or p.name.startswith(
            (
                "eslint.config.",
                ".eslintrc",
                ".prettier",
                "tsconfig",
                ".semgrep",
                "semgrep",
                "sonar-project",
                "Directory.Build.",
            )
        )
        or p.suffix in {".ruleset", ".globalconfig", ".csproj"}
    }
    config = read(h.root / ".harness/checks.json")
    for check in config["checks"].values():
        if check.get("quality_profile") == "security" and "--config" in check["argv"]:
            value = check["argv"][check["argv"].index("--config") + 1]
            path = (h.root / check.get("cwd", ".") / value).resolve()
            if not path.is_relative_to(h.root):
                raise HarnessError("Security rules must remain inside the project")
            paths.add(path.relative_to(h.root).as_posix())
    return digest(
        {
            "checks": config,
            "rules": {
                p: digest(safe_path(h.root, p).read_text(encoding="utf-8"))
                for p in sorted(paths)
            },
        }
    )


def report(h, task_id):
    task = h.task(task_id)[1]
    if not task["evidence"]:
        return {"result": "NOT_RUN", "task_id": task_id, "checks": []}
    evidence = h.evidence(task["evidence"][-1])
    config = read(h.root / ".harness/checks.json")["checks"]
    results = [
        r
        for r in evidence["results"]
        if config.get(r["check"], {}).get("quality_profile")
    ]
    current = h.current_evidence(task)
    return {
        "result": "NOT_RUN" if not results else "PASS" if current else "BLOCKED",
        "task_id": task_id,
        "evidence": task["evidence"][-1],
        "current_acceptance": current,
        "checks": results,
        "repair": repair_context(h, task),
        "notice": "Historical findings are diagnostic; only current complete verification establishes acceptance.",
    }
