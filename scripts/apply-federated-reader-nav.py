#!/usr/bin/env python3
"""Apply or verify the universal program navigation on a static HTML tree.

The transformation is deliberately byte-preserving outside the single fragment
inserted immediately after each document's opening ``body`` tag. Re-running the
apply command is idempotent: an already valid document is left untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MARKER = b'id="interlanguage-program-nav-v1"'
REQUIRED_LINKS = (
    b"https://kokunoyumeto.github.io/program-matematika-indonesia/id/#course-C70",
    b"https://kokunoyumeto.github.io/program-matematika-indonesia/en/#course-C70",
    b"https://appliedcombinatorics.org/book/",
)
BODY = re.compile(br"(<body\b[^>]*>)", re.IGNORECASE)
FRAGMENT = b"""<nav id="interlanguage-program-nav-v1" aria-label="Navigasi pembaca dan sumber / Reader and source navigation" style="position:sticky;top:0;z-index:2147483647;display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:.55rem;padding:.65rem 1rem;border-bottom:2px solid #1d4ed8;background:#eff6ff;color:#172554;font:600 1rem/1.35 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;text-align:center">
  <a rel="home" href="https://kokunoyumeto.github.io/program-matematika-indonesia/id/#course-C70" style="display:inline-block;padding:.38rem .62rem;border:2px solid #1d4ed8;border-radius:.35rem;background:#fff;color:#1e3a8a;text-decoration:underline">Program matematika (Bahasa Indonesia)</a>
  <a rel="home" href="https://kokunoyumeto.github.io/program-matematika-indonesia/en/#course-C70" style="display:inline-block;padding:.38rem .62rem;border:2px solid #1d4ed8;border-radius:.35rem;background:#fff;color:#1e3a8a;text-decoration:underline">Mathematics program (English)</a>
  <a rel="external" href="https://appliedcombinatorics.org/book/" style="display:inline-block;padding:.38rem .62rem;border:2px solid #1d4ed8;border-radius:.35rem;background:#fff;color:#1e3a8a;text-decoration:underline">Sumber asli / Authoritative original</a>
</nav>"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_document(path: Path, data: bytes) -> list[str]:
    errors: list[str] = []
    marker_count = data.count(MARKER)
    if marker_count != 1:
        errors.append(f"marker_count={marker_count}")
    for link in REQUIRED_LINKS:
        if data.count(link) != 1:
            errors.append(f"required_link_count[{link.decode('ascii')}]={data.count(link)}")
    if not BODY.search(data):
        errors.append("missing_body_tag")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"HTML root does not exist: {root}")
    html_files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".html"
    )
    if not html_files:
        raise SystemExit(f"No HTML files found beneath: {root}")

    changed: list[str] = []
    failures: dict[str, list[str]] = {}
    total_before = 0
    total_after = 0

    for path in html_files:
        relative = path.relative_to(root).as_posix()
        original = path.read_bytes()
        total_before += len(original)
        current = original

        if args.apply and MARKER not in current:
            current, substitutions = BODY.subn(
                lambda match: match.group(1) + b"\n" + FRAGMENT + b"\n",
                current,
                count=1,
            )
            if substitutions != 1:
                failures[relative] = ["unable_to_insert_after_body"]
                total_after += len(original)
                continue
            path.write_bytes(current)
            changed.append(relative)

        errors = validate_document(path, current)
        if errors:
            failures[relative] = errors
        total_after += len(current)

    report = {
        "schema": "interlanguage-federated-reader-nav-application-v1",
        "mode": "apply" if args.apply else "check",
        "root": str(root),
        "html_files": len(html_files),
        "changed_files": len(changed),
        "unchanged_files": len(html_files) - len(changed),
        "bytes_before": total_before,
        "bytes_after": total_after,
        "fragment_sha256": digest(FRAGMENT),
        "required_links": [link.decode("ascii") for link in REQUIRED_LINKS],
        "failures": failures,
        "result": "PASS" if not failures else "FAIL",
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
