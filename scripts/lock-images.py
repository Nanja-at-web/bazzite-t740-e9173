#!/usr/bin/env python3
"""Explicitly refresh immutable GHCR inputs; never starts a build."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

SOURCES = {
    "container_base": "ghcr.io/ublue-os/bazzite-deck:stable",
    "installer_base": "ghcr.io/ublue-os/bazzite:stable",
    "install_payload": "ghcr.io/nanja-at-web/bazzite-t740-e9173:latest",
}
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


def resolve(source):
    repository, tag = source.removeprefix("ghcr.io/").rsplit(":", 1)
    with urllib.request.urlopen(
        "https://ghcr.io/token?service=ghcr.io&scope=repository:" + repository + ":pull",
        timeout=40,
    ) as response:
        token = json.load(response)["token"]
    headers = {"Authorization": "Bearer " + token, "Accept": ACCEPT}

    def manifest(reference):
        request = urllib.request.Request(
            f"https://ghcr.io/v2/{repository}/manifests/{reference}", headers=headers
        )
        with urllib.request.urlopen(request, timeout=40) as response:
            raw = response.read()
        return json.loads(raw), "sha256:" + hashlib.sha256(raw).hexdigest()

    data, digest = manifest(tag)
    if "manifests" in data:
        selected = next(item for item in data["manifests"]
                        if item.get("platform", {}).get("os") == "linux"
                        and item["platform"].get("architecture") == "amd64")
        _, digest = manifest(selected["digest"])
        if digest != selected["digest"]:
            raise ValueError("Manifest digest mismatch")
    return {"source": source, "image": f"ghcr.io/{repository}@{digest}"}


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        resolved = dict(zip(SOURCES, pool.map(resolve, SOURCES.values())))
    result = {"schema_version": 1, "platform": "linux/amd64",
              "resolved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              **resolved}
    path = Path(__file__).resolve().parents[1] / "image-lock.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.read_text(), end="")
