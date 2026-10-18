"""Regression checks using real QEMU images; no desktop session is required.

Run with the installed private Python: python -m unittest discover -s tests -v.
"""

import asyncio
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "converter", Path(__file__).resolve().parents[1] / "qemu-image-converter.py")
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


class Bus:
    async def wait_for_disconnect(self):
        await asyncio.Future()


class Job:
    def __init__(self, callback=None):
        self.bus = Bus()
        self.percentages = []
        self.callback = callback

    async def update(self, percent):
        self.percentages.append(percent)
        if self.callback:
            self.callback(percent)


@unittest.skipUnless(shutil.which("qemu-img"), "qemu-img required")
class ConversionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw = self.root / 'Test $disk; "quoted".unknown'
        with self.raw.open("wb") as stream:
            stream.write(bytes(range(256)) * 4096)
            stream.truncate(8 * 1024 * 1024)

    def qemu(self, *arguments):
        return subprocess.run(["qemu-img", *map(str, arguments)],
                              capture_output=True, check=True)

    async def test_common_format_matrix_with_auto_detected_inputs(self):
        for source_format in converter.COMMON_FORMATS:
            source = self.root / (source_format + ".unexpected")
            self.qemu("convert", "-f", "raw", "-O", source_format, self.raw, source)
            original = source.read_bytes()
            for target in converter.COMMON_FORMATS:
                with self.subTest(source=source_format, target=target):
                    output = self.root / (source_format + "-" + target)
                    job = Job()
                    await converter.convert(source, output, target, job, asyncio.Event())
                    self.qemu("compare", "-f", "raw", "-F", target, self.raw, output)
                    self.assertEqual(job.percentages[-1], 100)
                    self.assertFalse(list(self.root.glob(".*.part")))
            self.assertEqual(source.read_bytes(), original)

    async def test_existing_file_and_dangling_symlink_are_preserved(self):
        output = self.root / "existing.qcow2"
        output.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            await converter.convert(self.raw, output, "qcow2", Job(), asyncio.Event())
        self.assertEqual(output.read_bytes(), b"keep")
        output.unlink()
        output.symlink_to(self.root / "missing")
        with self.assertRaises(FileExistsError):
            await converter.convert(self.raw, output, "qcow2", Job(), asyncio.Event())
        self.assertTrue(output.is_symlink())

    async def test_output_created_during_conversion_is_preserved(self):
        output = self.root / "race.qcow2"
        job = Job(lambda percent: output.write_bytes(b"winner"))
        with self.assertRaises(FileExistsError):
            await converter.convert(self.raw, output, "qcow2", job, asyncio.Event())
        self.assertEqual(output.read_bytes(), b"winner")
        self.assertFalse(list(self.root.glob(".*.part")))

    async def test_conversion_error_cleans_staging(self):
        source = self.root / "overlay.qcow2"
        self.qemu("create", "-f", "qcow2", "-F", "raw", "-b", self.raw, source)
        self.raw.unlink()
        output = self.root / "failed.vdi"
        with self.assertRaisesRegex(RuntimeError, "backing|Could not open"):
            await converter.convert(source, output, "vdi", Job(), asyncio.Event())
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".*.part")))

    async def test_cancel_stops_process_and_cleans_staging(self):
        fake = self.root / "slow-qemu"
        fake.write_text('#!/usr/bin/env python3\n'
                        'import sys, time\n'
                        'from pathlib import Path\n'
                        'Path(sys.argv[-1]).write_bytes(b"partial")\n'
                        'print("(1.00/100%)", flush=True)\n'
                        'time.sleep(30)\n')
        fake.chmod(0o755)
        cancel = asyncio.Event()
        job = Job(lambda percent: cancel.set())
        output = self.root / "canceled.qcow2"
        with patch.object(converter, "qemu_command", return_value=str(fake)):
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(
                    converter.convert(self.raw, output, "qcow2", job, cancel), 10)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".*.part")))


@unittest.skipUnless(shutil.which("qemu-img"), "qemu-img required")
class FormatTests(unittest.TestCase):
    def test_discovery_excludes_protocols_read_only_and_secret_formats(self):
        formats = converter.supported_formats()
        self.assertTrue(set(converter.COMMON_FORMATS).issubset(formats))
        self.assertTrue(set(formats).isdisjoint({"file", "http", "bochs", "luks"}))

    def test_default_names(self):
        source = Path("/tmp/My VM.vmdk")
        self.assertEqual(converter.default_output(source, "qcow2"), Path("/tmp/My VM.qcow2"))
        self.assertEqual(converter.default_output(source, "raw"), Path("/tmp/My VM.img"))
        self.assertEqual(converter.default_output(source, "vpc"), Path("/tmp/My VM.vhd"))

    def test_chooser_cancel_and_selection(self):
        with patch.object(converter, "supported_formats", return_value=["raw", "qcow2"]):
            with patch.object(converter, "dialog", return_value=None) as dialog:
                self.assertIsNone(converter.choose_output(Path("/tmp/source.img")))
                self.assertEqual(dialog.call_count, 1)
            with patch.object(converter, "dialog", side_effect=["qcow2", None]):
                self.assertIsNone(converter.choose_output(Path("/tmp/source.img")))
            with patch.object(converter, "dialog", side_effect=["qcow2", "/tmp/chosen.qcow2"]):
                self.assertEqual(converter.choose_output(Path("/tmp/source.img")),
                                 ("qcow2", Path("/tmp/chosen.qcow2")))


if __name__ == "__main__":
    unittest.main()
