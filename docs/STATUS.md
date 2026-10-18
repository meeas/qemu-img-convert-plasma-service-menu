# Current status

The initial repository code was present as untracked files on `main` at
`9a4b83c`. Changes remain uncommitted.

## Fix

The installed environment used Homebrew Python 3.15. `dbus-next==0.2.3`
imports `typing.no_type_check_decorator`, which Python 3.15 removed. This
caused an immediate ImportError before any Plasma job or output was created;
the helper incorrectly reported the dependency as missing.

The installer now selects Python 3.10–3.14, falling back from PATH to the
system interpreter, recreates its private environment on reinstall, and
checks the dependency import before installing launchers. Import failures
now include the interpreter version and underlying exception.

## Validation (2026-10-17)

- Reproduced the installed Python 3.15 import failure despite pip reporting
  dbus-next 0.2.3 installed.
- Installed into `/tmp` with Python 3.15 on PATH; the installer selected the
  system Python 3.14 and its dependency import passed.
- Ran that installed helper against the live Plasma JobView service and a
  real 8 MiB VMDK with a space in its filename. Conversion succeeded;
  `qemu-img info` reported qcow2 and `qemu-img compare` reported identical images.
- Reinstalled into the normal user data directory; dependency import and the
  installed helper's `--help` passed. Shell syntax, Python compilation, and
  edited-file whitespace checks passed.

## Remaining validation

The user confirmed the repaired installation works from Dolphin. Visible
progress and Cancel have not been separately confirmed; check these with a
larger disposable VMDK containing allocated data. Cancel should leave no final
qcow2 or hidden `.part` file. No remote CI evidence is available.

## Documentation

Replaced README.txt with a public-facing [README.md](../README.md), covering
requirements, installation, usage, output safety, troubleshooting, removal,
and licensing. Removed installation history and dated validation from the
README; validation evidence stays here. Reviewed commands against the installer,
checked local links and whitespace. Runtime code was unchanged by this rewrite.
