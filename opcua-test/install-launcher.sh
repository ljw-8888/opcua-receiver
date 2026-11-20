#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
exe="$PWD/OPCUA-Receiver"
test -x "$exe"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
install -Dm644 icons/opcua-receiver.svg "$data_dir/icons/hicolor/scalable/apps/opcua-receiver.svg"
mkdir -p -- "$data_dir/applications"
# A desktop entry parses string escapes first, then Exec quoting and field codes.
exec_path=$(printf '%s' "$exe" | sed -e 's/[\\"$`]/\\&/g' -e 's/\\/\\\\/g' -e 's/%/%%/g')
cat > "$data_dir/applications/opcua-receiver.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OPC UA 수신기
Exec="$exec_path"
Icon=opcua-receiver
StartupWMClass=OPCUA-Receiver
Terminal=false
Categories=Utility;
EOF
