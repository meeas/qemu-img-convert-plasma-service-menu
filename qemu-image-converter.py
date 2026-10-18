#!/usr/bin/env python3
"""Convert one local disk image with native KDE Plasma 6 job notifications.

Requires Python 3.10–3.14, dbus-next, qemu-img and a running Plasma session.
No Qt bindings, root access or Dolphin plugin are needed.
"""

import argparse
import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

try:
    from dbus_next import BusType, Message, MessageType, Variant
    from dbus_next.aio import MessageBus
except ImportError as error:
    print(f"Cannot import dbus-next with Python {sys.version.split()[0]}: {error}. "
          "Run install.sh, then use the installed virtual environment.",
          file=sys.stderr)
    sys.exit(1)

SERVICE = "org.kde.JobViewServer"
SERVER_IFACE = "org.kde.JobViewServerV2"
VIEW_IFACE = "org.kde.JobViewV3"
PROGRESS = re.compile(rb"\(([0-9]+(?:\.[0-9]+)?)/100%\)")
ERROR = 100  # KJob::UserDefinedError
CANCELED = 1  # KJob::KilledJobError / KIO::ERR_USER_CANCELED
APP_ID = "io.controlthings.qemu-image-converter"
APP_NAME = "QEMU Image Converter"
COMMON_FORMATS = ("qcow2", "vmdk", "vdi", "vhdx", "raw")
EXTENSIONS = {"raw": "img", "vpc": "vhd"}


def qemu_command() -> str:
    """Return the host qemu-img executable or raise a user-facing error."""
    executable = shutil.which("qemu-img")
    if not executable:
        raise RuntimeError("qemu-img was not found in PATH. Install qemu-img first.")
    return executable


def probe_format(executable: str, image_format: str) -> bool:
    """Test default standalone output support using a disposable 1 MiB image.

    Protocol drivers, read-only formats, and formats requiring extra options
    are excluded. Each subprocess has a five-second timeout. No user image is
    opened. The reported format and single-file layout must match the request.
    """
    if not re.fullmatch(r"[a-z0-9_-]+", image_format):
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="qemu-format-") as directory:
            root = Path(directory)
            source, output = root / "source", root / "output"
            with source.open("wb") as stream:
                stream.write(b"QEMU Image Converter format probe\n")
                stream.truncate(1024 * 1024)
            result = subprocess.run(
                [executable, "convert", "-f", "raw", "-O", image_format,
                 str(source), str(output)], capture_output=True, timeout=5,
                env=dict(os.environ, LC_ALL="C"))
            if result.returncode or set(root.iterdir()) != {source, output}:
                return False
            result = subprocess.run(
                [executable, "info", "--output=json", str(output)],
                capture_output=True, timeout=5)
            return (result.returncode == 0
                    and json.loads(result.stdout).get("format") == image_format)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def supported_formats() -> list[str]:
    """Discover installed formats supporting default standalone conversion.

    QEMU's help includes protocols as well as formats; conversion probes filter
    those out. Discovery is repeated on demand so QEMU upgrades take effect.
    """
    executable = qemu_command()
    result = subprocess.run([executable, "--help"], capture_output=True, text=True,
                            check=True, timeout=10, env=dict(os.environ, LC_ALL="C"))
    _, separator, section = result.stdout.partition("Supported image formats:")
    if not separator:
        raise RuntimeError("Cannot read the supported image formats from qemu-img.")
    candidates = sorted(set(section.strip().split("\n\n", 1)[0].split()))
    with ThreadPoolExecutor(max_workers=4) as pool:
        supported = list(pool.map(lambda name: probe_format(executable, name), candidates))
    return [name for name, available in zip(candidates, supported) if available]


def default_output(source: Path, image_format: str) -> Path:
    """Choose a sibling output; existing names are rejected, never replaced."""
    return source.with_suffix("." + EXTENSIONS.get(image_format, image_format))


def dialog(*arguments: str) -> str | None:
    """Run a native KDE chooser; return its value or None on user cancellation."""
    if not shutil.which("kdialog"):
        raise RuntimeError("Install kdialog to use Convert to..., or select a direct format.")
    result = subprocess.run(["kdialog", "--title", APP_NAME, "--desktopfile", APP_ID,
                             *arguments], capture_output=True, text=True)
    if result.returncode == 1:
        return None
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Could not open the conversion dialog.")
    return result.stdout.rstrip("\n")


def choose_output(source: Path) -> tuple[str, Path] | None:
    """Choose a supported format, then a local filename; cancellation writes nothing."""
    formats = supported_formats()
    if not formats:
        raise RuntimeError("No standalone writable image formats were found.")
    image_format = dialog("--combobox", "Convert to:", *formats,
                          "--default", "qcow2" if "qcow2" in formats else formats[0])
    if image_format is None:
        return None
    if image_format not in formats:
        raise ValueError(f"Unsupported output format: {image_format}")
    output = dialog("--getsavefilename", str(default_output(source, image_format)))
    if not output:
        return None
    return image_format, Path(os.path.abspath(output))


async def call(bus, destination, path, interface, member, signature="", body=None):
    reply = await asyncio.wait_for(bus.call(Message(
        destination=destination, path=path, interface=interface,
        member=member, signature=signature, body=body or [],
    )), timeout=10)
    if reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"{reply.error_name}: {' '.join(map(str, reply.body))}")
    return reply


class JobView:
    def __init__(self, bus, path, owner, cancel):
        self.bus, self.path, self.owner, self.cancel = bus, path, owner, cancel

    @classmethod
    async def create(cls, bus, source, output, cancel, image_format):
        hints = {
            "immediate": Variant("b", True),
            "title": Variant("s", f"Converting to {image_format.upper()}"),
            "descriptionLabel1": Variant("s", "Source"),
            "descriptionValue1": Variant("s", str(source)),
            "descriptionLabel2": Variant("s", "Destination"),
            "descriptionValue2": Variant("s", str(output)),
            "destUrl": Variant("s", output.as_uri()),
            "percent": Variant("u", 0),
        }
        reply = await call(bus, SERVICE, "/JobViewServer", SERVER_IFACE,
                           "requestView", "sia{sv}",
                           [APP_ID, 1, hints])
        job = cls(bus, reply.body[0], reply.sender, cancel)
        bus.add_message_handler(job.on_message)
        await call(bus, "org.freedesktop.DBus", "/org/freedesktop/DBus",
                   "org.freedesktop.DBus", "AddMatch", "s", [
                       f"type='signal',sender='{job.owner}',path='{job.path}',"
                       f"interface='{VIEW_IFACE}',member='cancelRequested'"
                   ])
        return job

    def on_message(self, message):
        if (message.message_type == MessageType.SIGNAL
                and message.sender == self.owner and message.path == self.path
                and message.interface == VIEW_IFACE
                and message.member == "cancelRequested"):
            self.cancel.set()

    async def update(self, percent):
        await call(self.bus, self.owner, self.path, VIEW_IFACE,
                   "update", "a{sv}", [{"percent": Variant("u", percent)}])

    async def finish(self, code=0, message=""):
        await call(self.bus, self.owner, self.path, VIEW_IFACE,
                   "terminate", "usa{sv}", [code, message, {}])


def publish_no_replace(temporary, output):
    """Linux atomic rename without replacing an existing file or symlink."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p,
                       ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(temporary), -100, os.fsencode(output), 1):
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(f"Output already exists: {output}")
        raise OSError(code, os.strerror(code), str(output))


async def stop_process(process):
    if process is None or process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()


async def convert(source: Path, output: Path, image_format: str, job, cancel) -> None:
    """Convert a local image, auto-probing its format, without replacing output.

    Callers must validate the output format with probe_format first. Stage in
    the destination directory for atomic publication. Reject auxiliary files,
    stop the process on cancellation or disconnect, and clean staging on exit.
    """
    if not source.is_file():
        raise ValueError(f"Select an existing local image file: {source}")
    if os.path.lexists(output):
        raise FileExistsError(f"Output already exists: {output}")
    executable = qemu_command()
    staging = Path(tempfile.mkdtemp(
        prefix=f".{output.name}.", suffix=".part", dir=output.parent))
    temporary = staging / output.name
    process = None
    try:
        environment = dict(os.environ, LC_ALL="C")
        process = await asyncio.create_subprocess_exec(
            executable, "convert", "-p", "-O", image_format,
            str(source), str(temporary), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, env=environment)

        async def consume():
            pending = b""
            diagnostic = b""
            last_percent = -1
            while chunk := await process.stdout.read(4096):
                diagnostic = (diagnostic + chunk)[-16384:]
                pending += chunk
                matches = list(PROGRESS.finditer(pending))
                if matches:
                    percent = min(99, max(0, int(float(matches[-1].group(1)))))
                    if percent != last_percent:
                        await job.update(percent)
                        last_percent = percent
                    pending = pending[matches[-1].end():]
                pending = pending[-256:]
            code = await process.wait()
            if code:
                detail = PROGRESS.sub(b"", diagnostic).decode("utf-8", "replace").strip()
                raise RuntimeError(detail or f"qemu-img exited with status {code}.")

        consumer = asyncio.create_task(consume())
        canceled = asyncio.create_task(cancel.wait())
        disconnected = asyncio.create_task(job.bus.wait_for_disconnect())
        try:
            done, _ = await asyncio.wait(
                [consumer, canceled, disconnected], return_when=asyncio.FIRST_COMPLETED)
            if disconnected in done:
                raise RuntimeError("The session D-Bus connection was lost.")
            if cancel.is_set():
                raise asyncio.CancelledError()
            await consumer
            # No awaits between the final cancellation check and publishing.
            if cancel.is_set():
                raise asyncio.CancelledError()
            if set(staging.iterdir()) != {temporary} or not temporary.is_file():
                raise RuntimeError("This conversion did not produce a standalone image.")
            temporary.chmod(0o600)
            publish_no_replace(temporary, output)
        finally:
            await stop_process(process)
            for task in (consumer, canceled, disconnected):
                task.cancel()
            await asyncio.gather(consumer, canceled, disconnected, return_exceptions=True)
        await job.update(100)
    finally:
        await stop_process(process)
        shutil.rmtree(staging)


def show_error(message):
    """Report setup or job-service failures on stderr and optionally in KDE."""
    print(message, file=sys.stderr)
    if shutil.which("kdialog"):
        subprocess.run(["kdialog", "--title", APP_NAME, "--error", message],
                       check=False)


async def run(source: str, image_format: str | None, output: str | None,
              choose: bool = False) -> int:
    """Resolve output, create a native job, and convert; return 0, 1, or 130."""
    # Absolute path, but preserve symlink names when choosing the output name.
    source = Path(os.path.abspath(os.path.expanduser(source)))
    bus = None
    job = None
    cancel = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, cancel.set)
    try:
        if not source.is_file():
            raise ValueError(f"Select an existing local image file: {source}")
        if choose:
            selection = await asyncio.to_thread(choose_output, source)
            if selection is None:
                return 0
            image_format, output = selection
        else:
            if not image_format or not await asyncio.to_thread(
                    probe_format, qemu_command(), image_format):
                raise ValueError(f"Unsupported standalone output format: {image_format}")
            output = (Path(os.path.abspath(os.path.expanduser(output))) if output
                      else default_output(source, image_format))
        if cancel.is_set():
            raise asyncio.CancelledError()
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        job = await JobView.create(bus, source, output, cancel, image_format)
        await convert(source, output, image_format, job, cancel)
        await job.finish()
        return 0
    except asyncio.CancelledError:
        if job:
            try:
                await job.finish(CANCELED, "Conversion canceled.")
            except Exception:
                pass
        return 130
    except Exception as error:
        message = str(error)
        if job:
            try:
                await job.finish(ERROR, message)
            except Exception:
                show_error(message)
        else:
            show_error(message)
        return 1
    finally:
        if bus:
            bus.disconnect()


def main():
    """CLI: --list-formats, or SOURCE with -O FORMAT [-o OUTPUT] / --choose."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="Local image file; format is auto-detected")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("-O", "--output-format", help="QEMU output format, e.g. qcow2 or raw")
    mode.add_argument("--choose", action="store_true", help="Choose format and destination in KDE")
    mode.add_argument("--list-formats", action="store_true", help="List standalone writable formats")
    parser.add_argument("-o", "--output", help="Destination filename; defaults beside source")
    arguments = parser.parse_args()
    if arguments.list_formats:
        if arguments.source or arguments.output:
            parser.error("--list-formats does not accept a source or output")
        try:
            print("\n".join(supported_formats()))
            return 0
        except Exception as error:
            print(error, file=sys.stderr)
            return 1
    if not arguments.source or not (arguments.choose or arguments.output_format):
        parser.error("provide SOURCE and either -O FORMAT or --choose")
    if arguments.choose and arguments.output:
        parser.error("--choose selects its own destination; omit --output")
    return asyncio.run(run(arguments.source, arguments.output_format,
                           arguments.output, arguments.choose))


if __name__ == "__main__":
    sys.exit(main())
