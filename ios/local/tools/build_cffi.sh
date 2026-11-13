#!/usr/bin/env bash
# Cross-compile cffi's _cffi_backend for iOS (arm64 device).
#
# cryptography's Rust module exposes a cffi-based OpenSSL binding, so importing
# cryptography pulls in _cffi_backend at runtime. cffi needs libffi, which iOS
# does not ship, so this script builds libffi first and links it statically.
#
# Usage: ./build_cffi.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."
REPO=$(pwd)
WORK="$REPO/.codex/build"
WHEELS="$REPO/.codex/wheelhouse"
PY="$REPO/.codex/build-venv/bin/python"
CFFI=2.1.1
LIBFFI=3.8.0
SDL="${IPHONEOS_DEPLOYMENT_TARGET:-16.0}"

export SDKROOT=$(xcrun --sdk iphoneos --show-sdk-path)
export CC="$(xcrun -f clang) -target arm64-apple-ios$SDL -isysroot $SDKROOT"
export LDSHARED="$(xcrun -f clang) -bundle -undefined dynamic_lookup -target arm64-apple-ios$SDL -isysroot $SDKROOT -L$SDKROOT/usr/lib"
export CFLAGS="-O2 -fPIC"
mkdir -p "$WORK" "$WHEELS"

# --- libffi ----------------------------------------------------------------
if [ ! -f "$WORK/libffi-ios/lib/libffi.a" ]; then
    [ -d "$WORK/libffi-$LIBFFI" ] || {
        curl -sSL "https://github.com/libffi/libffi/releases/download/v$LIBFFI/libffi-$LIBFFI.tar.gz" |
            tar xz -C "$WORK"
    }
    (
        cd "$WORK/libffi-$LIBFFI"
        CFLAGS="$CFLAGS -mios-version-min=$SDL" LDFLAGS="-arch arm64 -isysroot $SDKROOT" \
            ./configure --host=aarch64-apple-darwin --prefix="$WORK/libffi-ios" \
            --disable-shared --enable-static >/dev/null
        make -j6 >/dev/null
        make install >/dev/null
    )
fi

# --- cffi ------------------------------------------------------------------
[ -d "$WORK/cffi-$CFFI" ] || {
    curl -sSL "https://mirrors.nju.edu.cn/pypi/web/packages/9e/ef/008a1939e372c06329a3fce4279c02f328488f3526744906eeec3da7ad5f/cffi-$CFFI.tar.gz" |
        tar xz -C "$WORK"
}
(
    cd "$WORK/cffi-$CFFI"
    CFLAGS="$CFLAGS -I$WORK/libffi-ios/include" LDFLAGS="-L$WORK/libffi-ios/lib" \
        "$PY" setup.py build_ext --inplace >/dev/null
)

STAGE="$WORK/stage-cffi"
rm -rf "$STAGE"
mkdir -p "$STAGE/cffi-$CFFI.dist-info"
cp -R "$WORK/cffi-$CFFI/src/cffi" "$STAGE/"
cp "$WORK/cffi-$CFFI/build/lib.macosx-11.0-arm64-cpython-313/_cffi_backend.cpython-313-darwin.so" \
   "$STAGE/_cffi_backend.cpython-313-iphoneos.so"
cp "$WORK/cffi-$CFFI/PKG-INFO" "$STAGE/cffi-$CFFI.dist-info/METADATA"
"$PY" "$REPO/ios/local/tools/assemble_wheel.py" "$STAGE" cffi "$CFFI" "$WHEELS"
