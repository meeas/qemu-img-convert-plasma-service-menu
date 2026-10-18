# VMDK to qcow2 for KDE Plasma

Convert virtual machine disks from VMDK to qcow2 directly from Dolphin's
right-click menu. Conversion runs with a native Plasma job notification showing
progress, a Cancel button, and the result.

## Features

- Convert one local VMDK at a time with `qemu-img`.
- Save the qcow2 beside the source, leaving the VMDK intact.
- Protect existing output files and symlinks from being overwritten.
- Handle filenames containing spaces and shell metacharacters.
- Install for your user account without `sudo` or changes to system Python.

## Requirements

- Linux with KDE Plasma 6 and Dolphin.
- `qemu-img` installed on the host and available in Dolphin's `PATH`.
- Python **3.10–3.14** with `venv` and `pip` support.
- Internet access during installation to download `dbus-next==0.2.3` from PyPI.
- Write access and enough free space in the source directory for the converted
  image.

The destination filesystem must support Linux `renameat2(RENAME_NOREPLACE)`
for safe publication of the completed image.

## Installation

Download or clone this repository, open a terminal in its directory, and run:

```bash
bash install.sh
```

The installer creates a private Python environment, installs the helper, and
adds the Dolphin action. It checks `python3` on your `PATH`, falling back to
`/usr/bin/python3` if needed. Python 3.15 is not supported by the pinned D-Bus
dependency. You can supply a preferred interpreter with
`PYTHON=/path/to/python bash install.sh`.

Files are installed under `${XDG_DATA_HOME:-$HOME/.local/share}`:

| Location | Purpose |
| --- | --- |
| `vmdk-to-qcow2/` | Conversion helper and private Python environment |
| `kio/servicemenus/convert-to-qcow2.desktop` | Dolphin context-menu action |
| `applications/io.controlthings.vmdk-to-qcow2.desktop` | Job name and icon |

Close and reopen Dolphin if the action does not appear immediately.

## Usage

1. Shut down the virtual machine using the disk.
2. Right-click its `.vmdk` file in Dolphin.
3. Choose **Convert to qcow2**.

For example, `My VM.vmdk` produces `My VM.qcow2` in the same directory.
For a split VMDK, select the descriptor `.vmdk` file, rather than a `-flat`
or `-s001` extent.

Progress appears in Plasma's job notifications. Use **Cancel** to stop a
conversion; stopping the process can take up to five seconds. Plasma controls
notification visibility, including Do Not Disturb settings. Small images may
finish before a progress notification is visible.

### Output safety

Conversion writes to a hidden `.part` file in the destination directory. Once
complete, the file is atomically renamed to the final `.qcow2` name. An existing
file or symlink at that name causes an error, even if it was created while the
conversion was running.

Failures and cancellation remove the temporary file. A forced kill or power
loss can leave a hidden `.part` file; remove it only after confirming that no
conversion is running.

## Troubleshooting

**The menu action is missing:** close and reopen Dolphin, select a single local
`.vmdk` file, and check that installation completed successfully.

**Nothing happens or conversion fails:** run the installed helper from a terminal
to see diagnostics:

```bash
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
"$data_dir/vmdk-to-qcow2/venv/bin/python" \
  "$data_dir/vmdk-to-qcow2/vmdk-to-qcow2.py" '/path/to/My VM.vmdk'
```

The helper requires a running Plasma session and its job service. If that
service is unavailable, it reports the error on stderr and through `kdialog`
when available. Conversion starts only after the native job is created.

**`qemu-img` is missing:** install it on the host. An installation only inside a
toolbox or container is not available to the Dolphin helper.

**The output already exists:** move or rename the existing `.qcow2` before
converting again.

**Python or dependency errors:** confirm that Python 3.10–3.14 with `venv` and
`pip` is available, then run `bash install.sh`. Each installation recreates the
private environment and checks that the D-Bus dependency imports successfully.

## Uninstall

Remove the installed files for your user account:

```bash
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -- "$data_dir/kio/servicemenus/convert-to-qcow2.desktop"
rm -- "$data_dir/applications/io.controlthings.vmdk-to-qcow2.desktop"
rm -r -- "$data_dir/vmdk-to-qcow2"
```

Your source and converted disk images are kept.

## Development

See [current status and validation](docs/STATUS.md) for development checks and
remaining validation. The integration uses Plasma's `JobViewServerV2` and
`JobViewV3` D-Bus interfaces.

## License

See [LICENSE](LICENSE) for the GNU General Public License, version 3.
