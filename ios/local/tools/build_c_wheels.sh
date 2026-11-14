#!/usr/bin/env bash
# Cross-compile the setuptools-based native wheels for iOS (arm64 device) and
# assemble them into .codex/wheelhouse/:
#
#   zstandard 0.25.0  pure C extension (vendored zstd, no external libs)
#   pillow 12.3.0     C extension, zlib only; JPEG/TIFF/WebP/freetype disabled
#
# pydantic-core uses cargo/pyo3, see build_pydantic_core.sh.
#
# Usage: ./build_c_wheels.sh [zstandard|pillow|all]
set -euo pipefail
cd "$(dirname "$0")/../../.."
REPO=$(pwd)
WORK="$REPO/.codex/build"
WHEELS="$REPO/.codex/wheelhouse"
PY="$REPO/.codex/build-venv/bin/python"
SDL="${IPHONEOS_DEPLOYMENT_TARGET:-16.0}"

export SDKROOT=$(xcrun --sdk iphoneos --show-sdk-path)
export CC="$(xcrun -f clang) -target arm64-apple-ios$SDL -isysroot $SDKROOT"
# This machine's Python is a macOS build, so distutils also injects the macOS
# SDK lib dir; put the iOS one first or -lz resolves to the macOS library.
export LDSHARED="$(xcrun -f clang) -bundle -undefined dynamic_lookup -target arm64-apple-ios$SDL -isysroot $SDKROOT -L$SDKROOT/usr/lib"
export CFLAGS="-O2 -fPIC"
mkdir -p "$WHEELS"

fetch() {  # $1 url, $2 dest dir
    [ -d "$WORK/$2" ] && return
    mkdir -p "$WORK"
    curl -sSL "$1" | tar xz -C "$WORK"
}

build_zstandard() {
    fetch "https://files.pythonhosted.org/packages/fd/aa/3e0508d5a5dd96529cdc5a97011299056e14c6505b678fd58938792794b1/zstandard-0.25.0.tar.gz" zstandard-0.25.0
    local src="$WORK/zstandard-0.25.0" stage="$WORK/stage-zstandard"
    ( cd "$src" && "$PY" setup.py build_ext --inplace >/dev/null )
    rm -rf "$stage"; mkdir -p "$stage/zstandard" "$stage/zstandard-0.25.0.dist-info"
    cp "$src"/zstandard/*.py "$src"/zstandard/*.pyi "$src"/zstandard/py.typed "$stage/zstandard/"
    cp "$src"/zstandard/backend_c.cpython-313-darwin.so \
       "$stage/zstandard/backend_c.cpython-313-iphoneos.so"
    cp "$src/PKG-INFO" "$stage/zstandard-0.25.0.dist-info/METADATA"
    "$PY" "$REPO/ios/local/tools/assemble_wheel.py" "$stage" zstandard 0.25.0 "$WHEELS"
}

build_pillow() {
    fetch "https://mirrors.nju.edu.cn/pypi/web/packages/1c/3d/bb7fca845737cf9d7dbde16ed1843984665ff2e0a518f5db43e77ec540b9/pillow-12.3.0.tar.gz" pillow-12.3.0
    local src="$WORK/pillow-12.3.0" stage="$WORK/stage-pillow"
    # build_clib is required: Pillow 12 links _imaging against libpil_imaging_mode.a
    ( cd "$src" && "$PY" setup.py build_clib build_ext --disable-jpeg --disable-tiff \
        --disable-freetype --disable-lcms --disable-webp --disable-xcb \
        --disable-jpeg2000 --disable-raqm >/dev/null )
    rm -rf "$stage"; mkdir -p "$stage/PIL" "$stage/pillow-12.3.0.dist-info"
    cp "$src"/src/PIL/*.py "$stage/PIL/"
    for so in "$src"/build/lib.macosx-11.0-arm64-cpython-313/PIL/*.so; do
        cp "$so" "$stage/PIL/$(basename "$so" .cpython-313-darwin.so).cpython-313-iphoneos.so"
    done
    cp "$src/PKG-INFO" "$stage/pillow-12.3.0.dist-info/METADATA"
    "$PY" "$REPO/ios/local/tools/assemble_wheel.py" "$stage" pillow 12.3.0 "$WHEELS"
}

case "${1:-all}" in
    zstandard) build_zstandard ;;
    pillow) build_pillow ;;
    all) build_zstandard; build_pillow ;;
    *) echo "usage: $0 [zstandard|pillow|all]" >&2; exit 2 ;;
esac
