#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="${XDG_DATA_HOME:-$HOME/.local/share}/vmdk-to-qcow2"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"

command -v qemu-img >/dev/null || { echo 'qemu-img must be installed first.' >&2; exit 1; }
# dbus-next 0.2.3 imports typing.no_type_check_decorator, removed in 3.15.
# Prefer PATH's Python, but fall back to the host interpreter when necessary.
python_bin=""
for candidate in "${PYTHON:-python3}" /usr/bin/python3; do
    if command -v "$candidate" >/dev/null && "$candidate" -c \
        'import sys; sys.exit(not ((3, 10) <= sys.version_info < (3, 15)))'; then
        python_bin="$candidate"
        break
    fi
done
[[ -n "$python_bin" ]] || { echo 'Python 3.10–3.14 is required by dbus-next 0.2.3.' >&2; exit 1; }
mkdir -p "$app_dir" "$data_dir/kio/servicemenus" "$data_dir/applications"
# Recreate the private environment so reinstalling repairs an incompatible one.
"$python_bin" -m venv --clear "$app_dir/venv"
"$app_dir/venv/bin/python" -m pip install 'dbus-next==0.2.3'
"$app_dir/venv/bin/python" -c 'from dbus_next.aio import MessageBus'
install -m 755 "$source_dir/vmdk-to-qcow2.py" "$app_dir/vmdk-to-qcow2.py"

# Generate an absolute, correctly escaped Exec argument for this account.
"$app_dir/venv/bin/python" - "$app_dir" "$data_dir" <<'PY'
import os
from pathlib import Path
import sys
app, data = map(Path, sys.argv[1:])
def quoted(value):
    value = str(value).replace('%', '%%')
    # First Exec quoting, then .desktop value backslash escaping.
    value = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + value.replace('\\', '\\\\') + '"'
command = quoted(app / 'venv/bin/python') + ' ' + quoted(app / 'vmdk-to-qcow2.py')
menu = data / 'kio/servicemenus/convert-to-qcow2.desktop'
menu.write_text('''[Desktop Entry]
Type=Service
MimeType=application/x-vmdk-disk;application/x-virtualbox-vmdk;
Actions=convertToQcow2;
X-KDE-Protocols=file
X-KDE-RequiredNumberOfUrls=1
X-KDE-Priority=TopLevel

[Desktop Action convertToQcow2]
Name=Convert to qcow2
Icon=drive-harddisk
Exec=''' + command + ' %f\n')
menu.chmod(0o755)
(data / 'applications/io.controlthings.vmdk-to-qcow2.desktop').write_text('''[Desktop Entry]
Type=Application
Name=VMDK to qcow2
Icon=drive-harddisk
NoDisplay=true
Terminal=false
Exec=''' + command + ' %f\n')
print('Installed Dolphin action:', menu)
PY

echo 'Ready. Right-click a VMDK in Dolphin and choose Convert to qcow2.'
