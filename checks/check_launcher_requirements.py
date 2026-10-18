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

    def test_comma_ranges_enforce_both_bounds(self):
        for requirement, package, accepted, rejected in [
            ("pillow>=11,<13", "pillow", ("11", "11.0.0", "12.4.1"), ("10.9", "13", "13.0.0", "14")),
            ("pypdfium2>=5,<6", "pypdfium2", ("5", "5.8.0"), ("4.9", "6", "6.0.0")),
        ]:
            for version in accepted:
                with self.subTest(requirement=requirement, version=version):
                    check([requirement], {package: distribution(version)})
            for version in rejected:
                with self.subTest(requirement=requirement, version=version), self.assertRaisesRegex(RuntimeError, "缺少依赖或版本不符"):
                    check([requirement], {package: distribution(version)})
        check(["pillow>=11, <13"], {"pillow": distribution("12.0")})
        check(["pillow>11,<=12"], {"pillow": distribution("12.0.0")})

    def test_unknown_range_syntax_is_explicit(self):
        for requirement in ("pillow~=11", "pillow>=11,!=12", "pillow>=11,", "pillow>=11,<13.*",
                            "pillow>>11", "pillow===12", "pillow>=11rc1,<13"):
            with self.subTest(requirement=requirement), self.assertRaisesRegex(RuntimeError, "依赖声明已变化"):
                check([requirement], {"pillow": distribution("12")})
        with self.assertRaisesRegex(RuntimeError, "缺少依赖或版本不符"):
            check(["pillow>=11,<13"], {"pillow": distribution("11rc1")})

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

    def test_httpx_socks_extra_checks_base_and_socksio(self):
        installed = {"httpx": distribution("0.28.1"), "socksio": distribution("1.0.0")}
        check(["httpx[socks]>=0.28"], installed)
        with self.assertRaisesRegex(RuntimeError, "socksio"):
            check(["httpx[socks]>=0.28"], {"httpx": installed["httpx"]})
        with self.assertRaisesRegex(RuntimeError, "socksio"):
            check(["httpx[socks]>=0.28"], {**installed, "socksio": distribution("2.0.0")})
        with self.assertRaisesRegex(RuntimeError, "httpx>=0.28"):
            check(["httpx[socks]>=0.28"], {**installed, "httpx": distribution("0.27.0")})

    def test_unknown_extras_are_not_silently_accepted(self):
        with self.assertRaisesRegex(RuntimeError, "依赖声明已变化"):
            check(["httpx[unknown]>=0.28"], {"httpx": distribution("0.28.1")})

    def test_missing_import_is_not_hidden(self):
        with self.assertRaisesRegex(RuntimeError, "无法找到模块"):
            check([], {}, module_available=False)


if __name__ == "__main__":
    unittest.main()
