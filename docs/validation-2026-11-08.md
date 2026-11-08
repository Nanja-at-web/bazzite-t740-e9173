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
