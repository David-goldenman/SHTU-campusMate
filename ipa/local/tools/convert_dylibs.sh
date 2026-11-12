#!/usr/bin/env bash
# Turn every bundled extension module into a signed-friendly framework.
#
# iOS refuses to dlopen loose .so files that are not covered by the app's code
# signature. BeeWare's CPython build supports this by convention: a
# "<module>.so.fwork" file next to the original path points at
# Frameworks/<module>.framework/<module>, and the framework carries a
# "<module>.origin" file back to the placeholder. importlib follows both.
#
# Usage: convert_dylibs.sh <app-bundle> <python-xcframework>
# Runs as an Xcode build phase, so the frameworks exist before signing.
set -euo pipefail
BUNDLE="$1"
FRAMEWORK_ROOT="$2"
TEMPLATE="$FRAMEWORK_ROOT/build/iOS-dylib-Info-template.plist"
IDENTITY="${EXPANDED_CODE_SIGN_IDENTITY:-}"

CONVERTED=0
convert_one() {
    local so="$1"
    local name
    name=$(basename "$so" | cut -d. -f1)
    local relative="${so#"$BUNDLE"/}"
    local framework="Frameworks/$name.framework"

    if [ -e "$BUNDLE/$framework/$name" ]; then
        return
    fi
    mkdir -p "$BUNDLE/$framework"
    cp "$TEMPLATE" "$BUNDLE/$framework/Info.plist"
    plutil -replace CFBundleExecutable -string "$name" "$BUNDLE/$framework/Info.plist"
    plutil -replace CFBundleIdentifier -string "${PRODUCT_BUNDLE_IDENTIFIER:-edu.shanghaitech.campusmate.local}.$name" \
        "$BUNDLE/$framework/Info.plist"

    mv "$so" "$BUNDLE/$framework/$name"
    printf '%s/%s' "$framework" "$name" > "${so%.so}.fwork"
    printf '%s.fwork' "${relative%.so}" > "$BUNDLE/$framework/$name.origin"
    CONVERTED=$((CONVERTED + 1))
}

while IFS= read -r so; do
    convert_one "$so"
done < <(find "$BUNDLE/python" -name "*.so" -type f)

if [ -n "$IDENTITY" ]; then
    for framework in "$BUNDLE"/Frameworks/*.framework; do
        [ -d "$framework" ] || continue
        /usr/bin/codesign --force --sign "$IDENTITY" ${OTHER_CODE_SIGN_FLAGS:-} \
            --timestamp=none --preserve-metadata=identifier,entitlements,flags \
            --generate-entitlement-der "$framework"
    done
fi

echo "Converted $CONVERTED extension modules into frameworks."
