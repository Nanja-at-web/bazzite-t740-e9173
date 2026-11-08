# Build provenance and diagnostics (development)

These changes are prepared on a development branch. No ISO is built by pushing
this branch, and the installed hardware-validated build #4 is unaffected.

## Version syntax and independent identifiers

- OS version: actual `/usr/lib/os-release` fields, for example `VERSION_ID=45`.
- Upstream build: the locked Bazzite image version, currently `45.20261105`.
- Custom build: `<Bazzite version>.<custom revision>-polaris-sdl`, currently
  `45.20261105.2-polaris-sdl`.
- Image digest: immutable registry manifest reference from `image-lock.json`.

The human-readable form is `Bazzite 45.20261105.2 (Polaris SDL)`. The hardware
target stays in the repository, container and ISO names, not in the version.
The source commit remains a separate provenance field. Local container builds
from a dirty Git checkout are rejected rather than creating a second version
syntax. `build-version.json` controls the custom revision and variant;
`scripts/build-version.py` combines it with the locked upstream version.

`/usr/share/t740/build-info.json` lives in the image filesystem, so its provenance
survives rootfs-based OCI rechunking even if that operation drops OCI labels.
`t740-build-info` prints it; `t740-build-info --json` returns the full record.
An installed system reports its own OS and base. The live desktop separately
shows LIVE OS, ISO BUILD, PAYLOAD OS and PAYLOAD BUILD. Legacy payloads without
custom metadata retain their real os-release, inspected image ID and creation
date; no OS version is guessed from the live installer.

## Locked inputs

`image-lock.json` pins the AMD64 manifests of:

1. the Bazzite Deck base used by `just build`;
2. the desktop base used for the live installer;
3. the exact custom image installed by the ISO.

Refresh explicitly with `python3 scripts/lock-images.py`, review the diff and
commit it. This only queries registry metadata; it does not build anything.
The initial lock is a development snapshot, **not** a recovered build #4 lock.
Each resolved entry also records its OCI version label. The currently locked
payload remains the published revision `45.20261105.1-polaris-sdl` until the
new revision is built, verified and pinned by digest.

Building a new system container does not automatically change the pinned ISO
payload. After validating the published container, update `install_payload` to
its exact digest before requesting a new ISO. The installer uses this reference
both for its local OSTree payload and for the installed bootc origin, avoiding
an implicit switch to a newer `latest` during installation. Consequently,
automatic system updates do not advance beyond that pinned origin. Moving to a
new validated digest requires an explicit bootc switch/update of the origin.

The ISO workflow refuses to build unless the locked payload has a valid custom
version matching the version derived from the locked Bazzite base. Therefore
the present revision-1 payload lock intentionally cannot produce a revision-2
ISO. After a validated container is published and the lock is refreshed, the
ISO name will be
`bazzite-t740-e9173-45.20261105.2-polaris-sdl-amd64.iso`.

## Reproducible container release controls

The container creation time and `SOURCE_DATE_EPOCH` are derived from the Git
commit timestamp, not the wall clock of the GitHub runner. Rebuilding the same
commit with the same locked inputs therefore supplies the same timestamp to
Podman and the image build script. This removes one known source of needless
digest changes; complete byte-for-byte reproducibility still depends on the
base image and the behavior of all build tools.

Before any container build starts, the workflow queries GHCR and fails closed
if the version tag already exists. A release tag such as
`45.20261105.2-polaris-sdl` is therefore immutable and cannot silently be moved
to another digest. Mutable convenience aliases are only published together
with a previously unused version tag.

The container workflow has no scheduled trigger. It runs for pull requests,
pushes to `main`, or explicit manual dispatch. The ISO workflow remains
manual-only and is not started by a container build.

The lock does not make an ISO byte-for-byte reproducible: installer DNF repos,
Flatpak remotes, timestamps and build tools can still change. Package/tool locks
and an automated VM installation test are future work.

ISO artifacts additionally include `build-provenance/`, with the input lock,
installer metadata and inspected payload metadata. The image's own config ID
cannot be embedded inside itself (that would change the ID); it is recorded in
the installer's payload inspection or obtained from `bootc status` at runtime.

## Diagnostics

Run `t740-gpu-diagnostics` in Desktop Mode and redirect stdout to a file if needed.
It reports provenance, current OS/kernel, installed Mesa/libdrm/firmware package
versions, PCI-to-DRM mapping, connector state/modes, configured session options,
the current Gamescope executable, selected graphics environment variables and
open DRM nodes. It makes no system changes and does not elevate privileges.
Some process/journal data may require running it as the session owner or root.

Firmware package versions are not GPU VBIOS revisions. An open DRM node is not
proof that a GPU renders the game; utilization testing remains separate. Review
logs before sharing because application command lines/journal entries may contain
personal information. The tool never dumps the complete process environment.

## Verification without building an ISO

```bash
python3 -m unittest discover -s tests -v
bash -n build_files/build.sh system_files/usr/bin/t740-build-info \
  system_files/usr/bin/t740-gpu-diagnostics installer/build.sh \
  installer/titanoboa_hook_postrootfs.sh
```

Unit tests validate metadata and integration contracts. Actual container/ISO
builds, the digest-based Anaconda installation and the on-screen Conky layout
still require integration testing when a new ISO is authorized.
