#!/usr/bin/env python3
"""Print a deterministic build timestamp derived from a Git commit."""
import argparse
import datetime
from pathlib import Path
import subprocess


def commit_epoch(repo, revision):
    result = subprocess.run(
        ["git", "-C", str(repo), "show", "-s", "--format=%ct", revision],
        check=True, capture_output=True, text=True,
    )
    value = result.stdout.strip()
    if not value.isdigit():
        raise ValueError("Git commit timestamp is not a non-negative integer")
    return int(value)


def render(epoch, output_format):
    if output_format == "epoch":
        return str(epoch)
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--format", choices=("epoch", "rfc3339"), required=True)
    args = parser.parse_args()
    print(render(commit_epoch(args.repo, args.revision), args.format))
