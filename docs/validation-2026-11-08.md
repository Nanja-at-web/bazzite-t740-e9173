# Development validation, 2026-11-08

Scope: build metadata, locked image inputs and GPU diagnostics. No container or
ISO build was requested or started for this change. Main remains unchanged.

Passed locally:

- 11 Python unit/integration-contract tests (`python3 -m unittest discover -s tests -v`).
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
The validated hardware baseline remains ISO build #4, as documented in README.
