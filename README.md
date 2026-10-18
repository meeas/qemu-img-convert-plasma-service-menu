# QEMU Image Converter

Convert virtual machine disk images from Dolphin's right-click menu, with
native KDE Plasma progress notifications and cancellation.

```text
Convert ▸
    Convert to QCOW2
    Convert to VMDK
    Convert to VDI
    Convert to VHDX
    Convert to Raw Image
    ────────────────────
    Convert to...
```

## Features

- Convert one local disk image at a time using `qemu-img`.
- Automatically detect the input format from its contents.
- Save beside the source, or choose a format and destination with **Convert to...**.
- Keep source images intact and protect existing destination files and symlinks.
- See progress, cancel a conversion, and receive completion or error notifications.
- Install for your user account without `sudo` or changes to system Python.

## Requirements

- Linux with KDE Plasma 6 and Dolphin.
- Host-installed `qemu-img` and `kdialog`, available in Dolphin's `PATH`.
- Python **3.10–3.14** with `venv` and `pip` support.
- Internet access during installation to download `dbus-next==0.2.3` from PyPI.
- Write access and enough free space in the destination directory.

The destination filesystem must support Linux `renameat2(RENAME_NOREPLACE)`
for safe publication of completed images.

## Installation

Download or clone this repository, open a terminal in its directory, and run:

```bash
bash install.sh
```

The installer creates a private Python environment, checks available QEMU output
formats, and adds the Dolphin menu. It checks `python3` on your `PATH`, falling
back to `/usr/bin/python3` if needed. Python 3.15 is not supported by the pinned
D-Bus dependency. You can supply a preferred interpreter with
`PYTHON=/path/to/python bash install.sh`.

Files are installed under `${XDG_DATA_HOME:-$HOME/.local/share}`:

| Location | Purpose |
| --- | --- |
| `qemu-image-converter/` | Helper and private Python environment |
| `kio/servicemenus/qemu-image-converter.desktop` | Dolphin Convert submenu |
| `applications/io.controlthings.qemu-image-converter.desktop` | Job name and icon |

Close and reopen Dolphin if the menu does not appear immediately. Run the
installer again after a QEMU upgrade to refresh the direct format shortcuts.

### System-wide installation

To make the tool available to all desktop users, run:

```bash
sudo bash install.sh --system
```

This installs the helper and its private Python environment into
`/usr/local/lib/qemu-image-converter`, and the desktop entries into
`/usr/local/share/kio/servicemenus` and `/usr/local/share/applications`.
It uses the system Python by default and keeps Python dependencies separate
from the OS Python environment. Conversion still runs as the desktop user.

A user installation takes precedence over the system installation. To switch
to the shared installation, remove your user installation with
`bash install.sh --uninstall`. Installing or uninstalling one scope leaves the
other scope intact.

For a different system prefix, use `--system --prefix /absolute/path` for both
installation and removal. Its `share` directory must be included in the desktop
session's `XDG_DATA_DIRS` for Dolphin to discover the menu. The default
`/usr/local/share` is a standard XDG data location.

## Usage

1. Shut down the virtual machine using the disk.
2. Right-click one local disk image in Dolphin.
3. Open **Convert** and choose a destination format.

For example, **Convert to QCOW2** turns `My VM.vmdk` into `My VM.qcow2` beside
the source. Raw output uses `.img`; VHD output uses `.vhd`. Direct actions keep
the source's base name. If the resulting filename already exists, including
when it matches the source name, conversion reports an error. Use
**Convert to...** to choose a different filename or directory.

**Convert to...** first opens a format selector, then a native save dialog.
The selected format determines the image contents, even if you choose a
different filename extension. Cancel either dialog to exit without converting.

For a split VMDK, select the descriptor `.vmdk` file, rather than a `-flat`
or `-s001` extent. For an image with backing files, keep those files accessible;
the output contains the current visible disk contents as a standalone image.
This is a disk-content conversion, not a transfer of all snapshot history or
VM configuration.

Progress appears in Plasma's job notifications under **QEMU Image Converter**.
Use **Cancel** to stop conversion; stopping the process can take up to five
seconds. Plasma controls visibility, including Do Not Disturb settings. Small
images may finish before a progress notification is visible.

### Supported images and formats

The helper accepts local image files readable by the installed QEMU, including
raw files and files with unusual extensions. Dolphin shows the menu for
recognized disk-image MIME types, such as VMDK, QCOW, VDI, VHD, VHDX, and raw
disk images. An extensionless or unrecognized image can be converted from the
command line.

Only available common formats receive direct menu shortcuts. **Convert to...**
discovers the other supported outputs by testing small disposable conversions.
It offers formats that work with default options and produce a single local
image file. Read-only drivers, protocol drivers, encrypted output requiring
secrets, split output, and formats requiring special options are excluded.
Format availability does not guarantee that every source image's size or
features can be represented by that format; QEMU errors appear in the job.
Some formats, including VHD, may round the virtual disk size upward and pad
the additional space with zeros.

### Output safety

Conversion writes inside a hidden `.part` directory beside the destination.
Once complete, the single output file is atomically moved to the final name
with owner-only read/write permissions. An existing file or symlink is never
replaced, including one created while conversion is running.

Failures and cancellation remove the staging directory. A forced kill or power
loss can leave a hidden `.part` directory; remove it only after confirming that
no conversion is running.

## Command line

Run from a Plasma desktop session. Source-format detection is automatic.

```bash
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
python_bin="$data_dir/qemu-image-converter/venv/bin/python"
helper="$data_dir/qemu-image-converter/qemu-image-converter.py"

# Convert beside the source.
"$python_bin" "$helper" -O qcow2 -- '/path/to/My VM.vmdk'

# Choose a specific destination.
"$python_bin" "$helper" -O vdi -o '/path/to/Converted.vdi' -- '/path/to/disk.img'

# Open the format and destination dialogs.
"$python_bin" "$helper" --choose -- '/path/to/disk.qcow2'

# List available standalone output formats; no desktop session needed.
"$python_bin" "$helper" --list-formats
```

## Troubleshooting

**The menu is missing:** reopen Dolphin and select a single local disk image.
The menu is filtered by MIME type, so use the command line for an unrecognized
image. Check that installation completed successfully.

**Conversion fails or nothing appears:** use the command-line examples above
to see diagnostics. The helper requires a running Plasma job service and
starts conversion only after the native job is created. Setup errors are
reported on stderr and through `kdialog` when available.

**A command is missing:** install `qemu-img` and `kdialog` on the host. Programs
installed only inside a toolbox or container are not available to the helper.

**The output already exists:** use **Convert to...** to select a new filename,
or move the existing output before converting again.

**Python or dependency errors:** confirm Python 3.10–3.14 with `venv` and `pip`
is available, then run `bash install.sh`. Installation recreates the private
environment and checks that the D-Bus dependency imports successfully.

## Uninstall

Remove the current user's installation:

```bash
bash install.sh --uninstall
```

Remove the system-wide installation:

```bash
sudo bash install.sh --system --uninstall
```

Removal deletes the selected installation's desktop entries and private helper
environment. It does not require Python, QEMU, an internet connection, or a
running desktop. Your source and converted disk images are kept. Use the same
`XDG_DATA_HOME` or system `--prefix` that you used when installing.

## Development

Run the regression suite from the repository using the installed environment:

```bash
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
"$data_dir/qemu-image-converter/venv/bin/python" -m unittest discover -s tests -v
```

Tests use real QEMU conversions without requiring a desktop session. See
[current status](docs/STATUS.md) for validation evidence and manual checks,
and [design decisions](docs/DECISIONS.md) for the integration's scope.

The full installer lifecycle test runs offline when a dependency wheel is
provided; otherwise that test is skipped:

```bash
wheel_dir="$(mktemp -d)"
python_bin="${XDG_DATA_HOME:-$HOME/.local/share}/qemu-image-converter/venv/bin/python"
"$python_bin" -m pip download --no-deps --dest "$wheel_dir" 'dbus-next==0.2.3'
QEMU_CONVERTER_TEST_WHEELS="$wheel_dir" "$python_bin" -m unittest discover -s tests -v
rm -r -- "$wheel_dir"
```

## License

See [LICENSE](LICENSE) for the GNU General Public License, version 3.
