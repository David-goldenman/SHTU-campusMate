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

export PATH="/opt/homebrew/bin:$PATH"

APP=campusMateLocal
# "dev" builds install side by side with the release build and show a DEV icon.
CONFIG=Release
FLAVOUR=""
case "${1:-release}" in
    dev) CONFIG=Debug; FLAVOUR="-dev" ;;
    release) ;;
    *) echo "usage: $0 [release|dev]" >&2; exit 2 ;;
esac
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

mkdir -p "$BUILD" "$BUILD/module-cache" "$BUILD/tmp"
export CLANG_MODULE_CACHE_PATH="$PWD/$BUILD/module-cache"
export TMPDIR="$PWD/$BUILD/tmp"
xcodegen generate --spec project.yml >/dev/null

# Build by target, not by scheme+destination: the scheme path needs the
# simulator device types, which are absent once the simulator runtime is removed.
# SYMROOT/OBJROOT keep every intermediate inside ipa/local/build-local.
xcodebuild -project "$APP.xcodeproj" -target "$APP" -configuration "$CONFIG" -sdk iphoneos \
    SYMROOT="$PWD/$BUILD/Products" OBJROOT="$PWD/$BUILD/Intermediates" \
    MODULE_CACHE_DIR="$PWD/$BUILD/module-cache" \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" \
    ASSETCATALOG_COMPILER_SKIP_APP_STORE_DEPLOYMENT=YES build

rm -rf "$BUILD/Payload"
mkdir -p "$BUILD/Payload"
ditto "$BUILD/Products/$CONFIG-iphoneos/$APP.app" "$BUILD/Payload/$APP.app"
rm -f "campusMate$FLAVOUR.ipa"
(cd "$BUILD" && zip -qry "../campusMate$FLAVOUR.ipa" Payload)
echo "Local prototype IPA: $(pwd)/campusMate$FLAVOUR.ipa"
