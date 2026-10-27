"""Synthetic checks for the release scanner itself.

Every sensitive-looking value is generated at run time and written only to a temporary
directory; nothing real is stored in this file.
"""
import base64
import json
from pathlib import Path
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import unittest

from privacy_audit import FIXTURE_MARKER, audit

SCANNER = Path(__file__).resolve().with_name("privacy_audit.py")
ALNUM = string.ascii_letters + string.digits


def rand(length):
    """Random token with upper case, lower case and digits, like real credentials.

    Values that happen to contain fixture wording (for example "test") are redrawn so the
    heuristic rules always see them as real-looking secrets.
    """
    while True:
        value = "".join(secrets.choice(ALNUM) for _ in range(length))
        if any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value) \
                and not FIXTURE_MARKER.search(value):
            return value


def assign(name, value):
    return "{} = '{}'".format(name, value)


def b64url(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def without_catalog(findings):
    return [row for row in findings if "catalog" not in row[2]]


class PrivacyAuditTests(unittest.TestCase):
    def test_locations_only_for_private_artifacts_and_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env").write_text("SENTINEL_PRIVATE_CONTENT=fixture-only")
            (root / "sample.txt").write_text("/".join(["", "Users", "fixture-user", "project", ""]))
            (root / "node_modules").mkdir()
            findings = audit(root)
            self.assertIn((".env", 0, "private-or-generated-file"), findings)
            self.assertIn(("sample.txt", 1, "personal-absolute-path"), findings)
            self.assertIn(("node_modules", 0, "generated-or-private-directory"), findings)
            self.assertNotIn("SENTINEL_PRIVATE_CONTENT", repr(findings))

    def test_common_live_token_prefixes_report_no_token_material(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for prefix in ["mc", "sk"]:
                token = prefix + "_live_" + "FixtureOnly" * 3
                (root / "credential.txt").write_text(token)
                findings = audit(root)
                self.assertIn(("credential.txt", 1, "provider-secret-format"), findings)
                self.assertNotIn(token, repr(findings))

    def test_svg_external_and_active_content_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "safe.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="5" /></svg>')
            (root / "unsafe.svg").write_text('<svg><image href="https://example.invalid/a.png" /></svg>')
            self.assertIn(("unsafe.svg", 0, "svg-active-or-external-content"), audit(root))
            self.assertFalse(any(row[0] == "safe.svg" for row in audit(root)))

    def test_identifiers_contacts_and_hidden_secrets_are_reported_without_values(self):
        tenant = "t" + rand(8).lower()
        base_token, table_id = rand(27), "tbl" + rand(14)
        open_id, tenant_key = "ou_" + secrets.token_hex(16), secrets.token_hex(8)
        phone = "1" + secrets.choice("3456789") + "".join(secrets.choice(string.digits) for _ in range(9))
        email = rand(6).lower() + "@" + rand(8).lower() + ".cn"
        public_ip = ".".join(["11"] + [str(secrets.randbelow(200) + 1) for _ in range(3)])
        jwt = ".".join([b64url({"alg": "HS256", "typ": "JWT"}), b64url({"sub": rand(10)}), rand(32)])
        bearer, db_password, db_host = rand(32), rand(16), rand(8).lower() + ".cn"
        api_key, opaque, key_tail = rand(24), rand(32), rand(40)
        encoded_key = base64.b64encode("".join(["sk", "-proj-", rand(40)]).encode()).decode()
        store = "".join(["壹贰叁肆", "旗舰店"])
        latin_store = "".join([rand(6), "旗舰店"])
        server_name = ".".join([rand(6).lower(), rand(5).lower(), "vip"])
        volume = "/".join(["", "Volumes", "fixture-drive", "project", ""])
        planted = {
            "feishu.py": [
                f"BASE_URL = 'https://{tenant}.feishu.cn/base/{base_token}?table={table_id}'",
                assign("OWNER", open_id),
                assign("tenant_key", tenant_key),
            ],
            "contacts.md": [f"电话 {phone}", f"邮件 {email}", f"服务器 {public_ip}", store, volume],
            "brand.ts": [assign("const SHOP", latin_store)],
            "site.conf": ["server_name " + server_name + ";"],
            "tokens.py": [
                assign("SESSION", jwt),
                "HEADERS = {'Authorization': '" + " ".join(["Bearer", bearer]) + "'}",
                assign("DATABASE", "mysql://root:" + db_password + "@" + db_host + ":3306/shop"),
                assign("api_key", api_key),
                assign("OPAQUE", opaque),
                assign("ENCODED", encoded_key),
                "JOINED = " + " + ".join(["'sk-'", "'proj-'", "'" + key_tail + "'"]),
            ],
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, lines in planted.items():
                (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            findings = audit(root)
            result = subprocess.run([sys.executable, str(SCANNER), str(root)], capture_output=True, text=True)
        found = {category for _, _, category in findings}
        expected = {
            "feishu-document-token", "feishu-table-or-view-id", "non-public-url-host", "feishu-user-or-chat-id",
            "feishu-tenant-key", "cn-mobile-number", "email-address", "public-ip-address",
            "store-or-company-name-review", "personal-absolute-path", "jwt-token", "bearer-token-literal",
            "credential-in-url", "credential-assignment", "high-entropy-literal", "encoded-provider-secret-format",
            "split-literal-provider-secret-format", "non-public-host-name",
        }
        self.assertTrue(expected <= found, sorted(expected - found))
        self.assertIn(("brand.ts", 1, "store-or-company-name-review"), findings)
        self.assertEqual(result.returncode, 1)
        for value in [base_token, table_id, open_id, tenant_key, phone, email, public_ip, jwt, bearer, db_password,
                      db_host, api_key, opaque, encoded_key, key_tail, "壹贰叁肆", tenant, latin_store, server_name]:
            self.assertNotIn(value, repr(findings))
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_reserved_examples_and_fixture_wording_are_not_reported(self):
        lines = [
            assign("EMAIL", "operator@example.com"),
            assign("LOCAL", "http://127.0.0.1:8000/api/"),
            "SSRF = ['10.0.0.1', '169.254.169.254']",
            assign("IMAGE", "https://user:password@cdn.example.test/a.jpg"),
            assign("HEADER", "Bearer TEST_ONLY_NOT_A_REAL_TOKEN"),
            assign("password", "fixture-strong-pass-123"),
            assign("SHOP", "演示旗舰店"),
            assign("HINT", "https://xxx.feishu.cn/base/...?table=tbl..."),
            assign("API", "https://open.feishu.cn/open-apis/authen/v1/user_info"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "ok.py").write_text("\n".join(lines + ["shop = row.shop  # attribute access, not a host"]) + "\n",
                                        encoding="utf-8")
            (root / "notes.md").write_text("参考 opensource.org、example.com 与 localhost。\n", encoding="utf-8")
            (root / "site.conf").write_text("server_name localhost;\nproxy_pass http://backend:8000;\n", encoding="utf-8")
            self.assertEqual(without_catalog(audit(root)), [])

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_git_mode_checks_exactly_what_git_would_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(".env\n*.sqlite3\n")
            (root / ".env").write_text("ADMIN_PASSWORD=" + rand(20) + "\n")
            (root / "ignored.sqlite3").write_bytes(b"")
            (root / "forced.sqlite3").write_bytes(b"")
            subprocess.run(["git", "-C", str(root), "add", "-f", "forced.sqlite3"], check=True)
            (root / "notes.md").write_text("联系 " + rand(6).lower() + "@" + rand(8).lower() + ".cn\n", encoding="utf-8")
            findings = audit(root)
        paths = {path for path, _, _ in findings}
        self.assertFalse({".env", "ignored.sqlite3", ".git"} & paths)
        self.assertIn(("forced.sqlite3", 0, "private-or-generated-file"), findings)
        self.assertIn(("notes.md", 1, "email-address"), findings)

    def test_private_denylist_lives_outside_repository_and_is_never_echoed(self):
        term = "Qz" + rand(6)
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            root = Path(folder)
            (root / "doc.md").write_text("示例：" + " ".join(term.upper()) + "\n", encoding="utf-8")
            denylist = Path(outside) / "private-terms.txt"
            denylist.write_text("# one private term per line\n" + term + "\n", encoding="utf-8")
            findings = audit(root, denylist_path=denylist)
            self.assertIn(("doc.md", 1, "private-denylist-term"), findings)
            self.assertNotIn(term.lower(), repr(findings).lower())
            result = subprocess.run([sys.executable, str(SCANNER), str(root), "--denylist", str(denylist)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(term.lower(), (result.stdout + result.stderr).lower())
            inside = root / "terms.txt"
            inside.write_text(term + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                audit(root, denylist_path=inside)
            refused = subprocess.run([sys.executable, str(SCANNER), str(root), "--denylist", str(inside)],
                                     capture_output=True, text=True)
            self.assertEqual(refused.returncode, 2)

    def test_lockfile_must_resolve_from_public_npm_registry(self):
        lock = {"packages": {
            "node_modules/a": {"resolved": "https://registry.npmjs.org/a/-/a-1.0.0.tgz"},
            "node_modules/b": {"resolved": "https://npm.internal-mirror.invalid/b/-/b-1.0.0.tgz"},
        }}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "package-lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
            found = [row for row in audit(root) if row[0] == "package-lock.json"]
        self.assertEqual([category for _, _, category in found], ["lockfile-non-public-registry"])


if __name__ == "__main__":
    unittest.main()
