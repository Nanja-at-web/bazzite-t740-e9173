#!/usr/bin/env python3
"""Fail closed when an immutable release tag already exists in a registry."""
import json
import subprocess
import sys


def main(image, tag):
    try:
        result = subprocess.run(
            ["skopeo", "list-tags", f"docker://{image}"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        print("skopeo is required to verify the immutable version tag; "
              "refusing to publish", file=sys.stderr)
        return 2
    if result.returncode != 0:
        print("Unable to list registry tags; refusing to publish", file=sys.stderr)
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        return 2
    try:
        tags = json.loads(result.stdout)["Tags"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("Registry returned an invalid tag list; refusing to publish", file=sys.stderr)
        return 2
    if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
        print("Registry returned an invalid tag list; refusing to publish", file=sys.stderr)
        return 2
    if tag in tags:
        print(f"Immutable version tag already exists: {image}:{tag}", file=sys.stderr)
        return 1
    print(f"Immutable version tag is available: {image}:{tag}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} IMAGE TAG", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
