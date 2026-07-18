#!/usr/bin/env python3
"""Download vendor JS/CSS dependencies from CDN.

Zero npm/node dependency — uses Python stdlib only.
Run `./vendor-sync.py` to refresh all vendor files.
"""

import stat
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR_DIR = ROOT / "static" / "vendor"
BIN_DIR = ROOT / "bin"

TAILWIND_VERSION = "v4.3.2"

TAILWIND_URL = (
    f"https://github.com/tailwindlabs/tailwindcss/releases/download/"
    f"{TAILWIND_VERSION}/tailwindcss-linux-x64"
)
TAILWIND_DEST = BIN_DIR / "tailwindcss-linux-x64"

# Files downloaded from CDN
DOWNLOADS = {
    "htmx2.min.js": ("https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js", "htmx.org v2.0.10"),
    "alpine.min.js": ("https://unpkg.com/alpinejs@3.15.12/dist/cdn.min.js", "Alpine.js v3.15.12"),
    "alpine-collapse.min.js": (
        "https://unpkg.com/@alpinejs/collapse@3.15.12/dist/cdn.min.js",
        "Alpine Collapse v3.15.12",
    ),
    "marked.umd.js": ("https://unpkg.com/marked@18.0.5/lib/marked.umd.js", "marked v18.0.5"),
    "purify.min.js": ("https://unpkg.com/dompurify@3.4.11/dist/purify.min.js", "DOMPurify v3.4.11"),
    "sortable.min.js": ("https://unpkg.com/sortablejs@1.15.7/Sortable.min.js", "SortableJS v1.15.7"),
    "cropper.min.js": ("https://unpkg.com/cropperjs@2.1.1/dist/cropper.min.js", "Cropper.js v2.1.1"),
    "inter.css": (
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
        "Inter font CSS",
    ),
}

# Files generated locally (no CDN needed)
INLINE = {
    "json-enc.js": """\
htmx.defineExtension('json-enc', {
  onEvent: function (name, evt) {
    if (name === 'htmx:configRequest') {
      evt.detail.headers['Content-Type'] = 'application/json';
    }
  },
});
""",
}


def _download(url: str, dest: Path) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vendor-sync/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def check() -> int:
    """Verify all vendor files exist. Exit 0 if complete, 1 if anything missing."""
    missing = []
    for filename in DOWNLOADS:
        if not (VENDOR_DIR / filename).is_file():
            missing.append(f"static/vendor/{filename}")
    for filename in INLINE:
        if not (VENDOR_DIR / filename).is_file():
            missing.append(f"static/vendor/{filename}")
    if not TAILWIND_DEST.is_file():
        missing.append("bin/tailwindcss-linux-x64")
    if missing:
        print("Missing vendor files — run without --check to download:")
        for m in missing:
            print(f"  {m}")
        return 1
    print("All vendor files present")
    return 0


def sync() -> int:
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Vendor directory: {VENDOR_DIR}")
    print()

    ok = 0
    fail = 0

    # Tailwind CLI
    name = "tailwindcss-linux-x64"
    print(f"  {name} ...", end=" ", flush=True)
    try:
        data = _download(TAILWIND_URL, TAILWIND_DEST)
        TAILWIND_DEST.write_bytes(data)
        TAILWIND_DEST.chmod(TAILWIND_DEST.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"  {len(data):>8} bytes  Tailwind CSS CLI {TAILWIND_VERSION}")
        ok += 1
    except Exception as e:
        print(f"  FAILED ({e})")
        fail += 1

    # Downloaded vendor files
    for filename, (url, label) in DOWNLOADS.items():
        dest = VENDOR_DIR / filename
        print(f"  {filename} ...", end=" ", flush=True)
        try:
            data = _download(url, dest)
            # Strip source map references (browsers warn on 404s for .map files we don't ship)
            if dest.suffix in (".js", ".css"):
                data = data.replace(b"//# sourceMappingURL=", b"// ")
            dest.write_bytes(data)
            print(f"  {len(data):>8} bytes  {label}")
            ok += 1
        except Exception as e:
            print(f"  FAILED ({e})")
            fail += 1

    # Inline vendor files
    for filename, content in INLINE.items():
        dest = VENDOR_DIR / filename
        print(f"  {filename} ...", end=" ", flush=True)
        dest.write_text(content)
        print(f"  {len(content):>8} bytes  (inline)")
        ok += 1

    print()
    print(f"Done: {ok} ok, {fail} failed out of {len(DOWNLOADS) + len(INLINE) + 1}")

    return 0 if fail == 0 else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        return check()
    return sync()


if __name__ == "__main__":
    exit(main())
