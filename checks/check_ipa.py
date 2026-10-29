"""The iOS shell stays thin: these files must agree with the desktop backend."""
import json
import plistlib
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from PIL import Image

from backend.core.config import VERSION

IPA = PROJECT / "ipa"
APP = IPA / "campusMate"
SOURCES = ("CampusMateApp.swift", "ContentView.swift", "CampusWebView.swift", "ServerSettings.swift", "SetupView.swift")
SIGNING = {".p12", ".cer", ".mobileprovision", ".ipa", ".xcarchive", ".provisionprofile"}


def read(name):
    return (APP / name).read_text(encoding="utf-8")


def check():
    spec = (IPA / "project.yml").read_text(encoding="utf-8")
    bundle = re.search(r"PRODUCT_BUNDLE_IDENTIFIER:\s*(\S+)", spec)
    assert bundle and re.fullmatch(r"[a-z][a-z0-9]*(\.[a-z0-9-]+)+", bundle.group(1)), "The bundle identifier must be reverse DNS."
    version = re.search(r'MARKETING_VERSION:\s*"([^"]+)"', spec)
    assert version and version.group(1) == VERSION, f"The shell version must track backend {VERSION}."
    for fragment in ('iOS: "16.0"', "INFOPLIST_FILE: campusMate/Info.plist", "GENERATE_INFOPLIST_FILE: NO",
                     "ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon", "excludes:", "SUPPORTS_MACCATALYST: NO"):
        assert fragment in spec, f"project.yml lost {fragment}"

    info = plistlib.loads((APP / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "$(PRODUCT_BUNDLE_IDENTIFIER)"
    assert info["CFBundleShortVersionString"] == "$(MARKETING_VERSION)" and info["CFBundleVersion"] == "$(CURRENT_PROJECT_VERSION)"
    assert info["CFBundleDisplayName"] == "campusMate" and info["LSRequiresIPhoneOS"] is True
    assert info["ITSAppUsesNonExemptEncryption"] is False
    transport = info["NSAppTransportSecurity"]
    assert transport["NSAllowsLocalNetworking"] is True, "Local HTTP needs the ATS local-networking exception."
    assert "NSAllowsArbitraryLoads" not in transport, "Only local HTTP may be relaxed."
    assert len(info["NSLocalNetworkUsageDescription"]) >= 8
    assert info["UILaunchScreen"]["UIColorName"] == "LaunchBackground"
    assert "UIInterfaceOrientationPortrait" in info["UISupportedInterfaceOrientations"]

    icons = json.loads((APP / "Assets.xcassets/AppIcon.appiconset/Contents.json").read_text(encoding="utf-8"))
    name = icons["images"][0]["filename"]
    assert icons["images"][0]["size"] == "1024x1024" and len(icons["images"]) == 1
    icon = Image.open(APP / "Assets.xcassets/AppIcon.appiconset" / name)
    assert icon.size == (1024, 1024) and icon.mode == "RGB", "App Store icons are 1024x1024 without an alpha channel."
    colors = json.loads((APP / "Assets.xcassets/LaunchBackground.colorset/Contents.json").read_text(encoding="utf-8"))
    components = colors["colors"][0]["color"]
    assert components["color-space"] == "srgb" and set(components["components"]) == {"red", "green", "blue", "alpha"}

    for source in SOURCES:
        assert (APP / source).is_file(), f"{source} is missing."
    settings = read("ServerSettings.swift")
    assert "static let defaultPort = 16666" in settings, "The shell must default to the desktop port."
    assert 'URLQueryItem(name: "pair"' in settings, "The first request must carry the pairing code."
    web = read("CampusWebView.swift")
    assert "runJavaScriptTextInputPanelWithPrompt" in web, "The password generator uses window.prompt."
    assert "UIActivityViewController" in web and "decisionHandler(.download)" in web, "Exports must reach the share sheet."
    assert "url.host == origin.host" in web and "UIApplication.shared.open(url)" in web, "Foreign links must leave the app."
    assert "NSURLErrorCancelled" in web, "Offline detection must ignore cancelled loads."
    setup = read("SetupView.swift")
    assert "8 位配对码" in setup and "run.cmd --share" in setup, "Setup must explain where the code comes from."
    assert "QQ" in setup, "The WeChat/QQ boundary is documented in the app."


    script = (IPA / "build_ipa.sh").read_bytes()
    assert b"\r" not in script, "Shell scripts keep LF endings."
    build = script.decode("utf-8")
    for fragment in ("set -euo pipefail", "xcodegen generate", "xcodebuild archive", "-exportArchive",
                     "CODE_SIGNING_ALLOWED=NO", "Payload", "$APP.ipa"):
        assert fragment in build, f"build_ipa.sh lost {fragment}"
    export = plistlib.loads((IPA / "ExportOptions.plist").read_bytes())
    assert export["signingStyle"] == "automatic" and export["method"] in {"development", "ad-hoc", "app-store"}
    assert export["compileBitcode"] is False

    readme = (IPA / "README.md").read_text(encoding="utf-8")
    assert len(readme) > 800 and "run.cmd --share" in readme and "配对码" in readme
    assert "暂不在手机端实现" in readme, "The WeChat/QQ boundary must stay documented."

    for path in IPA.rglob("*"):
        assert path.suffix.lower() not in SIGNING, f"Signing material and build output stay out of the repository: {path}"
        if path.is_file() and path.suffix.lower() in {".swift", ".yml", ".plist", ".sh", ".md", ".json", ".py"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in ("sk-", "BEGIN PRIVATE KEY", "api_key", "Bearer "):
                assert marker not in text, f"{path.relative_to(PROJECT)} must not contain secrets."

    workflow = (PROJECT / ".github" / "workflows" / "ios.yml").read_text(encoding="utf-8")
    assert "runs-on: macos" in workflow and "./build_ipa.sh" in workflow and "working-directory: ipa" in workflow
    assert re.search(r"uses: \S+@[0-9a-f]{40}", workflow), "Actions stay pinned to commit SHAs."
    print("ipa: shell sources, icon, plist, pairing defaults, build script and macOS workflow passed")


if __name__ == "__main__":
    check()
