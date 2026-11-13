#!/usr/bin/env bash
# Cross-compile pydantic-core for iOS (arm64, device) and assemble the wheel.
#
# This is the P1 spike: the backend needs FastAPI, which needs pydantic, which
# needs pydantic_core — the only Rust/native piece in that chain. Everything
# else (fastapi, starlette, anyio, httpx, pydantic) is pure Python.
#
# Prerequisites (all kept inside the repository, nothing installed system wide):
#   .codex/tools/bin/uv                 https://astral.sh/uv
#   .codex/rust/cargo/bin/rustup        RUSTUP_HOME/CARGO_HOME under .codex/rust
#   .codex/build-venv                   uv venv + maturin (only used for reference)
#   ipa/local/Python.xcframework        beeware/Python-Apple-support iOS archive
#
# Usage: ./build_pydantic_core.sh [version]
set -euo pipefail
cd "$(dirname "$0")/../../.."
REPO=$(pwd)
export RUSTUP_HOME="$REPO/.codex/rust/rustup"
export CARGO_HOME="$REPO/.codex/rust/cargo"
export PATH="$CARGO_HOME/bin:$PATH"

VERSION=${1:-2.50.1}
WORK="$REPO/.codex/build"
SRC="$WORK/pydantic_core-$VERSION"
TARGET="$REPO/.codex/cache/cargo-target/aarch64-apple-ios/release"
PREFIX="$REPO/.codex/ios-prefix"
WHEELS="$REPO/.codex/wheelhouse"

# pyo3 needs a Python "prefix" for the target: headers, the dylib, and the
# iOS-specific _sysconfigdata. Python-Apple-support ships them in two places.
FRAMEWORK="$REPO/ipa/local/Python.xcframework/ios-arm64"
rm -rf "$PREFIX"
mkdir -p "$PREFIX/lib/python3.13" "$PREFIX/include"
cp -L "$FRAMEWORK/lib/libpython3.13.dylib" "$PREFIX/lib/"
ln -sf lib/libpython3.13.dylib "$PREFIX/libpython3.13.dylib"
cp "$FRAMEWORK"/lib-arm64/python3.13/_sysconfigdata*.py "$PREFIX/lib/python3.13/"
cp -R "$FRAMEWORK"/include/python3.13 "$PREFIX/include/"

if [ ! -d "$SRC" ]; then
    mkdir -p "$WORK"
    curl -sSL "https://files.pythonhosted.org/packages/source/p/pydantic-core/pydantic_core-$VERSION.tar.gz" |
        tar xz -C "$WORK" || {
        echo "Download the sdist for $VERSION manually into $WORK" >&2
        exit 1
    }
fi

export SDKROOT=$(xcrun --sdk iphoneos --show-sdk-path)
export IPHONEOS_DEPLOYMENT_TARGET=${IPHONEOS_DEPLOYMENT_TARGET:-16.0}
export PYO3_CROSS=1
export PYO3_CROSS_PYTHON_VERSION=3.13
export PYO3_CROSS_LIB_DIR="$PREFIX"
export CARGO_TARGET_DIR="$REPO/.codex/cache/cargo-target"

cd "$SRC"
cargo build --release --target aarch64-apple-ios

test -f "$TARGET/lib_pydantic_core.dylib"

mkdir -p "$WHEELS"
"$REPO/.codex/build-venv/bin/python" - "$SRC" "$TARGET/lib_pydantic_core.dylib" "$WHEELS" "$VERSION" <<'PY'
import base64, hashlib, sys, zipfile
from pathlib import Path

src, so, out_dir, version = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
name = f"pydantic_core-{version}-cp313-cp313-ios_16_0_arm64_iphoneos.whl"
records = []

def add(zf, entry, data):
    zf.writestr(entry, data)
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    records.append(f"{entry},sha256={digest},{len(data)}")

with zipfile.ZipFile(out_dir / name, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted((src / "python/pydantic_core").rglob("*")):
        if path.is_file():
            add(zf, path.relative_to(src / "python").as_posix(), path.read_bytes())
    add(zf, "pydantic_core/_pydantic_core.cpython-313-iphoneos.so", so.read_bytes())
    add(zf, f"pydantic_core-{version}.dist-info/METADATA", (src / "PKG-INFO").read_bytes())
    wheel = ("Wheel-Version: 1.0\nGenerator: campusmate-ios-build\n"
             "Root-Is-Purelib: false\nTag: cp313-cp313-ios_16_0_arm64_iphoneos\n")
    add(zf, f"pydantic_core-{version}.dist-info/WHEEL", wheel.encode())
    records.append(f"pydantic_core-{version}.dist-info/RECORD,,")
    zf.writestr(f"pydantic_core-{version}.dist-info/RECORD", "\n".join(records) + "\n")
print(out_dir / name)
PY
