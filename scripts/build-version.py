#!/usr/bin/env python3
"""Print the custom version derived from the immutable Bazzite base lock."""
import argparse
import json
import re
from pathlib import Path


def build_version(lock_path, config_path):
    lock = json.loads(Path(lock_path).read_text())
    config = json.loads(Path(config_path).read_text())
    upstream = lock.get("container_base", {}).get("version")
    revision = config.get("custom_revision")
    variant = config.get("variant")
    if not isinstance(upstream, str) or not re.fullmatch(r"[0-9]+\.[0-9]{8}", upstream):
        raise ValueError("container_base.version must match 45.YYYYMMDD")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("custom_revision must be a positive integer")
    if variant != "polaris-sdl":
        raise ValueError("variant must be polaris-sdl for this image")
    return f"{upstream}.{revision}-{variant}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("image-lock.json"))
    parser.add_argument("--config", type=Path, default=Path("build-version.json"))
    args = parser.parse_args()
    print(build_version(args.lock, args.config))
