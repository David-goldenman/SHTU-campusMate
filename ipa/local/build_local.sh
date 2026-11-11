#!/usr/bin/env bash
# Build the self-contained iOS prototype: embedded CPython + local HTTP server
# + the repository web/ workspace, packaged as campusMateLocal.ipa.
#
#   ./build_local.sh
#
# Requires Xcode 15+, xcodegen, and ipa/local/Python.xcframework
# (beeware/Python-Apple-support, iOS archive).
set -euo pipefail
cd "$(dirname "$0")"

APP=campusMateLocal
BUILD=build-local
ARCHIVE="$BUILD/$APP.xcarchive"

xcodebuild -version >/dev/null 2>&1 || {
    echo 'A full Xcode install is required; see ipa/README.md.' >&2
    exit 1
}
command -v xcodegen >/dev/null || { echo 'xcodegen is required: brew install xcodegen' >&2; exit 1; }
[ -d Python.xcframework ] || {
    echo 'Python.xcframework is missing: download the iOS archive from beeware/Python-Apple-support.' >&2
    exit 1
}

mkdir -p "$BUILD"
xcodegen generate --spec project.yml >/dev/null

xcodebuild archive -project "$APP.xcodeproj" -scheme "$APP" -configuration Release \
    -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" -derivedDataPath "$BUILD/DerivedData" \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" \
    ASSETCATALOG_COMPILER_SKIP_APP_STORE_DEPLOYMENT=YES

rm -rf "$BUILD/Payload"
mkdir -p "$BUILD/Payload"
ditto "$ARCHIVE/Products/Applications/$APP.app" "$BUILD/Payload/$APP.app"
rm -f "../$APP.ipa"
(cd "$BUILD" && zip -qry "../$APP.ipa" Payload)
echo "Local prototype IPA: $(pwd)/$APP.ipa"
