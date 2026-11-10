#!/usr/bin/env bash
# Build ipa/campusMate.ipa on macOS.
#
#   ./build_ipa.sh                 unsigned .ipa (works on a simulator/unsigned install tools)
#   CAMPUS_IOS_TEAM=XXXXXXXXXX ./build_ipa.sh
#                                  signed .ipa for a real device, using the Apple
#                                  developer team and automatic provisioning
#
# xcodegen (brew install xcodegen) turns project.yml into campusMate.xcodeproj.
set -euo pipefail
cd "$(dirname "$0")"

APP=campusMate
BUILD=build
ARCHIVE="$BUILD/$APP.xcarchive"

xcodebuild -version >/dev/null 2>&1 || {
    echo 'A full Xcode install is required, not just the command line tools:' >&2
    echo '  install Xcode from the App Store, then: sudo xcode-select -s /Applications/Xcode.app' >&2
    exit 1
}
command -v xcodegen >/dev/null || { echo 'xcodegen is required: brew install xcodegen' >&2; exit 1; }

export TMPDIR="$(pwd)/.tmp"
mkdir -p "$TMPDIR" "$BUILD"

xcodegen generate --spec project.yml

if [[ -n "${CAMPUS_IOS_TEAM:-}" ]]; then
    echo "Archiving for team $CAMPUS_IOS_TEAM."
    xcodebuild archive -project "$APP.xcodeproj" -scheme "$APP" -configuration Release \
        -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
        -allowProvisioningUpdates DEVELOPMENT_TEAM="$CAMPUS_IOS_TEAM" CODE_SIGN_STYLE=Automatic
    rm -rf "$BUILD/export"
    xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist ExportOptions.plist \
        -exportPath "$BUILD/export" -allowProvisioningUpdates
    cp "$BUILD/export/$APP.ipa" "$APP.ipa"
    echo "Signed IPA: $(pwd)/$APP.ipa"
    exit 0
fi

echo 'Archiving without code signing; install with a sideloading tool or sign it later.'
xcodebuild archive -project "$APP.xcodeproj" -scheme "$APP" -configuration Release \
    -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=""

rm -rf "$BUILD/Payload"
mkdir -p "$BUILD/Payload"
ditto "$ARCHIVE/Products/Applications/$APP.app" "$BUILD/Payload/$APP.app"
rm -f "$APP.ipa"
(cd "$BUILD" && zip -qry "../$APP.ipa" Payload)
echo "Unsigned IPA: $(pwd)/$APP.ipa"
