"""Launcher dependency checks, with synthetic metadata and no package installs."""
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("campus_launcher", ROOT / "scripts" / "launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
REPOSITORY = "https://github.com/vvbbnn00/shanghaitech-ids-passkey.git"
COMMIT = "7c4df62716ceb3d94452d22f3d07f19ff1b8db8b"
GIT_REQUIREMENT = "shanghaitech-ids-passkey @ git+" + REPOSITORY + "@" + COMMIT


def distribution(version="0.1.0", origin=None):
    return SimpleNamespace(version=version, read_text=lambda name: origin)


def check(requirements, installed, module_available=True):
    def lookup(name):
        if name not in installed:
            raise importlib.metadata.PackageNotFoundError(name)
        return installed[name]

    with patch.object(launcher.tomllib, "loads", return_value={"project": {"dependencies": requirements}}), \
         patch.object(launcher.importlib.metadata, "distribution", side_effect=lookup), \
         patch.object(launcher.importlib.util, "find_spec", return_value=object() if module_available else None):
        launcher.check_runtime()


class RequirementsCheck(unittest.TestCase):
    def test_pinned_git_dependency_and_versioned_packages(self):
        origin = json.dumps({"url": REPOSITORY, "vcs_info": {"vcs": "git", "commit_id": COMMIT}})
        check(["filelock>=3", "deepseek-harness-sdk==0.1.5rc1", GIT_REQUIREMENT], {
            "filelock": distribution("3.17.0"),
            "deepseek-harness-sdk": distribution("0.1.5rc1"),
            "shanghaitech-ids-passkey": distribution(origin=origin),
        })

    def test_missing_packages_are_reported_together(self):
        with self.assertRaises(RuntimeError) as error:
            check(["filelock>=3", GIT_REQUIREMENT], {})
        self.assertIn("filelock>=3", str(error.exception))
        self.assertIn(GIT_REQUIREMENT, str(error.exception))
        self.assertNotIn("依赖声明已变化", str(error.exception))

    def test_git_dependency_requires_matching_repository_and_commit(self):
        origins = [None, "{}", "[]", "{broken}",
            json.dumps({"url": REPOSITORY, "vcs_info": {"vcs": "git", "commit_id": "f" * 40}}),
            json.dumps({"url": "https://example.org/other.git", "vcs_info": {"vcs": "git", "commit_id": COMMIT}}),
        ]
        for origin in origins:
            with self.subTest(origin=origin), self.assertRaisesRegex(RuntimeError, "缺少依赖或版本不符"):
                check([GIT_REQUIREMENT], {"shanghaitech-ids-passkey": distribution(origin=origin)})

    def test_version_mismatches_still_fail(self):
        for requirement, name, version in [("filelock>=3", "filelock", "2.9"),
                ("deepseek-harness-sdk==0.1.5rc1", "deepseek-harness-sdk", "0.1.5")]:
            with self.subTest(requirement=requirement), self.assertRaises(RuntimeError):
                check([requirement], {name: distribution(version)})

    def test_windows_dependency_marker(self):
        requirement = "tzdata>=2025.2; sys_platform == 'win32'"
        with patch.object(launcher.sys, "platform", "win32"):
            check([requirement], {"tzdata": distribution("2025.2")})
            with self.assertRaisesRegex(RuntimeError, "缺少依赖或版本不符"):
                check([requirement], {})
        with patch.object(launcher.sys, "platform", "linux"):
            check([requirement], {})
        with self.assertRaisesRegex(RuntimeError, "依赖条件已变化"):
            check(["tzdata>=2025.2; unknown_marker"], {})

    def test_missing_import_is_not_hidden(self):
        with self.assertRaisesRegex(RuntimeError, "无法找到模块"):
            check([], {}, module_available=False)


if __name__ == "__main__":
    unittest.main()
