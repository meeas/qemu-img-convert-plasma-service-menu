# Current status

QEMU Image Converter extends the working VMDK-to-qcow2 helper to local images
readable by QEMU and standalone output formats that work with default options.
The work is based on `88b7a76` on `main`; changes remain uncommitted.

## Implemented

- Renamed the helper and desktop identity to QEMU Image Converter.
- Added a top-level Dolphin `Convert` submenu for recognized disk-image MIME
  types and one local file. Common available formats have direct actions;
  `Convert to...` uses kdialog for format and destination selection.
- Removed the input extension restriction and fixed VMDK input format. QEMU
  now auto-detects sources, including unusual extensions through the CLI.
- Discover writable standalone formats with disposable conversion probes;
  exclude read-only/protocol drivers and formats needing secrets or options.
- Preserve Plasma jobs, cancellation, source files, and no-replace publication.
  Stage in a private directory, reject sidecar files, and publish with mode 0600.
- Added regression tests and public usage documentation. Accepted scope and
  implementation rationale are in [DECISIONS.md](DECISIONS.md).
- Installer replaces the old menu/application entries after creating their
  replacements. The old private helper directory is retained to avoid deleting
  unrelated files; new installations use `qemu-image-converter/`.

## Validation (2026-10-17)

- Eight regression tests passed using system Python 3.14 and QEMU 10.2.2.
  These include all 25 source/destination combinations among QCOW2, VMDK,
  VDI, VHDX, and raw, with source preservation and real content comparison.
- Tests cover existing files and dangling symlinks, publication races,
  conversion failure cleanup, process cancellation cleanup, chooser cancellation
  and selection, output naming, and capability filtering.
- Discovered nine standalone outputs: parallels, qcow, qcow2, qed, raw, vdi,
  vhdx, vmdk, and vpc. All nine passed conversions through the live Plasma job
  service, content comparison, and mode-0600 checks. VPC rounded the virtual
  size upward; QEMU comparison confirmed equal contents with zero padding.
- Installation into a temporary path containing spaces and `%` passed; the
  generated application desktop entry passed desktop-file-validate. Reviewed
  service-menu action names, MIME types, selection count, submenu, and escaping.
- Installed into the normal user data directory. Confirmed the installed helper
  matches the source, its `--help` works, the new menu is present, the obsolete
  launchers are removed, and the application desktop entry validates.
- Shell syntax, Python compilation, diff whitespace, and documentation local
  links/code fences/whitespace passed.

## Remaining validation

Confirm in Dolphin after reopening it:

1. Recognized disk images show `Convert` with the agreed action labels; selecting
   multiple files or a directory does not show this tool's actions.
2. A direct action creates the expected sibling image and a native job.
3. `Convert to...` opens the format selector followed by the save dialog; test
   a destination in another directory and cancellation at either dialog.
4. A larger disposable image shows progress; Cancel removes staging and leaves
   no final output. Existing output files are preserved and errors are visible.

The prior single-format installation was confirmed working by the user.
The new menu placement and dialog rendering require user confirmation. No
remote CI results are available.
