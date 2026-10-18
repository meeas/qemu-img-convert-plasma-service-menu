# Current status

QEMU Image Converter extends the working VMDK-to-qcow2 helper to local images
readable by QEMU and standalone output formats that work with default options.
The multi-format integration is committed as `309a490` on `main`. Menu-order
and installer lifecycle changes remain uncommitted.

## Implemented

- Renamed the helper and desktop identity to QEMU Image Converter.
- Added a top-level Dolphin `Convert` submenu for recognized disk-image MIME
  types and one local file. Common available formats have direct actions;
  `Convert to...` uses kdialog for format and destination selection.
- Grouped `Convert to...` after a separator to keep it below format shortcuts;
  KIO sorts internal identifiers within each group.
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
- User installation remains the default. `--system` installs under `/usr/local`
  using a shared private environment and system Python; `--prefix` can override
  that location. `--uninstall` removes only the selected installation scope
  without runtime dependencies. See [README.md](../README.md) for commands.

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
- The expanded suite passed all 11 tests, including offline real installation
  and removal in independent user and system-prefix layouts, dependency-free
  uninstall, argument validation, repeated removal, unrelated-file preservation,
  final chooser grouping, escaped paths, and shared environment permissions
  under an initially restrictive umask. The system layout was tested under a
  temporary prefix, without privileged writes to `/usr/local`.
- Refreshed the normal user installation offline and confirmed its installed
  action list ends with `_SEPARATOR_;choose;`.

## Remaining validation

The user confirmed the multi-format integration works. After reopening Dolphin,
confirm that `Convert to...` now appears at the bottom after a separator.
Visible progress and Cancel on a larger image have not been separately confirmed.
Actual installation under `/usr/local` and visibility from another desktop
account remain unverified; the equivalent prefix lifecycle passed locally.
No remote CI results are available.
