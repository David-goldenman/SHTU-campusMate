#!/usr/bin/env bash
# Cross-compile cryptography for iOS (arm64 device) and assemble the wheel.
#
# cryptography is a Rust extension (pyo3, abi3) statically linked against
# OpenSSL, so this script also builds OpenSSL with Apple's ios64-cross target.
#
# Usage: ./build_cryptography.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."
REPO=$(pwd)
WORK="$REPO/.codex/build"
WHEELS="$REPO/.codex/wheelhouse"
PY="$REPO/.codex/build-venv/bin/python"
VERSION=50.0.2
OPENSSL=4.0.3
SDL="${IPHONEOS_DEPLOYMENT_TARGET:-16.0}"

export RUSTUP_HOME="$REPO/.codex/rust/rustup"
export CARGO_HOME="$REPO/.codex/rust/cargo"
export PATH="$CARGO_HOME/bin:$PATH"
export SDKROOT=$(xcrun --sdk iphoneos --show-sdk-path)
export IPHONEOS_DEPLOYMENT_TARGET="$SDL"

# --- OpenSSL for iOS -------------------------------------------------------
if [ ! -f "$WORK/openssl-ios/lib/libcrypto.a" ]; then
    [ -d "$WORK/openssl-$OPENSSL" ] || {
        mkdir -p "$WORK"
        curl -sSL "https://github.com/openssl/openssl/releases/download/openssl-$OPENSSL/openssl-$OPENSSL.tar.gz" |
            tar xz -C "$WORK"
    }
    (
        cd "$WORK/openssl-$OPENSSL"
        export CROSS_TOP=$(xcode-select -p)/Platforms/iPhoneOS.platform/Developer
        export CROSS_SDK=iPhoneOS18.5.sdk
        ./Configure ios64-cross no-shared no-tests no-docs --prefix="$WORK/openssl-ios" >/dev/null
        make -j6 >/dev/null
        make install_sw >/dev/null
    )
fi

# --- cryptography ----------------------------------------------------------
[ -d "$WORK/cryptography-$VERSION" ] || {
    mkdir -p "$WORK"
    curl -sSL "https://mirrors.nju.edu.cn/pypi/web/packages/9d/af/182eb91b0df3fe75c4d9f26fe70684569566745f6ba7e5c9c73a862c5252/cryptography-$VERSION.tar.gz" |
        tar xz -C "$WORK"
}

export PYO3_CROSS=1
export PYO3_CROSS_PYTHON_VERSION=3.13
export PYO3_CROSS_LIB_DIR="$REPO/.codex/ios-prefix"
export PYO3_PYTHON="$PY"
export OPENSSL_DIR="$WORK/openssl-ios"
export OPENSSL_STATIC=1
export CARGO_TARGET_DIR="$REPO/.codex/cache/crypto-target"
# rustc asks for the macOS compiler runtime (-lclang_rt.osx); the iOS linker
# rejects it, so filter it out through a wrapper.
export CARGO_TARGET_AARCH64_APPLE_IOS_LINKER="$REPO/.codex/tools/ios-linker.sh"

( cd "$WORK/cryptography-$VERSION" && env "CFLAGS_aarch64-apple-ios=-I$REPO/.codex/ios-prefix/include/python3.13" \
    cargo build --release --target aarch64-apple-ios -p cryptography-rust >/dev/null )

STAGE="$WORK/stage-cryptography"
rm -rf "$STAGE"
mkdir -p "$STAGE/cryptography-50.0.2.dist-info" "$STAGE/cryptography/hazmat/bindings"
cp -R "$WORK/cryptography-$VERSION/src/cryptography" "$STAGE/"
cp "$CARGO_TARGET_DIR/aarch64-apple-ios/release/libcryptography_rust.dylib" \
   "$STAGE/cryptography/hazmat/bindings/_rust.abi3.so"
cp "$WORK/cryptography-$VERSION/PKG-INFO" "$STAGE/cryptography-$VERSION.dist-info/METADATA"
"$PY" "$REPO/ipa/local/tools/assemble_wheel.py" "$STAGE" cryptography "$VERSION" "$WHEELS" \
    cp39-abi3-ios_16_0_arm64_iphoneos
