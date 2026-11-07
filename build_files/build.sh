#!/bin/bash

set -ouex pipefail

# Copy the contents of system_files/ of the git repo to /
cp -avf "/ctx/system_files"/. /

# Fail the image build if the selected Bazzite base does not provide Gamescope.
# Current Bazzite uses the regular binary with the SDL compatibility backend;
# the separate gamescope-legacy executable was removed upstream.
test -x /usr/bin/gamescope

# The session fragment is sourced by gamescope-session-plus. Keep it readable
# and make the diagnostics helper directly executable.
chmod 0644 /etc/gamescope-session-plus/sessions.d/steam
chmod 0755 /usr/bin/t740-gpu-diagnostics
