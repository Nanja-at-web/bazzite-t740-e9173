#!/usr/bin/env python3
"""Write durable build provenance inside an image, independent of OCI rechunking."""
import argparse
import json
import re
import shlex
from pathlib import Path

BUILD_ID_PATTERN = re.compile(
    r"(?P<upstream_version>[0-9]+\.[0-9]{8})\."
    r"(?P<custom_revision>[1-9][0-9]*)-"
    r"(?P<variant>polaris-sdl)"
)


def parse_build_id(value):
    match = BUILD_ID_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("Build ID must match 45.YYYYMMDD.N-polaris-sdl")
    result = match.groupdict()
    result["custom_revision"] = int(result["custom_revision"])
    return result


def bazzite_base_version(os_release):
    pattern = re.compile(r"(?<![0-9])([0-9]+\.[0-9]{8})(?:\.[0-9]+)?(?![0-9])")
    for key in ("OSTREE_VERSION", "BUILD_ID", "VERSION"):
        match = pattern.search(os_release.get(key, ""))
        if match:
            return match.group(1)
    raise ValueError("Cannot determine Bazzite base version from os-release")


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
    version = parse_build_id(build_id)
    os_release = read_os_release(root / "usr/lib/os-release")
    base_version = bazzite_base_version(os_release)
    if version["upstream_version"] != base_version:
        raise ValueError(
            f"Build version {version['upstream_version']} does not match base OS {base_version}"
        )
    upstream_file = root / "usr/share/ublue-os/image-info.json"
    upstream = json.loads(upstream_file.read_text()) if upstream_file.exists() else None
    data = {"schema_version": 2, "role": role, "build_id": build_id,
            "version": version,
            "display_name": (
                f"Bazzite {version['upstream_version']}."
                f"{version['custom_revision']} (Polaris SDL)"
            ),
            "target_hardware": {
                "system": "HP t740 Thin Client",
                "discrete_gpu": "AMD Radeon E9173",
                "graphics_family": "AMD Polaris (Lexa PRO)",
            },
            "source_revision": revision, "created": created,
            "base_image": base_image, "install_payload": payload or None,
            "os": {key: os_release.get(key) for key in
                   ("NAME", "VERSION", "VERSION_ID", "BUILD_ID",
                    "OSTREE_VERSION", "PRETTY_NAME")},
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
