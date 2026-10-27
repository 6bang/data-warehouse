"""Exercise init in a throwaway release tree without starting services or npm."""
import base64
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = ["DJANGO_SECRET_KEY", "INTEGRATION_ENCRYPTION_KEY", "ADMIN_PASSWORD", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"]


class DevLauncherTests(unittest.TestCase):
    def prepare(self, root):
        (root / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/dev.py", root / "scripts/dev.py")
        shutil.copyfile(ROOT / ".env.example", root / ".env.example")

    def initialize(self, root):
        return subprocess.run([sys.executable, "scripts/dev.py", "init"], cwd=root, capture_output=True, text=True, check=False)

    def test_init_unique_private_credentials_without_output_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            roots = [Path(first), Path(second)]
            values = []
            for root in roots:
                self.prepare(root)
                result = self.initialize(root)
                self.assertEqual(result.returncode, 0, result.stderr)
                destination = root / ".env"
                content = destination.read_bytes()
                data = dict(line.split("=", 1) for line in content.decode().splitlines() if line and not line.startswith("#"))
                values.append(data)
                for key in SECRET_KEYS:
                    self.assertGreaterEqual(len(data[key]), 32, key)
                    self.assertNotIn(data[key], result.stdout + result.stderr)
                self.assertEqual(len(base64.urlsafe_b64decode(data["INTEGRATION_ENCRYPTION_KEY"])), 32)
                self.assertGreaterEqual(len(data["DJANGO_SECRET_KEY"]), 50)
                self.assertEqual(data["DB_ENGINE"], "sqlite")
                self.assertEqual(data["AI_API_BASE_URL"], "")
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
                repeated = self.initialize(root)
                self.assertEqual(repeated.returncode, 0, repeated.stderr)
                self.assertEqual(destination.read_bytes(), content)
                for key in SECRET_KEYS:
                    self.assertNotIn(data[key], repeated.stdout + repeated.stderr)
                self.assertFalse((root / "frontend").exists())
                self.assertFalse((root / ".venv").exists())
            for key in SECRET_KEYS:
                self.assertNotEqual(values[0][key], values[1][key], key)

    def test_generated_key_encrypts_and_decrypts_if_backend_dependency_installed(self):
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            self.skipTest("Install backend requirements for Fernet round-trip validation")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare(root)
            result = self.initialize(root)
            self.assertEqual(result.returncode, 0)
            data = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines() if line and not line.startswith("#"))
            fernet = Fernet(data["INTEGRATION_ENCRYPTION_KEY"].encode())
            self.assertEqual(fernet.decrypt(fernet.encrypt(b"fixture-only")), b"fixture-only")


if __name__ == "__main__":
    unittest.main()
