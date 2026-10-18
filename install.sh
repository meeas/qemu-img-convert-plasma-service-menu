#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
system=false
uninstall=false
prefix=/usr/local
custom_prefix=false
usage() {
    cat <<'HELP'
Usage: bash install.sh [--system] [--uninstall] [--prefix DIR]

Install QEMU Image Converter for the current user by default.
  --system       Install for all users under /usr/local (usually requires sudo).
  --uninstall    Remove the selected user or system installation.
  --prefix DIR   Override /usr/local for --system; use an absolute path.
  -h, --help     Show this help.

Examples:
  bash install.sh
  sudo bash install.sh --system
  bash install.sh --uninstall
  sudo bash install.sh --system --uninstall
HELP
}
while (($#)); do
    case "$1" in
        --system) system=true ;;
        --uninstall) uninstall=true ;;
        --prefix)
            [[ $# -ge 2 && "$2" == /* ]] || { echo '--prefix requires an absolute path.' >&2; exit 2; }
            prefix="${2%/}"
            [[ -n "$prefix" ]] || { echo '--prefix cannot be /.' >&2; exit 2; }
            custom_prefix=true
            shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done
if "$custom_prefix" && ! "$system"; then
    echo '--prefix requires --system.' >&2
    exit 2
fi
if "$system"; then
    data_dir="$prefix/share"
    app_dir="$prefix/lib/qemu-image-converter"
    # Publicly readable environments/launchers even with a restrictive root umask.
    umask 022
else
    data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
    app_dir="$data_dir/qemu-image-converter"
fi
[[ "$data_dir" == /* ]] || { echo 'XDG_DATA_HOME must be an absolute path.' >&2; exit 2; }

if "$uninstall"; then
    # Remove only this scope's launchers and private application environment.
    rm -f -- "$data_dir/kio/servicemenus/qemu-image-converter.desktop" \
        "$data_dir/applications/io.controlthings.qemu-image-converter.desktop"
    rm -rf -- "$app_dir"
    echo "Removed QEMU Image Converter from $app_dir"
    exit 0
fi

command -v qemu-img >/dev/null || { echo 'qemu-img must be installed first.' >&2; exit 1; }
command -v kdialog >/dev/null || { echo 'kdialog must be installed first (used by Convert to...).' >&2; exit 1; }
# dbus-next 0.2.3 imports typing.no_type_check_decorator, removed in 3.15.
# Prefer PATH's Python, but fall back to the host interpreter when necessary.
python_bin=""
default_python=python3
if "$system"; then
    # A shared install must not default to an administrator's private Python.
    default_python=/usr/bin/python3
fi
for candidate in "${PYTHON:-$default_python}" /usr/bin/python3; do
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
install -m 755 "$source_dir/qemu-image-converter.py" "$app_dir/qemu-image-converter.py"

# Generate an absolute, correctly escaped Exec argument for this account.
"$app_dir/venv/bin/python" - "$app_dir" "$data_dir" <<'PY'
import os
from pathlib import Path
import subprocess
import sys
app, data = map(Path, sys.argv[1:])
def quoted(value):
    value = str(value).replace('%', '%%')
    # First Exec quoting, then .desktop value backslash escaping.
    value = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + value.replace('\\', '\\\\') + '"'
helper = app / 'qemu-image-converter.py'
formats = subprocess.check_output(
    [str(app / 'venv/bin/python'), str(helper), '--list-formats'], text=True).splitlines()
if not formats:
    raise SystemExit('No standalone writable QEMU image formats found.')
common = [('qcow2', 'QCOW2'), ('vmdk', 'VMDK'), ('vdi', 'VDI'),
          ('vhdx', 'VHDX'), ('raw', 'Raw Image')]
available = [(fmt, label) for fmt, label in common if fmt in formats]
command = quoted(app / 'venv/bin/python') + ' ' + quoted(helper)
menu = data / 'kio/servicemenus/qemu-image-converter.desktop'
menu.write_text('''[Desktop Entry]
Type=Service
MimeType=application/x-vmdk-disk;application/x-virtualbox-vmdk;application/x-qemu-disk;application/x-qed-disk;application/x-vdi-disk;application/x-vhd-disk;application/x-vhdx-disk;application/x-raw-disk-image;application/x-raw-floppy-disk-image;application/x-cd-image;application/x-apple-diskimage;
Actions=''' + ''.join(fmt + ';' for fmt, _ in available) + ("_SEPARATOR_;" if available else "") + '''choose;
X-KDE-Protocols=file
X-KDE-RequiredNumberOfUrls=1
X-KDE-Priority=TopLevel
X-KDE-Submenu=Convert
Icon=drive-harddisk
''' + ''.join('''
[Desktop Action ''' + fmt + ''']
Name=Convert to ''' + label + '''
Icon=drive-harddisk
Exec=''' + command + ' -O ' + fmt + ' -- %f\n' for fmt, label in available) + '''

[Desktop Action choose]
Name=Convert to...
Icon=drive-harddisk
Exec=''' + command + ' --choose -- %f\n')
menu.chmod(0o755)
(data / 'applications/io.controlthings.qemu-image-converter.desktop').write_text('''[Desktop Entry]
Type=Application
Name=QEMU Image Converter
Icon=drive-harddisk
NoDisplay=true
Terminal=false
Exec=''' + command + ' --choose -- %f\n')
# Remove superseded launchers only after their replacements are ready.
(data / 'kio/servicemenus/convert-to-qcow2.desktop').unlink(missing_ok=True)
(data / 'applications/io.controlthings.vmdk-to-qcow2.desktop').unlink(missing_ok=True)
print('Installed Dolphin action:', menu)
PY

echo 'Ready. Right-click a disk image in Dolphin and open Convert.'
