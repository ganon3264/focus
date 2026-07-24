#!/usr/bin/env python3
"""Download vendor JS/CSS dependencies from CDN.
Uses Python stdlib only.
Run `./vendor-sync.py` to refresh all vendor files.
"""

import glob
import hashlib
import platform
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR_DIR = ROOT / "static" / "vendor"
BIN_DIR = ROOT / "bin"

# ── Versions ────────────────────────────────────────────────────────────────
HTMX_VERSION = "2.0.10"
ALPINE_VERSION = "3.15.12"
MARKED_VERSION = "18.0.5"
DOMPURIFY_VERSION = "3.4.11"
SORTABLEJS_VERSION = "1.15.7"
CROPPERJS_VERSION = "2.1.1"
IDIOMORPH_VERSION = "0.7.4"
TAILWIND_VERSION = "v4.3.2"

def _is_musl() -> bool:
    if glob.glob("/lib/ld-musl-*"):
        return True
    if Path("/etc/alpine-release").is_file():
        return True
    return False


def _detect_tailwind_platform() -> tuple[str, str]:
    os_map = {"linux": "linux", "darwin": "macos", "win32": "windows"}
    raw_os = os_map.get(sys.platform)
    if not raw_os:
        print(_yellow(f"Warning: unsupported platform {sys.platform!r}, falling back to linux-x64"))
        return "tailwindcss-linux-x64", "bin/tailwindcss-linux-x64"

    machine = platform.machine().lower()
    arch_map = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}
    arch = arch_map.get(machine)
    if not arch:
        print(_yellow(f"Warning: unsupported arch {machine!r}, falling back to linux-x64"))
        return "tailwindcss-linux-x64", "bin/tailwindcss-linux-x64"

    binary = f"tailwindcss-{raw_os}-{arch}"

    # Append .exe on Windows
    if raw_os == "windows":
        binary += ".exe"

    # Armv7 is only available on linux; fall back in case it ever pops up on other OSes
    if machine.startswith("armv7"):
        if raw_os == "linux":
            return f"tailwindcss-linux-armv7", f"bin/tailwindcss-linux-armv7"
        return "tailwindcss-linux-x64", "bin/tailwindcss-linux-x64"

    # Musl variant (Linux only)
    if raw_os == "linux" and _is_musl():
        binary += "-musl"

    return binary, f"bin/{binary}"


TAILWIND_BINARY, TAILWIND_CHECKSUM_KEY = _detect_tailwind_platform()
TAILWIND_URL = (
    f"https://github.com/tailwindlabs/tailwindcss/releases/download/"
    f"{TAILWIND_VERSION}/{TAILWIND_BINARY}"
)
TAILWIND_DEST = BIN_DIR / TAILWIND_BINARY

DOWNLOADS = {
    "htmx2.min.js": (
        f"https://unpkg.com/htmx.org@{HTMX_VERSION}/dist/htmx.min.js",
        f"htmx.org v{HTMX_VERSION}",
    ),
    "alpine.min.js": (
        f"https://unpkg.com/alpinejs@{ALPINE_VERSION}/dist/cdn.min.js",
        f"Alpine.js v{ALPINE_VERSION}",
    ),
    "alpine-collapse.min.js": (
        f"https://unpkg.com/@alpinejs/collapse@{ALPINE_VERSION}/dist/cdn.min.js",
        f"Alpine Collapse v{ALPINE_VERSION}",
    ),
    "marked.umd.js": (
        f"https://unpkg.com/marked@{MARKED_VERSION}/lib/marked.umd.js",
        f"marked v{MARKED_VERSION}",
    ),
    "purify.min.js": (
        f"https://unpkg.com/dompurify@{DOMPURIFY_VERSION}/dist/purify.min.js",
        f"DOMPurify v{DOMPURIFY_VERSION}",
    ),
    "sortable.min.js": (
        f"https://unpkg.com/sortablejs@{SORTABLEJS_VERSION}/Sortable.min.js",
        f"SortableJS v{SORTABLEJS_VERSION}",
    ),
    "cropper.min.js": (
        f"https://unpkg.com/cropperjs@{CROPPERJS_VERSION}/dist/cropper.min.js",
        f"Cropper.js v{CROPPERJS_VERSION}",
    ),
    "alpine-morph.min.js": (
        f"https://unpkg.com/@alpinejs/morph@{ALPINE_VERSION}/dist/cdn.min.js",
        f"Alpine Morph v{ALPINE_VERSION}",
    ),
    "htmx-alpine-morph.js": (
        "https://unpkg.com/htmx-ext-alpine-morph@2.0.1/alpine-morph.js",
        "HTMX 2 Alpine Morph Extension",
    ),
    "inter-variable.woff2": (
        "https://unpkg.com/@fontsource-variable/inter@5.3.0/files/inter-latin-wght-normal.woff2",
        "Inter Variable Font (Latin)",
    ),
}

CHECKSUMS = {
    "alpine-collapse.min.js": "c7661d4e2cf0465e3cd693190debb5f592ac72dcc4cfe650581273767558b27b",
    "alpine.min.js": "57b37d7cae9a27d965fdae4adcc844245dfdc407e655aee85dcfff3a08036a3f",
    "cropper.min.js": "27f29dae3c6fa7a5f6126901f4d1f8cbbc36756196046aa7e97d2eae14131979",
    "htmx2.min.js": "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de",
    "inter-variable.woff2": "3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62",
    "marked.umd.js": "1f0acde4c17e28e4fb233ab358de856bee2f6ac28c7c757a68e2e3725f0db848",
    "purify.min.js": "1009d4715549e1331c1702529ed924260e4c5b5d04e2eb94e2112398a6dd1aa3",
    "sortable.min.js": "bf4241bc73fef7f11c59a283a69fe8051cdd31c6d8ff5a2b9ba219e7831fcf76",
    # Tailwind CSS CLI — platform variants
    "bin/tailwindcss-linux-x64": "5036c4fb4328e0bcdbb6065c70d8ac9452e0d4c947113a788a8f94fd390425c1",
    "bin/tailwindcss-linux-arm64": "394ddccc2402cfa3abd97dfba56f3587781a3d6e6ce66e65ceada14beb7664b8",
    "bin/tailwindcss-linux-x64-musl": "ae828e9e989ecbddb2bef856af8b0308ba162583b4922b3a065b5e26f86b0691",
    "bin/tailwindcss-linux-arm64-musl": "24a0dd39cbbced9d94f6313a747cc29ab2523a6a7b69204f2151e0af6aad6eef",
    "bin/tailwindcss-macos-x64": "cef8f110471e889c3c4409055cf8aff33076f58a081867b0dfc6534b290bfbb0",
    "bin/tailwindcss-macos-arm64": "b800b0659dc64b9f03ede5660244d9415d777d5739ae2889280877ca37be742a",
    "bin/tailwindcss-windows-x64.exe": "224a62a8351d3b8da9d950a4eb1d7176dc901dc4735b47f816f3dfcbc67d8654",
}


def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m"


def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m"


def _warn_mismatch(mismatched: list) -> None:
    print(_yellow("Checksum mismatch:"))
    for key, expected, actual in mismatched:
        print(f"    {key}")
        print(f"      expected: {expected}")
        print(f"      actual:   {actual}")


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vendor-sync/1.0"})
    last_err = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < 3:
                time.sleep(1 * attempt)
    raise last_err


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> int:
    missing = []
    mismatched = []
    for filename in DOWNLOADS:
        dest = VENDOR_DIR / filename
        if not dest.is_file():
            missing.append(f"static/vendor/{filename}")
    if not TAILWIND_DEST.is_file():
        missing.append(f"bin/{TAILWIND_BINARY}")

    if missing:
        print(_red("Missing vendor files:"))
        for m in missing:
            print(f"  {m}")
        return 1

    for key, expected in CHECKSUMS.items():
        p = ROOT / key
        if not p.is_file():
            continue
        actual = _hash_file(p)
        if actual != expected:
            mismatched.append((key, expected, actual))

    if mismatched:
        _warn_mismatch(mismatched)
        return 1

    print("All vendor files present and checksums match")
    return 0


def sync() -> int:
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Vendor directory: {VENDOR_DIR}")
    print()

    ok = 0
    fail = 0

    print(f"  {TAILWIND_BINARY} ...", end=" ", flush=True)
    try:
        data = _download(TAILWIND_URL)
        tmp = TAILWIND_DEST.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.rename(TAILWIND_DEST)
        # Make executable (no-op on Windows)
        try:
            TAILWIND_DEST.chmod(TAILWIND_DEST.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        except NotImplementedError:
            pass
        actual = hashlib.sha256(data).hexdigest()
        expected = CHECKSUMS.get(TAILWIND_CHECKSUM_KEY)
        if expected and actual != expected:
            _warn_mismatch([(TAILWIND_CHECKSUM_KEY, expected, actual)])
        print(f"  {len(data):>8} bytes  Tailwind CSS CLI {TAILWIND_VERSION}")
        ok += 1
    except Exception as e:
        print(f"  {_red('FAILED')} ({e})")
        fail += 1

    for filename, (url, label) in DOWNLOADS.items():
        dest = VENDOR_DIR / filename
        print(f"  {filename} ...", end=" ", flush=True)
        try:
            data = _download(url)
            # Strip source map references (browsers warn on 404s for .map files we don't ship)
            if dest.suffix in (".js", ".css"):
                data = data.replace(b"//# sourceMappingURL=", b"// ")
            tmp = dest.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.rename(dest)
            actual = hashlib.sha256(data).hexdigest()
            expected = CHECKSUMS.get(filename)
            if expected and actual != expected:
                _warn_mismatch([(filename, expected, actual)])
            print(f"  {len(data):>8} bytes  {label}")
            ok += 1
        except Exception as e:
            print(f"  {_red('FAILED')} ({e})")
            fail += 1

    print()
    print(f"Done: {ok} ok, {fail} failed out of {len(DOWNLOADS) + 1}")

    return 0 if fail == 0 else 1


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--check":
            return check()
        if sys.argv[1] == "--print-tailwind-path":
            print(TAILWIND_DEST.relative_to(ROOT))
            return 0
    return sync()


if __name__ == "__main__":
    exit(main())
