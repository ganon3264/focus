#!/usr/bin/env python3
"""Download vendor JS/CSS dependencies from CDN.
Uses Python stdlib only.
Run `./vendor-sync.py` to refresh all vendor files.
"""

import hashlib
import stat
import sys
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

TAILWIND_URL = (
    f"https://github.com/tailwindlabs/tailwindcss/releases/download/"
    f"{TAILWIND_VERSION}/tailwindcss-linux-x64"
)
TAILWIND_DEST = BIN_DIR / "tailwindcss-linux-x64"

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
    "idiomorph-ext.min.js": (
        f"https://unpkg.com/idiomorph@{IDIOMORPH_VERSION}/dist/idiomorph-ext.min.js",
        f"Idiomorph v{IDIOMORPH_VERSION} + HTMX morph extension",
    ),
    "inter.css": (
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
        "Inter font CSS",
    ),
}

CHECKSUMS = {
    "alpine-collapse.min.js": "c7661d4e2cf0465e3cd693190debb5f592ac72dcc4cfe650581273767558b27b",
    "alpine.min.js": "57b37d7cae9a27d965fdae4adcc844245dfdc407e655aee85dcfff3a08036a3f",
    "cropper.min.js": "27f29dae3c6fa7a5f6126901f4d1f8cbbc36756196046aa7e97d2eae14131979",
    "htmx2.min.js": "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de",
    "idiomorph-ext.min.js": "a6437e55b1b6a07bc421f0d230266a39399b6826c6ed19e0ed9c63b707444a5f",
    "inter.css": "34bd07407ad1de576cba1f67651fa31a8fe783e24a6e1817e08c24bdc54014f9",
    "marked.umd.js": "1f0acde4c17e28e4fb233ab358de856bee2f6ac28c7c757a68e2e3725f0db848",
    "purify.min.js": "1009d4715549e1331c1702529ed924260e4c5b5d04e2eb94e2112398a6dd1aa3",
    "sortable.min.js": "bf4241bc73fef7f11c59a283a69fe8051cdd31c6d8ff5a2b9ba219e7831fcf76",
    "bin/tailwindcss-linux-x64": "5036c4fb4328e0bcdbb6065c70d8ac9452e0d4c947113a788a8f94fd390425c1",
}


def _warn_mismatch(mismatched: list) -> None:
    print("Checksum mismatch:")
    for key, expected, actual in mismatched:
        print(f"    {key}")
        print(f"      expected: {expected}")
        print(f"      actual:   {actual}")


def _download(url: str, dest: Path) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vendor-sync/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


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
        missing.append("bin/tailwindcss-linux-x64")

    if missing:
        print("Missing vendor files — run without --check to download:")
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
        print("  Run without --check to re-download and update checksums.")
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

    name = "tailwindcss-linux-x64"
    print(f"  {name} ...", end=" ", flush=True)
    try:
        data = _download(TAILWIND_URL, TAILWIND_DEST)
        TAILWIND_DEST.write_bytes(data)
        TAILWIND_DEST.chmod(TAILWIND_DEST.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        actual = hashlib.sha256(data).hexdigest()
        expected = CHECKSUMS.get("bin/tailwindcss-linux-x64")
        if expected and actual != expected:
            _warn_mismatch([("bin/tailwindcss-linux-x64", expected, actual)])
        print(f"  {len(data):>8} bytes  Tailwind CSS CLI {TAILWIND_VERSION}")
        ok += 1
    except Exception as e:
        print(f"  FAILED ({e})")
        fail += 1

    for filename, (url, label) in DOWNLOADS.items():
        dest = VENDOR_DIR / filename
        print(f"  {filename} ...", end=" ", flush=True)
        try:
            data = _download(url, dest)
            # Strip source map references (browsers warn on 404s for .map files we don't ship)
            if dest.suffix in (".js", ".css"):
                data = data.replace(b"//# sourceMappingURL=", b"// ")
            dest.write_bytes(data)
            actual = hashlib.sha256(data).hexdigest()
            expected = CHECKSUMS.get(filename)
            if expected and actual != expected:
                _warn_mismatch([(filename, expected, actual)])
            print(f"  {len(data):>8} bytes  {label}")
            ok += 1
        except Exception as e:
            print(f"  FAILED ({e})")
            fail += 1

    print()
    print(f"Done: {ok} ok, {fail} failed out of {len(DOWNLOADS) + 1}")

    return 0 if fail == 0 else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        return check()
    return sync()


if __name__ == "__main__":
    exit(main())
