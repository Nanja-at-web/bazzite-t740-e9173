# Development validation, 2026-11-08

Scope: Bazzite-style custom versioning, build metadata, locked image inputs and
GPU diagnostics. No container or ISO build was requested or started for this
change. Main remains unchanged.

Passed locally:

- 20 Python unit/integration-contract tests (`python3 -m unittest discover -s tests -v`).
- Version generation returned `45.20261105.1-polaris-sdl` from the locked
  Bazzite `45.20261105` base and custom revision configuration.
- OCI metadata for both locked Bazzite base digests was checked directly in
  GHCR and reports `org.opencontainers.image.version=45.20261105`.
- The locked legacy custom payload has no OCI version label. Its lock value is
  explicitly `null`, and the ISO workflow now rejects it instead of assigning
  a misleading new version.
- Bash syntax checks, individually, for the metadata display helper, diagnostics,
  system build script, installer build script and Anaconda postrootfs hook.
- Parsing of the ISO workflow as YAML and confirmation that its push trigger is
  restricted to main, with no pull-request ISO trigger.
- `git diff --check`.
- Resolution of three Linux/AMD64 GHCR manifests to SHA-256 references in
  `image-lock.json`. These are current development inputs, not the historical
  inputs of hardware-validated ISO build #4.

Not validated here: Podman image creation/rechunking, installation from a
digest-pinned containers-storage payload, on-screen Conky rendering or a complete
VM/hardware installation. Those require a later authorized image build/test.
`just` and `shellcheck` were not installed in this local environment; the
Justfile-specific integration check and ShellCheck remain part of the later
container workflow validation.
The validated hardware baseline remains ISO build #4, as documented in README.

## Container integration validation: workflow run #15

The container workflow was manually dispatched for development commit
`430665e08c95fb69514569d2400bcd0505d5947a` without merging to `main`:

- Run: <https://github.com/Nanja-at-web/bazzite-t740-e9173/actions/runs/42486319431>
- Result: success.
- `just` installation and Justfile syntax validation: success.
- Container build and `bootc container lint`: success.
- rpm-ostree rechunking: success.
- OCI provenance labels were restored after rechunking, including version
  `45.20261105.1-polaris-sdl`, full source revision, creation time and the
  digest-pinned Bazzite base.
- The expected version tag `45.20261105.1-polaris-sdl` was generated and applied
  to the local test image.
- Registry login, GHCR push, Cosign installation and signing were skipped by the
  workflow's default-branch guards.
- The published `latest` AMD64 digest remained
  `sha256:2b844d7734a68477db72856d5ce542a2d71d989a4c60900fea3fb47b2683fd51`
  and still has no version label.

Because the test image was intentionally not published, its runner-local image
ID is not a durable registry digest and cannot yet be selected as an ISO
payload. Publishing the validated container on the default branch and recording
its resulting GHCR digest is the next release step. No ISO was built.
