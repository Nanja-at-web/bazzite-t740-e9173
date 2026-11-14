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
payload is the signed revision `45.20261105.2-polaris-sdl` at digest
`sha256:93dc4bb0199798624851db25908a922fe42826efee5f61f990bfe6443ff1d4fa`.

Building a new system container does not automatically change the pinned ISO
payload. After validating the published container, update `install_payload` to
its exact digest before requesting a new ISO. The installer uses this reference
both for its local OSTree payload and for the installed bootc origin, avoiding
an implicit switch to a newer `latest` during installation. Consequently,
automatic system updates do not advance beyond that pinned origin. Moving to a
new validated digest requires an explicit bootc switch/update of the origin.

The ISO workflow refuses to build unless the locked payload has a valid custom
version matching the version derived from the locked Bazzite base. The current
revision-2 payload satisfies that check, but an ISO is still created only by an
explicit manual workflow dispatch. Its filename will be
`bazzite-t740-e9173-45.20261105.2-polaris-sdl-amd64.iso`.

## Reproducible container release controls

The container creation time and `SOURCE_DATE_EPOCH` are derived from the Git
commit timestamp, not the wall clock of the GitHub runner. Rebuilding the same
commit with the same locked inputs therefore supplies the same timestamp to
Podman and the image build script. This removes one known source of needless
digest changes; complete byte-for-byte reproducibility still depends on the
base image and the behavior of all build tools.

### Container workflow policy

The container workflow starts on pull requests targeting `main`, pushes to
`main`, and explicit manual dispatch. There are no workflow-wide path exclusions:
a small `classify` job always explains why later work runs or is skipped. The
`result` job always checks required job outcomes, including blocked classification.
A workflow start does not itself mean an image will be built or published.

`scripts/classify-container-changes.py` reads Git objects without network access.
It emits deterministic JSON with classes, paths, reasons, blocking status, event,
base/head SHA, test/build/release decisions and `run_iso=false`. The optional
`--github-output` argument explicitly appends only boolean workflow outputs.
It never changes versions, source files or registry state.

| Class | Inputs | Container validation | Main-push release candidate |
| --- | --- | --- | --- |
| A | `Containerfile`, `build_files/**`, `system_files/**`, `installer/build-metadata.py`, `Justfile`, `image-template.env`, `build-version.json`, `scripts/build-version.py`, `scripts/build-created.py`, container-base lock changes | Yes | Yes |
| B | `.github/workflows/build.yml`, classifier, tag guard, `cosign.pub` | Yes | No |
| C | ISO workflow, `disk_config/**`, remaining `installer/**`, installer-base/payload lock changes | No | No |
| D | Provenance/policy tests, resolution-time-only or formatting-only lock changes | No | No |
| E | `README.md`, `docs/**`, `AGENTS.md`, `.agents/**` | No | No |
| F | `prototype/hybrid-focus/**`, `tests/test_hybrid_focus_*.py` | No | No |
| G | Any unclassified path | Blocked | Blocked |

All nonblocked classes run local software tests; no hardware acceptance test is
invoked. Mixed classes combine requirements. `Justfile` and `image-template.env`
are conservatively treated as whole-file container inputs. The shared installer
metadata writer is explicitly a container input, unlike the rest of the installer.
The public verification key is release infrastructure, never a private secret.

The lock is compared as JSON at both commits. Container-base changes are A;
installer-base/payload changes are C. Only `resolved_at` or formatting changes are
D. Unknown/missing keys, unsupported schema/platform, malformed JSON, missing
objects, unsupported changes and an empty diff block classification. Lock
addition, deletion or rename also requires explicit review. No unknown path is
silently ignored, including newly introduced build-context ignore files.

PR classification uses the merge base of the event base SHA and PR head SHA.
Push classification uses the complete event-before/event-after range, so all
commits in a push are considered. Git name/status records are NUL-separated;
renames classify both old and new paths. The base must be an ancestor of head.
A complete history is checked out for classification. Missing or divergent bases
fail closed; there is no best-effort fallback to a smaller diff.

Manual dispatch classifies the selected commit against its first parent and
validates the complete selected source tree. It always requests tests and a
container validation build when classification succeeds. Initial commits or
unclassifiable last-commit changes block it. Dispatch is validation-only even on
`main`; it never checks release-tag availability, signs, publishes or updates
`latest`. PRs and pure B changes have the same no-publication boundary.

### Publication and immutable version tags

Only a `push` to `refs/heads/main` with class A, nonblocking classification,
successful tests and successful container validation may enter `publish`.
Package-write permission and `SIGNING_SECRET` are confined to that job. PRs never
receive the signing key or a publication path. There is no `pull_request_target`.

The validation job builds/rechunks without registry-write credentials. The
publication job separately checks the version tag before its release build;
it builds the same source again after that check. This deliberately avoids a
large cross-job image artifact. The two builds are not assumed byte-identical.
The released image is identified by its actual pushed digest.

The unchanged `scripts/check-version-tag.py` rejects an existing tag (exit 1)
and registry/tool/response errors (exit 2). A free tag requires a valid tag-list
response (exit 0). There is no automatic revision increment. An explicitly
approved new release must choose a previously unused version; an existing
`45.20261105.2-polaris-sdl` tag therefore blocks a new release with that version.

Immediately before the first registry push the tag is checked again. Publication
then proceeds in this order:

1. Push only the immutable version tag and capture the actual SHA-256 digest.
2. Sign exactly `repository@digest` with the existing signing key.
3. Verify that same digest against `cosign.pub`.
4. Copy the verified remote digest to `latest` and the other convenience aliases,
   excluding the immutable version tag from this alias loop.

Tag checks, push, signing and verification do not tolerate errors. If signing or
verification fails, the workflow fails and alias promotion never starts. The
already-pushed version tag may remain unsigned or unverified: it is not deleted,
reused or automatically repaired. Recovery requires a separate explicit decision.
A later alias-copy failure can leave partially updated aliases; no atomic
multi-tag transaction or automatic rollback is claimed.

Publication remains serialized per repository with `cancel-in-progress: false`.
Only pull-request validations share a PR-specific group and may cancel an older
validation of that same PR. Each main-push or manual-dispatch validation uses a
unique `github.run_id` group with cancellation disabled. A later infrastructure
commit therefore cannot cancel an earlier container-relevant main validation.
This does not promise an unlimited publication queue. The read-then-push checks are not atomic against external
publishers; registry-enforced create-only tag semantics are not established.
A green workflow alone is not a substitute for recording the concrete digest
and signature verification result.

The ISO workflow remains byte-unchanged and manual-only. The classifier always
returns `run_iso=false`; no container job dispatches an ISO. No lock refresh,
revision update, deployment or hardware validation follows automatically from CI.
HP build #4 remains the separate historical hardware baseline. These are workflow
contracts and local-test evidence, not evidence of a new container or ISO build.

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
