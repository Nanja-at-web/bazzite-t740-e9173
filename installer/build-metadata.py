#!/usr/bin/env python3
"""Write durable build provenance inside an image, independent of OCI rechunking."""
import argparse
import json
import re
import shlex
from pathlib import Path


def read_os_release(path):
    values = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            tokens = shlex.split(value)
            values[key] = tokens[0] if tokens else ""
    return values


def pinned(value):
    if not re.fullmatch(r"ghcr\.io/[a-z0-9_./-]+@sha256:[0-9a-f]{64}", value):
        raise ValueError("A digest-pinned GHCR reference is required: " + value)
    return value


def write_metadata(root, role, build_id, revision, created, base_image, payload=""):
    pinned(base_image)
    if role == "installer":
        pinned(payload)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("A full source commit SHA is required")
    if not build_id or not created:
        raise ValueError("Build ID and creation time are required")
    os_release = read_os_release(root / "usr/lib/os-release")
    upstream_file = root / "usr/share/ublue-os/image-info.json"
    upstream = json.loads(upstream_file.read_text()) if upstream_file.exists() else None
    data = {"schema_version": 1, "role": role, "build_id": build_id,
            "source_revision": revision, "created": created,
            "base_image": base_image, "install_payload": payload or None,
            "os": {key: os_release.get(key) for key in
                   ("NAME", "VERSION_ID", "BUILD_ID", "PRETTY_NAME")},
            "upstream_image_info": upstream}
    destination = root / "usr/share/t740/build-info.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2) + "\n")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--role", choices=("system", "installer"), required=True)
    for name in ("build-id", "revision", "created", "base-image"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--payload", default="")
    args = parser.parse_args()
    write_metadata(args.root, args.role, args.build_id, args.revision,
                   args.created, args.base_image, args.payload)
