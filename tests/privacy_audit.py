#!/usr/bin/env python3
"""Offline privacy checks for the files you are about to publish.

Prints only "path:line: category" and never the matched text. Inside a Git work tree it checks
exactly what Git would publish (tracked files plus untracked files that are not ignored);
otherwise it walks a clean release directory.

This is a guardrail, not proof that nothing private remains. Business names (brands, shops,
companies, people) can only be caught reliably with your own list: keep a plain-text denylist
OUTSIDE the repository and pass it with --denylist (or PRIVACY_DENYLIST).
"""
from pathlib import Path
import argparse
import base64
import binascii
import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import urllib.parse

FORBIDDEN_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "uploads",
                  "media", "screenshots", "backups"}
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".log", ".pyc", ".pem", ".key", ".p12", ".pfx", ".har",
                      ".sql", ".dump", ".bak"}
REVIEW_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".xlsx", ".xls", ".docx", ".pptx",
                   ".zip", ".gz", ".7z"}
LOCKFILES = {"package-lock.json"}

# Hosts allowed in URLs and e-mail domains: reserved example names, single-label service names
# (docker "backend"), and public technical services the code calls only after a user configures
# them. Never add your own business, tenant or server domains here.
PUBLIC_HOSTS = {"open.feishu.cn", "accounts.feishu.cn", "api.openai.com", "api.deepseek.com", "item.taobao.com",
                "item.jd.com", "mobile.yangkeduo.com", "opensource.org", "www.w3.org", "registry.npmjs.org"}
PLACEHOLDER_TENANTS = {"example", "xxx", "your-tenant"}
# Public address used by an SSRF regression test as "an allowed public endpoint" (historic example.com).
TEST_PUBLIC_IPS = {"93.184.216.34"}
# Obvious fixture wording; only relaxes the heuristic rules, never the fixed secret formats.
FIXTURE_MARKER = re.compile(r"(?i)test|fake|fixture|example|demo|sentinel|placeholder|dummy|sample|changeme|"
                            r"not[-_]?a[-_]?real|invalid|secret-pass|admin-pass")
FICTION_MARKERS = ("演示", "示例", "测试", "虚构", "样例", "模拟", "某某", "示范")

FORMAT_RULES = {
    "personal-absolute-path": re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/|/Volume[s]/[^/\s'\"`]+/|[A-Za-z]:\\Users\\[^\\]+\\"),
    "private-key-material": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"),
    "provider-secret-format": re.compile(
        r"\b(?:AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
        r"sk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,}|(?:mc|sk|rk)_live_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|"
        r"AIza[0-9A-Za-z_-]{35}|glpat-[A-Za-z0-9_-]{20,})"),
    "feishu-app-identity": re.compile(r"\bcli_[a-z0-9]{12,}\b"),
    "feishu-user-or-chat-id": re.compile(r"\b(?:ou|on|oc|om|od)_[0-9a-f]{32}\b"),
    "feishu-document-token": re.compile(
        r"(?:feishu\.cn|larksuite\.com|larkoffice\.com)/(?:base|wiki|docx|docs|sheets|bitable|file|mindnotes|minutes)/"
        r"[A-Za-z0-9]{20,}"),
    "jwt-token": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
}
FEISHU_TABLE_ID = re.compile(r"\b(?:tbl|vew|fld|rec)([A-Za-z0-9]{12,})\b")
TENANT_KEY = re.compile(r"(?i)tenant[_-]?keys?[\"']?\s*[:=]\s*[\"']?(?:[0-9a-f]{16}[\s,]*)+")
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b[a-z0-9_]*?(?:password|passwd|secret|api_?key|access_?key|private_?key|auth_?token|access_?token|"
    r"refresh_?token|client_?secret|app_?secret|session_?id|cookie)\b[\"']?\s*[:=]\s*[\"'`]([!#-&(-_a-~]{8,})[\"'`]")
BEARER = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{16,})")
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://([^\s/?#\"'`<>)\],;]+)", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
CN_MOBILE = re.compile(r"(?<![\d])(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
CN_ID = re.compile(r"(?<![0-9A-Za-z])\d{17}[0-9Xx](?![0-9A-Za-z])")
QUOTED = re.compile(r"[\"'`]([A-Za-z0-9+/_=.\-]{20,200})[\"'`]")
BASE64_RUN = re.compile(r"(?<![A-Za-z0-9+/_=-])[A-Za-z0-9+/_-]{24,}={0,2}")
JOINED_LITERALS = re.compile(r"[\"']\s*\+\s*[\"']|(?<=[\"'])[ \t]+(?=[\"'])")
STORE_OR_COMPANY = re.compile(r"([一-鿿A-Za-z0-9·&]{2,20})(旗舰店|专营店|专卖店|企业店|官方店|工厂店|股份有限公司|有限公司|制衣厂|服饰厂)")
# Bare host names (no scheme) are only checked in config, script and document files, where they
# usually mean a real server or domain (nginx server_name, ssh targets, ALLOWED_HOSTS ...).
CONFIG_SUFFIXES = {".conf", ".cron", ".sh", ".bash", ".zsh", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".service",
                   ".md", ".txt"}
CONFIG_NAMES = {"Dockerfile", "Caddyfile", "Procfile", "nginx.conf"}
BARE_HOST = re.compile(r"(?<![\w@./:-])((?:[a-z0-9-]+\.)+(?:com|cn|net|org|vip|io|co|top|xyz|shop|site|cloud|tech|info|"
                       r"biz|me|cc|tv|app|dev|ai|hk|tw|jp|us|uk|de|fr|sg|club|online|store|work|ltd|group|link))(?![\w.-])",
                       re.I)
LOCK_RESOLVED = re.compile(r"\"resolved\"\s*:\s*\"([^\"]+)\"")
DENY_SEPARATORS = re.compile(r"[\s\-_./·・,，、|:：'\"`]+")


def allowed_ip(text):
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return True  # not an address (for example a version string with an octet above 255)
    return ip.is_loopback or ip.is_unspecified or ip.is_link_local or ip.is_private or text in TEST_PUBLIC_IPS


def allowed_host(host):
    host = host.lower().rsplit("@", 1)[-1]
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    host = host.rstrip(".")
    if not host or any(mark in host for mark in "{}$%<>"):
        return True  # empty or templated host, e.g. 127.0.0.1:{port}
    if "." not in host or host in PUBLIC_HOSTS:
        return True  # single-label service names such as docker "backend"
    if IPV4.fullmatch(host) or ":" in host:
        return allowed_ip(host)
    if host.endswith((".example", ".invalid", ".test", ".localhost")):
        return True
    if re.fullmatch(r"(?:[a-z0-9-]+\.)*example\.(?:com|net|org)", host):
        return True
    return host.split(".")[0] in PLACEHOLDER_TENANTS and host.endswith((".feishu.cn", ".larksuite.com"))


def entropy(text):
    counts = {char: text.count(char) for char in set(text)}
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def valid_cn_id(text):
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    if "10X98765432"[sum(int(c) * w for c, w in zip(text[:17], weights)) % 11] != text[17].upper():
        return False
    year, month, day = int(text[6:10]), int(text[10:12]), int(text[12:14])
    return 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31


def secret_like(value):
    classes = sum([any(c.islower() for c in value), any(c.isupper() for c in value), any(c.isdigit() for c in value)])
    return classes == 3 and entropy(value) >= 3.5 and not FIXTURE_MARKER.search(value)


def compact(text):
    return DENY_SEPARATORS.sub("", text).lower()


def decoded_variants(line):
    """Text hidden by URL encoding, unicode escapes or base64 within one line."""
    variants = []
    if "%" in line:
        variants.append(urllib.parse.unquote(line))
    if "\\u" in line or "\\x" in line:
        variants.append(re.sub(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})",
                               lambda m: chr(int(m.group(1) or m.group(2), 16)), line))
    for match in BASE64_RUN.finditer(line):
        token = match.group(0)
        if token.startswith(("sha512-", "sha384-", "sha256-", "sha1-")):
            continue
        for decode in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                text = decode(token + "=" * (-len(token) % 4)).decode("utf-8")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                continue
            if text and sum(ch.isprintable() for ch in text) / len(text) > 0.9:
                variants.append(text)
                break
    return variants


def line_findings(line, *, lockfile, svg, denylist):
    found = []
    for category, pattern in FORMAT_RULES.items():
        if pattern.search(line):
            found.append(category)
    for match in FEISHU_TABLE_ID.finditer(line):
        suffix = match.group(1)
        if any(c.isupper() for c in suffix) and (any(c.islower() for c in suffix) or any(c.isdigit() for c in suffix)):
            found.append("feishu-table-or-view-id")
    if TENANT_KEY.search(line):
        found.append("feishu-tenant-key")
    for match in URL.finditer(line):
        netloc = match.group(1)
        if "@" in netloc and not allowed_host(netloc.rsplit("@", 1)[-1]):
            found.append("credential-in-url")
        elif not lockfile and not allowed_host(netloc):
            found.append("non-public-url-host")
    if not lockfile:
        for match in EMAIL.finditer(line):
            if not allowed_host(match.group(1)):
                found.append("email-address")
        for match in IPV4.finditer(line):
            if not allowed_ip(match.group(0)):
                found.append("public-ip-address")
        for match in CREDENTIAL_ASSIGNMENT.finditer(line):
            if not FIXTURE_MARKER.search(match.group(1)):
                found.append("credential-assignment")
        for match in BEARER.finditer(line):
            if not FIXTURE_MARKER.search(match.group(1)):
                found.append("bearer-token-literal")
        if not svg:
            for match in QUOTED.finditer(line):
                if secret_like(match.group(1)):
                    found.append("high-entropy-literal")
    if CN_MOBILE.search(line):
        found.append("cn-mobile-number")
    if any(valid_cn_id(match.group(0)) for match in CN_ID.finditer(line)):
        found.append("cn-id-number")
    for match in STORE_OR_COMPANY.finditer(line):
        name = match.group(1)[:-2] if match.group(1).endswith("股份") else match.group(1)
        if len(name) >= 2 and not any(marker in name for marker in FICTION_MARKERS) and not FIXTURE_MARKER.search(name):
            found.append("store-or-company-name-review")
    if denylist:
        flat = compact(line)
        if any(term in flat for term in denylist):
            found.append("private-denylist-term")
    return found


def scan_text(relative, content, denylist):
    findings = []
    name = Path(relative).name
    lockfile, svg = name in LOCKFILES, relative.endswith(".svg")
    config = Path(relative).suffix.lower() in CONFIG_SUFFIXES or name in CONFIG_NAMES or name.startswith(".env")
    for number, line in enumerate(content.splitlines(), 1):
        categories = set(line_findings(line, lockfile=lockfile, svg=svg, denylist=denylist))
        if config and any(not allowed_host(match.group(1)) for match in BARE_HOST.finditer(line)):
            categories.add("non-public-host-name")
        joined = JOINED_LITERALS.sub("", line)
        if joined != line:
            hidden = set(line_findings(joined, lockfile=lockfile, svg=svg, denylist=denylist)) - categories
            categories |= {"split-literal-" + category for category in hidden}
        if not lockfile:
            for variant in decoded_variants(line):
                hidden = set(line_findings(variant, lockfile=False, svg=svg, denylist=denylist)) - categories
                categories |= {"encoded-" + category for category in hidden if category != "high-entropy-literal"}
        if name.startswith(".env"):
            key, _, value = line.partition("=")
            if re.search(r"(?i)secret|password|token|key", key) and value.strip() and not line.lstrip().startswith("#"):
                categories.add("env-secret-value")
        if lockfile:
            for match in LOCK_RESOLVED.finditer(line):
                if not match.group(1).startswith("https://registry.npmjs.org/"):
                    categories.add("lockfile-non-public-registry")
        findings.extend((relative, number, category) for category in sorted(categories))
    if svg and re.search(r"<\s*(?:script|foreignObject|image)\b|\b(?:href|onload|onclick)\s*=|url\s*\(", content, re.I):
        findings.append((relative, 0, "svg-active-or-external-content"))
    return findings


def git_files(root):
    """Files Git would publish, or None when root is not a Git work tree."""
    if not (root / ".git").exists():
        return None
    try:
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    paths = sorted({part for part in listed.decode("utf-8", "surrogateescape").split("\0") if part})
    return [root / part for part in paths if (root / part).exists() or (root / part).is_symlink()]


def load_denylist(path, root):
    denylist_path = Path(path).expanduser().resolve()
    if denylist_path == root or root in denylist_path.parents:
        raise ValueError("The private denylist must live outside the repository so it is never published.")
    terms = []
    for raw in denylist_path.read_text(encoding="utf-8").splitlines():
        term = compact(raw.strip())
        if raw.strip() and not raw.strip().startswith("#") and len(term) >= 2:
            terms.append(term)
    return terms


def audit(root, denylist_path=None, use_git=True):
    root = Path(root).resolve()
    denylist = load_denylist(denylist_path, root) if denylist_path else []
    findings = []

    def report(path, category, line=0):
        findings.append((path.relative_to(root).as_posix(), line, category))

    def check_file(path):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            report(path, "symlink-not-release-content")
            return
        if any(part in FORBIDDEN_DIRS for part in Path(relative).parts[:-1]):
            report(path, "generated-or-private-directory")
        if path.name == ".DS_Store" or (path.name.startswith(".env") and path.name != ".env.example") \
                or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            report(path, "private-or-generated-file")
        if path.suffix.lower() in REVIEW_SUFFIXES:
            report(path, "image-document-or-archive-needs-manual-review")
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            report(path, "binary-needs-manual-review")
            return
        findings.extend(scan_text(relative, content, denylist))

    def visit(directory):
        for path in sorted(directory.iterdir()):
            if path.is_symlink():
                report(path, "symlink-not-release-content")
            elif path.is_dir():
                if path.name in FORBIDDEN_DIRS:
                    report(path, "generated-or-private-directory")
                else:
                    visit(path)
            else:
                check_file(path)

    listed = git_files(root) if use_git else None
    if listed is None:
        visit(root)
    else:
        for path in listed:
            check_file(path)

    catalog = root / "frontend/public/demo-products.json"
    if catalog.exists():
        try:
            products = json.loads(catalog.read_text(encoding="utf-8"))["products"]
            if len(products) != 60:
                report(catalog, "catalog-must-have-60-fictional-products")
            for row in products:
                if not re.fullmatch(r"/demo-assets/product-(?:00[1-9]|0[1-5][0-9]|060)\.svg", row.get("imageUrl", "")):
                    report(catalog, "catalog-image-not-local-allowlist")
                if row.get("createdAt") is not None:
                    report(catalog, "catalog-real-timestamp")
        except (ValueError, TypeError, KeyError):
            report(catalog, "malformed-demo-catalog")
    else:
        report(catalog, "missing-demo-catalog")
    return sorted(set(findings))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--denylist", default=os.environ.get("PRIVACY_DENYLIST"),
                        help="private term list kept OUTSIDE the repository (one term per line)")
    parser.add_argument("--no-git", action="store_true", help="walk every file even inside a Git work tree")
    args = parser.parse_args()
    try:
        results = audit(args.root, args.denylist, use_git=not args.no_git)
    except (ValueError, OSError) as error:
        print(f"Privacy audit could not run: {error}", file=sys.stderr)
        sys.exit(2)
    for path, line, category in results:
        print(f"{path}:{line}: {category}")
    mode = "git" if not args.no_git and git_files(Path(args.root).resolve()) is not None else "tree"
    print(f"Privacy audit ({mode} mode, denylist {'on' if args.denylist else 'off'}): "
          f"{len(results)} finding(s); no matched values printed.")
    sys.exit(bool(results))
