#!/usr/bin/env python3
"""Convert one local VMDK, reporting progress to KDE Plasma 6's JobView service.

Requires Python 3.10–3.14, dbus-next, qemu-img and a running Plasma session.
No Qt bindings, root access or Dolphin plugin are needed.
"""

import argparse
import asyncio
import ctypes
import errno
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
    async def create(cls, bus, source, output, cancel):
        hints = {
            "immediate": Variant("b", True),
            "title": Variant("s", "Converting VMDK to qcow2"),
            "descriptionLabel1": Variant("s", "Source"),
            "descriptionValue1": Variant("s", str(source)),
            "descriptionLabel2": Variant("s", "Destination"),
            "descriptionValue2": Variant("s", str(output)),
            "destUrl": Variant("s", output.as_uri()),
            "percent": Variant("u", 0),
        }
        reply = await call(bus, SERVICE, "/JobViewServer", SERVER_IFACE,
                           "requestView", "sia{sv}",
                           ["io.controlthings.vmdk-to-qcow2", 1, hints])
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


async def convert(source, output, job, cancel):
    if source.suffix.lower() != ".vmdk" or not source.is_file():
        raise ValueError(f"Select an existing .vmdk file: {source}")
    if os.path.lexists(output):
        raise FileExistsError(f"Output already exists: {output}")
    executable = shutil.which("qemu-img")
    if not executable:
        raise RuntimeError("qemu-img was not found in PATH. Install qemu-img first.")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".part", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    process = None
    try:
        environment = dict(os.environ, LC_ALL="C")
        process = await asyncio.create_subprocess_exec(
            executable, "convert", "-p", "-f", "vmdk", "-O", "qcow2",
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
            publish_no_replace(temporary, output)
        finally:
            await stop_process(process)
            for task in (consumer, canceled, disconnected):
                task.cancel()
            await asyncio.gather(consumer, canceled, disconnected, return_exceptions=True)
        await job.update(100)
    finally:
        await stop_process(process)
        temporary.unlink(missing_ok=True)


def show_error(message):
    """Fallback only when the native job service itself is unavailable."""
    print(message, file=sys.stderr)
    if shutil.which("kdialog"):
        subprocess.run(["kdialog", "--title", "Convert to qcow2", "--error", message],
                       check=False)


async def run(source):
    # Absolute path, but preserve symlink names when choosing the output name.
    source = Path(os.path.abspath(os.path.expanduser(source)))
    output = source.with_suffix(".qcow2")
    bus = None
    job = None
    cancel = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, cancel.set)
    try:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        job = await JobView.create(bus, source, output, cancel)
        await convert(source, output, job, cancel)
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
            show_error("Cannot start native KDE conversion job: " + message)
        return 1
    finally:
        if bus:
            bus.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Local .vmdk file to convert")
    arguments = parser.parse_args()
    return asyncio.run(run(arguments.source))


if __name__ == "__main__":
    sys.exit(main())
