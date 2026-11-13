"""Zip a staged tree into a wheel with a valid RECORD.

Usage: assemble_wheel.py <stage-dir> <dist-name> <version> <out-dir> [tag]

The stage directory already contains the package tree plus
``<dist>-<version>.dist-info/METADATA``; WHEEL and RECORD are generated here.
"""
import base64
import hashlib
import sys
import zipfile
from pathlib import Path

stage, dist, version, out_dir = (Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4]))
tag = sys.argv[5] if len(sys.argv) > 5 else "cp313-cp313-ios_16_0_arm64_iphoneos"
info = f"{dist}-{version}.dist-info"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / f"{dist}-{version}-{tag}.whl"

records = []
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(stage.rglob("*")):
        if not path.is_file() or path.parts[-2:] == (info, "RECORD"):
            continue
        name = path.relative_to(stage).as_posix()
        data = path.read_bytes()
        zf.writestr(name, data)
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        records.append(f"{name},sha256={digest},{len(data)}")
    wheel = f"Wheel-Version: 1.0\nGenerator: campusmate-ios-build\nRoot-Is-Purelib: false\nTag: {tag}\n"
    zf.writestr(f"{info}/WHEEL", wheel.encode())
    digest = base64.urlsafe_b64encode(hashlib.sha256(wheel.encode()).digest()).rstrip(b"=").decode()
    records.append(f"{info}/WHEEL,sha256={digest},{len(wheel)}")
    records.append(f"{info}/RECORD,,")
    zf.writestr(f"{info}/RECORD", "\n".join(records) + "\n")

print(out)
