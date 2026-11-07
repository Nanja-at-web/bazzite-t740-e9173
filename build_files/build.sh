#!/bin/bash

set -ouex pipefail

# Copy the contents of system_files/ of the git repo to /
cp -avf "/ctx/system_files"/. /

# Fail the image build if the selected Bazzite base ever stops shipping the
# compatibility compositor required by the E9170/Polaris generation.
test -x /usr/bin/gamescope-legacy

# The session fragment is sourced by gamescope-session-plus. Keep it readable
# and make the diagnostics helper directly executable.
chmod 0644 /etc/gamescope-session-plus/sessions.d/steam
chmod 0755 /usr/local/bin/t740-gpu-diagnostics
