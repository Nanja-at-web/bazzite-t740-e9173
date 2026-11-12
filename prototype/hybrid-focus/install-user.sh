#!/usr/bin/env bash

set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
data_home="${XDG_DATA_HOME:-${HOME}/.local/share}"
config_home="${XDG_CONFIG_HOME:-${HOME}/.config}"
bin_home="${XDG_BIN_HOME:-${HOME}/.local/bin}"
install_root="${data_home}/bazzite-hybrid-focus"
unit_dir="${config_home}/systemd/user"
application_dir="${data_home}/applications"

for command in python3 busctl systemctl install cp; do
    command -v "${command}" >/dev/null || {
        echo "Missing required command: ${command}" >&2
        exit 1
    }
done

busctl --system tree org.shadowblip.InputPlumber --list >/dev/null
test -f "${source_dir}/inputplumber/bazzite-hybrid-desktop.yaml"
grep -q '^kind: DeviceProfile$' "${source_dir}/inputplumber/bazzite-hybrid-desktop.yaml"

install -d -m 0755 "${install_root}/src" "${install_root}/inputplumber" "${bin_home}" "${unit_dir}" "${application_dir}"

cp -a "${source_dir}/src/." "${install_root}/src/"
install -m 0644 "${source_dir}/inputplumber/bazzite-hybrid-desktop.yaml" "${install_root}/inputplumber/bazzite-hybrid-desktop.yaml"
install -m 0755 "${source_dir}/bin/bazzite-hybrid-focusd" "${bin_home}/bazzite-hybrid-focusd"
install -m 0755 "${source_dir}/bin/bazzite-hybrid-focusctl" "${bin_home}/bazzite-hybrid-focusctl"
install -m 0755 "${source_dir}/bin/bazzite-hybrid-focus-diagnostics" "${bin_home}/bazzite-hybrid-focus-diagnostics"
render_template() {
python3 - "$1" "$2" "${bin_home}" <<'PY'
import os
from pathlib import Path
import sys

source, destination, bin_home = map(Path, sys.argv[1:])
rendered_bin_home = str(bin_home).replace("%", "%%")
content = source.read_text(encoding="utf-8").replace(
    "@BIN_HOME@", rendered_bin_home
)
destination.write_text(content, encoding="utf-8")
os.chmod(destination, 0o644)
PY
}

render_template "${source_dir}/systemd/bazzite-hybrid-focus.service" "${unit_dir}/bazzite-hybrid-focus.service"
render_template "${source_dir}/applications/bazzite-hybrid-send-desktop.desktop" "${application_dir}/bazzite-hybrid-send-desktop.desktop"
render_template "${source_dir}/applications/bazzite-hybrid-return-game.desktop" "${application_dir}/bazzite-hybrid-return-game.desktop"

systemctl --user daemon-reload
systemctl --user enable --now bazzite-hybrid-focus.service

echo "Hybrid Focus prototype installed for ${USER:-current user}."
echo "Pin 'Return Controller to Game' to the secondary Plasma panel or desktop."
