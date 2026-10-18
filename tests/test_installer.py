"""Installer lifecycle tests; installs stay inside temporary directories.

Full installation tests require QEMU_CONVERTER_TEST_WHEELS pointing to a
directory containing the dbus-next 0.2.3 wheel. They use real venv/pip offline.
Argument validation and dependency-free uninstall checks always run.
"""

import configparser
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"
WHEELS = os.environ.get("QEMU_CONVERTER_TEST_WHEELS")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="qemu install % ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.data = self.root / "user"
        self.prefix = self.root / "system"
        self.environment = dict(os.environ, XDG_DATA_HOME=str(self.data))

    def run_installer(self, *arguments, environment=None, expected=0):
        result = subprocess.run(
            ["/usr/bin/bash", str(INSTALLER), *map(str, arguments)],
            capture_output=True, text=True, env=environment or self.environment)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_help_and_invalid_arguments(self):
        self.assertIn("--uninstall", self.run_installer("--help").stdout)
        for arguments in (("--unknown",), ("--prefix",), ("--prefix", "relative"),
                          ("--prefix", "/"), ("--prefix", str(self.prefix))):
            with self.subTest(arguments=arguments):
                self.run_installer(*arguments, expected=2)
        self.assertFalse(self.data.exists())
        self.assertFalse(self.prefix.exists())

    def test_uninstall_needs_no_python_qemu_or_dialog(self):
        commands = self.root / "commands"
        commands.mkdir()
        for command in ("dirname", "rm"):
            (commands / command).symlink_to(shutil.which(command))
        environment = dict(self.environment, PATH=str(commands))
        for scope in ((), ("--system", "--prefix", self.prefix)):
            self.run_installer(*scope, "--uninstall", environment=environment)

    @unittest.skipUnless(WHEELS, "set QEMU_CONVERTER_TEST_WHEELS for offline install tests")
    def test_user_and_system_install_uninstall_are_independent(self):
        environment = dict(self.environment, PIP_NO_INDEX="1", PIP_FIND_LINKS=WHEELS,
                           PIP_DISABLE_PIP_VERSION_CHECK="1")
        # Exercise both real layouts with restrictive calling permissions.
        previous_umask = os.umask(0o077)
        try:
            self.run_installer(environment=environment)
            self.run_installer("--system", "--prefix", self.prefix, environment=environment)
        finally:
            os.umask(previous_umask)
        for data, app in ((self.data, self.data / "qemu-image-converter"),
                          (self.prefix / "share", self.prefix / "lib/qemu-image-converter")):
            menu = configparser.ConfigParser(interpolation=None)
            menu.read(data / "kio/servicemenus/qemu-image-converter.desktop")
            actions = menu["Desktop Entry"]["Actions"].strip(";").split(";")
            self.assertEqual(actions[-2:], ["_SEPARATOR_", "choose"])
            self.assertEqual(menu["Desktop Action choose"]["Name"], "Convert to...")
            self.assertIn(str(app).replace("%", "%%"), menu["Desktop Action choose"]["Exec"])
            subprocess.run([str(app / "venv/bin/python"), str(app / "qemu-image-converter.py"),
                            "--list-formats"], check=True, capture_output=True)
            if data == self.prefix / "share":
                self.assertEqual(app.stat().st_mode & 0o777, 0o755)
                self.assertEqual((app / "venv").stat().st_mode & 0o777, 0o755)
                self.assertEqual((data / "applications/io.controlthings.qemu-image-converter.desktop").stat().st_mode & 0o777, 0o644)
        sentinel = self.data / "unrelated.txt"
        sentinel.write_text("keep")
        self.run_installer("--system", "--prefix", self.prefix, "--uninstall")
        self.assertFalse((self.prefix / "lib/qemu-image-converter").exists())
        self.assertFalse((self.prefix / "share/kio/servicemenus/qemu-image-converter.desktop").exists())
        self.assertFalse((self.prefix / "share/applications/io.controlthings.qemu-image-converter.desktop").exists())
        self.assertTrue((self.data / "qemu-image-converter").exists())
        self.run_installer("--uninstall")
        self.run_installer("--uninstall")  # Repeating removal is harmless.
        self.assertFalse((self.data / "qemu-image-converter").exists())
        self.assertFalse((self.data / "kio/servicemenus/qemu-image-converter.desktop").exists())
        self.assertFalse((self.data / "applications/io.controlthings.qemu-image-converter.desktop").exists())
        self.assertEqual(sentinel.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
