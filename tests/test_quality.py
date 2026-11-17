"""Quality profile contracts and an actual failing-check -> repair -> recheck loop."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platform_support import symlink

from harnesslib import processes, quality, runner, verification
from harnesslib.core import Harness
from harnesslib.storage import HarnessError, atomic, read, validate_schema

KIT = Path(__file__).resolve().parents[1]


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "schemas").mkdir()
        shutil.copy(
            KIT / "schemas/checks.schema.json", self.root / "schemas/checks.schema.json"
        )
        atomic(
            self.root / ".harness/checks.json",
            {"schema_version": 1, "stack_revision": None, "checks": {}},
        )

    def write(self, path, text=""):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def check(self, argv=None):
        return {
            "kind": "command",
            "argv": argv or ["{python}", "-c", 'print("checked")'],
            "timeout_seconds": 10,
            "approved": True,
            "approval_reference": "Isolated test fixture",
            "purpose": "Exercise isolated quality execution",
        }

    def test_detect_polyglot_and_script_only_without_execution(self):
        for p in [
            "api/pyproject.toml",
            "api/src/main.py",
            "ui/package.json",
            "ui/tsconfig.json",
            "ui/src/app.ts",
            "mobile/App.csproj",
            "mobile/App.cs",
            "scripts/check.sh",
            "scripts/setup.ps1",
            "scripts/utility.py",
            "node_modules/dependency/index.js",
        ]:
            self.write(p)
        found = {
            (m["path"], m["profile"]) for m in quality.detect(self.root)["modules"]
        }
        for item in [
            ("api", "python"),
            ("ui", "typescript"),
            ("mobile", "csharp"),
            ("scripts", "shell"),
            ("scripts", "powershell"),
            ("scripts", "python"),
        ]:
            self.assertIn(item, found)
        self.assertFalse(any("node_modules" in path for path, _ in found))

    def test_all_profiles_generate_schema_valid_unapproved_checks(self):
        self.write("templates/quality/semgrep.json", '{"rules": []}')
        for profile, categories in quality.PROFILES.items():
            result = quality.plan(self.root, profile, categories=list(categories))
            validate_schema(
                {
                    "schema_version": 1,
                    "stack_revision": None,
                    "checks": result["checks"],
                },
                read(KIT / "schemas/checks.schema.json"),
            )
            self.assertTrue(result["checks"])
            self.assertTrue(all(not c["approved"] for c in result["checks"].values()))
            self.assertTrue(
                all(
                    "{cache}" not in c["argv"] and "{rules}" not in c["argv"]
                    for c in result["checks"].values()
                )
            )
        self.assertEqual(read(self.root / ".harness/checks.json")["checks"], {})

    def test_apply_requires_current_preview_preserves_approvals_and_conflicts(self):
        preview = quality.plan(self.root, "python")
        with self.assertRaises(HarnessError):
            quality.plan(self.root, "python", apply=True)
        quality.plan(self.root, "python", apply=True, expected=preview["expected"])
        cfg = read(self.root / ".harness/checks.json")
        name = next(iter(cfg["checks"]))
        cfg["checks"][name].update(
            approved=True, approval_reference="Real fixture approval"
        )
        atomic(self.root / ".harness/checks.json", cfg)
        with self.assertRaises(HarnessError):
            quality.plan(self.root, "python", apply=True, expected=preview["expected"])
        preview = quality.plan(self.root, "python")
        quality.plan(self.root, "python", apply=True, expected=preview["expected"])
        self.assertTrue(
            read(self.root / ".harness/checks.json")["checks"][name]["approved"]
        )
        cfg["checks"][name]["argv"].append("--custom")
        atomic(self.root / ".harness/checks.json", cfg)
        preview = quality.plan(self.root, "python")
        self.assertEqual(preview["result"], "BLOCKED")
        with self.assertRaises(HarnessError):
            quality.plan(self.root, "python", apply=True, expected=preview["expected"])
        self.assertEqual(read(self.root / ".harness/checks.json"), cfg)

    def test_module_names_and_workspace_node_tools(self):
        self.write("front end/package.json", "{}")
        self.write("node_modules/eslint/bin/eslint.js")
        result = quality.plan(self.root, "typescript", "front end", ["lint"])
        check = next(iter(result["checks"].values()))
        self.assertEqual(check["cwd"], "front end")
        self.assertEqual(check["argv"][1], "../node_modules/eslint/bin/eslint.js")
        self.assertNotIn("npx", check["argv"])

    def test_traversal_and_symlink_module_rejected(self):
        with self.assertRaises(HarnessError):
            quality.plan(self.root, "python", "../")
        self.write("real/file.py")
        symlink(self.root / "linked", self.root / "real")
        with self.assertRaises(HarnessError):
            quality.plan(self.root, "python", "linked")

    def test_module_and_rules_cannot_escape_evidence_inventory(self):
        self.write(".harness/hidden-rule.json", '{"rules": []}')
        with self.assertRaises(HarnessError):
            quality.plan(self.root, "python", ".harness")
        with self.assertRaises(HarnessError):
            quality.plan(self.root, "security", rules=".harness/hidden-rule.json")

    def test_dynamic_scripts_include_new_files_and_reject_empty(self):
        check = self.check(["shellcheck", "--"])
        check["file_extensions"] = [".sh"]
        with self.assertRaises(HarnessError):
            quality.prepare(self.root, check)
        self.write("-danger.sh")
        self.assertIn("./-danger.sh", quality.prepare(self.root, check)[1])
        self.write("nested/new.sh")
        self.assertIn("./nested/new.sh", quality.prepare(self.root, check)[1])
        self.write("node_modules/ignored.sh")
        self.assertFalse(
            any("ignored" in x for x in quality.prepare(self.root, check)[1])
        )

    def test_actual_subprocess_cwd_version_and_nonzero(self):
        self.write("module with spaces/input.txt", "expected")
        check = self.check(
            [
                "{python}",
                "-c",
                'from pathlib import Path; assert Path("input.txt").read_text()=="expected"',
            ]
        )
        check.update(cwd="module with spaces", version_argv=["{python}", "--version"])
        h = Harness(self.root)
        with patch.object(h, "state", return_value={}):
            result = h.run_check("quality-fixture", check)
            self.assertEqual(result["result"], "PASS", result)
            self.assertIn("Python", result["tool_version"])
            self.assertTrue((self.root / result["log"]).is_file())
            check["argv"] = ["{python}", "-c", "raise SystemExit(1)"]
            self.assertEqual(h.run_check("quality-fixture", check)["result"], "FAIL")

    def test_unapproved_does_not_even_probe_version(self):
        check = self.check()
        check.update(approved=False, version_argv=["missing-quality-tool", "--version"])
        with patch.object(quality, "version") as probe:
            self.assertEqual(
                Harness(self.root).run_check("quality-test", check)["result"], "NOT_RUN"
            )
            probe.assert_not_called()

    def test_missing_tool_version_mismatch_timeout_and_empty_scripts_block(self):
        h = Harness(self.root)
        check = self.check()
        for version in [
            ["specreceipt-no-such-tool", "--version"],
            ["{python}", "-c", "raise SystemExit(2)"],
        ]:
            check["version_argv"] = version
            self.assertEqual(h.run_check("quality-test", check)["result"], "BLOCKED")
        check.update(
            version_argv=["{python}", "--version"], expected_version="not this version"
        )
        self.assertEqual(h.run_check("quality-test", check)["result"], "BLOCKED")
        check.pop("expected_version")
        with patch.object(
            quality.processes,
            "run",
            side_effect=subprocess.TimeoutExpired("fixture", 1),
        ):
            self.assertEqual(h.run_check("quality-test", check)["result"], "BLOCKED")
        check["file_extensions"] = [".sh"]
        self.assertEqual(h.run_check("quality-test", check)["result"], "BLOCKED")

    def test_policy_snapshot_detects_new_suppressions_and_configuration(self):
        h = Harness(self.root)
        before = quality.policy_snapshot(h)
        self.write(".semgrepignore", "src/\n")
        self.assertNotEqual(quality.policy_snapshot(h), before)
        self.write("pyproject.toml", '[tool.ruff.lint]\nignore=["F401"]\n')
        second = quality.policy_snapshot(h)
        self.assertNotEqual(second, before)
        self.write("code.py", 'print("normal implementation change")')
        self.assertEqual(quality.policy_snapshot(h), second)

    def test_security_uses_local_rules_and_redacts_secrets(self):
        self.write("templates/quality/semgrep.json", '{"rules": []}')
        preview = quality.plan(self.root, "security")
        checks = list(preview["checks"].values())
        self.assertIn("--metrics=off", checks[0]["argv"])
        self.assertNotIn("auto", checks[0]["argv"])
        self.assertIn("--redact", checks[1]["argv"])
        self.assertNotIn(
            "dependencies", [name.rsplit("-", 1)[-1] for name in preview["checks"]]
        )

    def test_public_cli_keeps_leak_check_preview_reviewable(self):
        self.write("templates/quality/semgrep.json", '{"rules": []}')
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(KIT / "harness"),
                "--root",
                str(self.root),
                "quality",
                "plan",
                "--profile",
                "security",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(all(isinstance(c, dict) for c in data["checks"].values()))
        self.assertEqual(len(data["checks"]), 2)
        self.assertEqual(read(self.root / ".harness/checks.json")["checks"], {})

    def test_tool_state_stays_local_and_credentials_are_not_inherited(self):
        check = self.check(["semgrep", "scan"])
        check["quality_profile"] = "security"
        with patch.dict(
            "os.environ",
            {
                "SEMGREP_APP_TOKEN": "private-fixture",
                "SSL_CERT_FILE": "/fixture/ca.pem",
            },
        ):
            env = quality.environment(self.root, check)
        self.assertNotIn("SEMGREP_APP_TOKEN", env)
        self.assertEqual(env["SSL_CERT_FILE"], "/fixture/ca.pem")
        self.assertTrue(
            Path(env["SEMGREP_SETTINGS_FILE"]).is_relative_to(self.root / ".harness")
        )
        check["quality_profile"] = "csharp"
        self.assertTrue(
            Path(
                quality.environment(self.root, check)["DOTNET_CLI_HOME"]
            ).is_relative_to(self.root / ".harness")
        )

    @unittest.skipUnless(
        os.environ.get("HARNESS_REAL_DOTNET"), "Optional real .NET SDK8+ boundary"
    )
    def test_real_csharp_format_preserves_source_inventory(self):
        dotnet = os.environ["HARNESS_REAL_DOTNET"]
        module = self.root / "app"
        module.mkdir()
        preview = quality.plan(self.root, "csharp", "app", ["format"])
        name, check = next(iter(preview["checks"].items()))
        check.update(
            approved=True,
            approval_reference="Isolated real SDK test fixture",
            timeout_seconds=60,
        )
        check["argv"][0] = dotnet
        check["version_argv"][0] = dotnet
        env = quality.environment(self.root, check)
        major = int(quality.version(self.root, check).split(".")[0])
        self.assertGreaterEqual(major, 8)
        self.write(
            "app/App.csproj",
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            f"<OutputType>Exe</OutputType><TargetFramework>net{major}.0</TargetFramework>"
            "</PropertyGroup></Project>",
        )
        self.write(
            "app/Program.cs",
            'class C{static void Main(){System.Console.WriteLine("hello");}}\n',
        )
        feed = self.root / ".harness/empty-feed"
        feed.mkdir()
        restore = [
            dotnet,
            *preview["preparation"]["restore_argv"][1:],
            "--source",
            str(feed),
        ]
        processes.run(
            restore,
            cwd=module,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        h = Harness(self.root)
        before = verification.inventory(self.root)
        with patch.object(h, "state", return_value={}):
            result = h.run_check(name, check)
            self.assertEqual(result["result"], "FAIL", result)
            self.assertIn("WHITESPACE", result["summary"])
            self.assertEqual(verification.inventory(self.root), before)
            processes.run(
                [dotnet, "format", "--no-restore"],
                cwd=module,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            repaired = verification.inventory(self.root)
            self.assertNotEqual(repaired, before)
            result = h.run_check(name, check)
            self.assertEqual(result["result"], "PASS", result)
            self.assertEqual(verification.inventory(self.root), repaired)


class QualityLoopTests(unittest.TestCase):
    def setUp(self):
        from test_harness import HarnessTests

        self.fixture = HarnessTests("test_invalid_state_rejected")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.h, self.root = self.fixture.h, self.fixture.root
        cfg = read(self.root / ".harness/checks.json")
        cfg["checks"]["quality-fixture"] = {
            "kind": "command",
            "argv": [
                "{python}",
                "-c",
                'from pathlib import Path; import sys; bad="bad-pattern" in Path("docs/DEMO.md").read_text(); print("DEMO.md:1: fixture-rule: remove bad-pattern" if bad else "clean"); sys.exit(int(bad))',
            ],
            "version_argv": ["{python}", "--version"],
            "quality_profile": "python",
            "timeout_seconds": 5,
            "approved": True,
            "approval_reference": "Isolated test authorization",
            "purpose": "Detect a concrete defect in the isolated repair fixture",
        }
        atomic(self.root / ".harness/checks.json", cfg)
        path = self.root / "specs/harness-demo/tasks.json"
        feature = read(path)
        task = feature["tasks"][0]
        task["required_checks"] = ["quality-fixture"]
        task["acceptance_checks"] = [
            {"criterion": c, "checks": ["quality-fixture"]}
            for c in task["acceptance_criteria"]
        ]
        atomic(path, feature)
        (self.root / "docs/DEMO.md").write_text("checkpoint resume bad-pattern\n")

    def test_finding_reaches_host_then_repair_is_verified(self):
        self.fixture.implemented()
        first = runner.run(self.h, 12, 600)
        self.assertEqual(first["host_role"]["role"], "implement", first)
        self.assertTrue(first["quality_repair"]["checks"][0]["log"])
        self.assertIn("fixture-rule", first["quality_repair"]["checks"][0]["summary"])
        self.assertIn(
            "REWORK", [x["to"] for x in self.h.task("DEMO-001")[1]["history"]]
        )
        (self.root / "docs/DEMO.md").write_text("checkpoint resume repaired\n")
        runner.submit(self.h, first["host_role"]["request_id"], "fixture implementer")
        result = runner.run(self.h, 12, 600)
        self.assertEqual(result["action"], "review", result)
        self.assertEqual(self.h.task("DEMO-001")[1]["status"], "VERIFIED")
        self.assertEqual(quality.report(self.h, "DEMO-001")["result"], "PASS")

    def test_missing_analyzer_stops_without_rework(self):
        cfg = read(self.root / ".harness/checks.json")
        cfg["checks"]["quality-fixture"]["version_argv"] = [
            "specreceipt-no-such-tool",
            "--version",
        ]
        atomic(self.root / ".harness/checks.json", cfg)
        self.fixture.implemented()
        result = runner.run(self.h, 12, 600)
        self.assertEqual(result["action"], "repair-environment", result)
        self.assertEqual(self.h.task("DEMO-001")[1]["status"], "IMPLEMENTED")
        self.assertNotIn(
            "REWORK", [x["to"] for x in self.h.task("DEMO-001")[1]["history"]]
        )

    def test_automatic_repair_cannot_add_ignore_policy(self):
        self.fixture.implemented()
        first = runner.run(self.h, 12, 600)
        (self.root / ".semgrepignore").write_text("docs/\n")
        with self.assertRaisesRegex(HarnessError, "quality policy"):
            runner.submit(
                self.h, first["host_role"]["request_id"], "fixture implementer"
            )


if __name__ == "__main__":
    unittest.main()
