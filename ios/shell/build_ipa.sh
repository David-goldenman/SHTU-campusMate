#!/usr/bin/env bash
# Build ipa/campusMate.ipa on macOS.
#
#   ./build_ipa.sh                 unsigned .ipa (works on a simulator/unsigned install tools)
#   CAMPUS_IOS_TEAM=XXXXXXXXXX ./build_ipa.sh
#   CAMPUS_VARIANT=web CAMPUS_VERSION=1.0.0 ./build_ipa.sh
#                                  web-shell variant (bundle id +.web, "web"
#                                  badge icon, output ios/ipa/campusMate-web.ipa)
#                                  signed .ipa for a real device, using the Apple
#                                  developer team and automatic provisioning
#
# xcodegen (brew install xcodegen) turns project.yml into campusMate.xcodeproj.
set -euo pipefail
cd "$(dirname "$0")"

APP=campusMate
BUILD=build
VARIANT="${CAMPUS_VARIANT:-}"
VERSION="${CAMPUS_VERSION:-}"
# The web variant shares the code but is a separate app: its own bundle id,
# display name, "web" badge icon and output file.
if [[ "$VARIANT" == "web" ]]; then
    BUNDLE_ID="edu.shanghaitech.campusmate.web"
    DISPLAY_NAME="campusMate web"
    ICON_VARIANT="web"
    OUTPUT_NAME="campusMate-web"
else
    BUNDLE_ID="edu.shanghaitech.campusmate"
    DISPLAY_NAME="campusMate"
    ICON_VARIANT="release"
    OUTPUT_NAME="campusMate"
fi
OUTPUT="$(cd .. && pwd)/ipa/$OUTPUT_NAME.ipa"
EXTRA_SETTINGS=()
[[ -n "$VERSION" ]] && EXTRA_SETTINGS+=(MARKETING_VERSION="$VERSION")
EXTRA_SETTINGS+=(PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" CAMPUS_DISPLAY_NAME="$DISPLAY_NAME")
ARCHIVE="$BUILD/$APP.xcarchive"
DERIVED="$BUILD/DerivedData"

xcodebuild -version >/dev/null 2>&1 || {
    echo 'A full Xcode install is required, not just the command line tools:' >&2
    echo '  install Xcode from the App Store, then: sudo xcode-select -s /Applications/Xcode.app' >&2
    exit 1
}
command -v xcodegen >/dev/null || { echo 'xcodegen is required: brew install xcodegen' >&2; exit 1; }

export TMPDIR="$(pwd)/.tmp"
mkdir -p "$TMPDIR" "$BUILD"

# Copy the variant's icons into the target; the catalog is deliberately not
# used because actool needs a simulator runtime.
rm -rf campusMate/Icons
mkdir -p campusMate/Icons
cp tools/icons/"$ICON_VARIANT"/*.png campusMate/Icons/
xcodegen generate --spec project.yml

if [[ -n "${CAMPUS_IOS_TEAM:-}" ]]; then
    echo "Archiving for team $CAMPUS_IOS_TEAM."
    xcodebuild archive -project "$APP.xcodeproj" -scheme "$APP" -configuration Release \
        -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" -derivedDataPath "$DERIVED" \
        -allowProvisioningUpdates DEVELOPMENT_TEAM="$CAMPUS_IOS_TEAM" CODE_SIGN_STYLE=Automatic \
        "${EXTRA_SETTINGS[@]}"
    rm -rf "$BUILD/export"
    xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist ExportOptions.plist \
        -exportPath "$BUILD/export" -allowProvisioningUpdates
    mkdir -p "$(dirname "$OUTPUT")"
    cp "$BUILD/export/$APP.ipa" "$OUTPUT"
    echo "Signed IPA: $(pwd)/$OUTPUT"
    exit 0
fi

echo 'Building without code signing; install with a sideloading tool or sign it later.'
# Build by target, not by scheme+destination: destination resolution needs the
# iOS platform runtime, which is absent on machines that removed the simulator.
# App Store thinning also runs actool inside a simulator, so skip it.
mkdir -p "$BUILD/module-cache" "$BUILD/tmp"
CLANG_MODULE_CACHE_PATH="$PWD/$BUILD/module-cache" TMPDIR="$PWD/$BUILD/tmp" \
xcodebuild -project "$APP.xcodeproj" -target "$APP" -configuration Release -sdk iphoneos \
    SYMROOT="$PWD/$BUILD/Products" OBJROOT="$PWD/$BUILD/Intermediates" \
    MODULE_CACHE_DIR="$PWD/$BUILD/module-cache" \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" \
    ASSETCATALOG_COMPILER_SKIP_APP_STORE_DEPLOYMENT=YES \
    "${EXTRA_SETTINGS[@]}" build

rm -rf "$BUILD/Payload"
mkdir -p "$BUILD/Payload"
ditto "$BUILD/Products/Release-iphoneos/$APP.app" "$BUILD/Payload/$APP.app"
mkdir -p "$(dirname "$OUTPUT")"
rm -f "$OUTPUT"
(cd "$BUILD" && zip -qry "$OUTPUT" Payload)
echo "Unsigned IPA: $OUTPUT"
