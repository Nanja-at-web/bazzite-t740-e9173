#!/usr/bin/env bash

set -euo pipefail

data_home="${XDG_DATA_HOME:-${HOME}/.local/share}"
config_home="${XDG_CONFIG_HOME:-${HOME}/.config}"
bin_home="${XDG_BIN_HOME:-${HOME}/.local/bin}"
install_root="${data_home}/bazzite-hybrid-focus"
unit="${config_home}/systemd/user/bazzite-hybrid-focus.service"

if [[ -x "${bin_home}/bazzite-hybrid-focusctl" ]]; then
    "${bin_home}/bazzite-hybrid-focusctl" game || true
fi

systemctl --user disable --now bazzite-hybrid-focus.service || true

rm -f "${bin_home}/bazzite-hybrid-focusd" "${bin_home}/bazzite-hybrid-focusctl" "${bin_home}/bazzite-hybrid-focus-diagnostics" "${unit}" "${data_home}/applications/bazzite-hybrid-send-desktop.desktop" "${data_home}/applications/bazzite-hybrid-return-game.desktop"
rm -rf -- "${install_root}"

systemctl --user daemon-reload
echo "Hybrid Focus prototype removed."
