# Design decisions

## Accepted: native Dolphin integration for local disk images

Use a service menu with `X-KDE-Submenu=Convert` and top-level priority.
Direct action labels are `Convert to QCOW2` and equivalent; `Convert to...`
opens a format selector followed by a native save dialog using kdialog.
The application and notification identity is QEMU Image Converter.

Match recognized disk-image MIME types and one local file. Dolphin determines
menu visibility from MIME types; QEMU probes the source format only when a
conversion is requested. Accept other extensions through the command line.
This avoids a compiled Dolphin plugin or probing files during menu creation.

Direct actions write beside the source; the chooser can change destination.
Existing outputs, including the source's own filename, cause an error. Preserve
native progress, cancellation, the source, and protection against publication
races. Batch jobs, remote URLs/devices as top-level inputs, encryption controls,
split output, and format-specific options are outside the accepted scope.

## Accepted: discover default standalone output capabilities

QEMU's advertised drivers include protocols and read-only formats. Probe small
raw-to-target conversions in disposable directories; accept only outputs whose
detected format matches the requested driver and which produce one file.
This also excludes formats requiring secrets or additional options. Discovery
uses the installed QEMU rather than a fixed writable-format list.

Generate common shortcuts at installation; rediscover outputs for the chooser
and validate direct requests at runtime. Format support depends on the input's
size and features as well, so surface real conversion failures through Plasma.

## Accepted: publish only standalone output without replacing destinations

Stage in a hidden private directory on the destination filesystem. Reject
auxiliary output files, set owner-only file permissions, and publish with
Linux `renameat2(RENAME_NOREPLACE)`. Preserve the output basename while staging
for formats whose embedded metadata uses that name. Cancel or failure stops
the child process and removes the whole staging directory.

## Accepted: compatible private Python environment

dbus-next 0.2.3 imports an API removed in Python 3.15. Use Python 3.10–3.14,
falling back to the system interpreter when PATH selects an incompatible one.
Recreate the private environment on installation and smoke-test the import.
