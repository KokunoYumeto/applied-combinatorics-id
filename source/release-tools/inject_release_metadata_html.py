#!/usr/bin/env python3
"""Create the DOI-bound public HTML reader from the rights-pruned release copy."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "source" / "output" / "html-open-release-20260822"
DEST = ROOT / "source" / "output" / "html-public-2026.08.22.1"
RECEIPT = ROOT / "qa" / "HTML_RELEASE_METADATA_INJECTION_20260822_1.json"
BASE_FILES = 1495
BASE_BYTES = 287_590_509
BASE_MANIFEST = "9442ed4533fcb901ec02ae069ed98a81ff6174329982086d884dacd14a0138d1"
BASE_CSS_BYTES = 668
BASE_CSS_SHA = "0a5b2e443554134df1d5e6ca8e14805f18a24401fb5610cd88cd5a39d4a50879"
VERSION = "2026.08.22.1"
VERSION_DOI = "10.5281/zenodo.22059672"
CONCEPT_DOI = "10.5281/zenodo.22058531"
PUBLIC_RECORD = "https://zenodo.org/records/22059672"
SOURCE_COMMIT = "33b20df670d1f8d98266cd2f4a287a79b01649ea"
SOURCE_URL = f"https://github.com/mitchkeller/applied-combinatorics/tree/{SOURCE_COMMIT}"
JOBE_RUNTIME_STEM = "717.6536d187ca95d341.js"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_stats(root: Path) -> tuple[int, int, str]:
    rows: list[tuple[str, int, str]] = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix().encode("utf-8")):
        rel = path.relative_to(root).as_posix()
        rows.append((rel, path.stat().st_size, file_sha(path)))
    payload = "".join(f"{name}\t{size}\t{digest}\n" for name, size, digest in rows).encode("utf-8")
    return len(rows), sum(row[1] for row in rows), sha(payload)


METADATA_HTML = f'''<aside class="r012-release-metadata" aria-label="Metadata rilis edisi Bahasa Indonesia">
<p class="r012-release-lead"><strong>Edisi lengkap Bahasa Indonesia (<span lang="en">id-ID</span>) · versi {VERSION}</strong></p>
<p><a href="https://doi.org/{VERSION_DOI}">DOI versi {VERSION_DOI}</a> · <a href="https://doi.org/{CONCEPT_DOI}">DOI konsep {CONCEPT_DOI}</a> · <a href="{PUBLIC_RECORD}">semua berkas di Zenodo</a></p>
<p>Diterjemahkan dengan bantuan AI dan dipelihara secara independen berdasarkan <a href="{SOURCE_URL}">sumber resmi pada commit <code>{SOURCE_COMMIT}</code></a>. Cakupan: seluruh buku, termasuk bagian awal, 16 bab, latihan, bagian akhir, dan lampiran latar belakang. Edisi ini bukan terbitan resmi Mitchel T. Keller atau William T. Trotter dan tidak menyiratkan dukungan mereka.</p>
</aside>'''

CSS_APPEND = '''

/* DOI-bound release metadata; deterministic public-artifact addition, 2026-08-22.1. */
.r012-release-metadata {
  box-sizing: border-box;
  width: min(60rem, 100%);
  margin: 1.25rem auto 2rem;
  padding: 1rem 1.25rem;
  border: 1px solid #8aa0b8;
  border-left: 0.35rem solid #16395f;
  border-radius: 0.25rem;
  background: #f5f8fb;
  color: #182330;
}
.r012-release-metadata p { margin: 0.45rem 0; }
.r012-release-metadata .r012-release-lead { margin-top: 0; font-size: 1.05em; }
.r012-release-metadata a { overflow-wrap: anywhere; }
@media (max-width: 700px) {
  .r012-release-metadata { margin: 1rem auto 1.5rem; padding: 0.85rem 1rem; }
}
'''


def inject(path: Path, marker: str) -> dict[str, object]:
    before = path.read_bytes()
    text = before.decode("utf-8")
    if text.count(marker) != 1 or "r012-release-metadata" in text:
        raise RuntimeError(f"Unexpected release metadata marker state: {path.name}")
    after = text.replace(marker, marker + "\n" + METADATA_HTML, 1).encode("utf-8")
    path.write_bytes(after)
    return {
        "path": path.relative_to(DEST).as_posix(),
        "before_bytes": len(before),
        "before_sha256": sha(before),
        "after_bytes": len(after),
        "after_sha256": sha(after),
        "operation": "insert DOI/source/coverage/AI/nonendorsement release metadata after the visible page heading",
    }


def deterministic_gzip(data: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, compresslevel=9, mtime=0) as stream:
        stream.write(data)
    return output.getvalue()


def sanitize_jobe_client_identifier(destination: Path) -> dict[str, object]:
    """Disable and remove the upstream public Jobe client identifier from emitted runtime bytes.

    The unmodified pinned Runestone corresponding-source archive remains in the
    corresponding-source package.  The public offline reader does not load the
    disabled activecode component and must not expose its public service key.
    """
    js_path = destination / "_static" / JOBE_RUNTIME_STEM
    map_path = destination / "_static" / f"{JOBE_RUNTIME_STEM}.map"
    paths = (js_path, map_path)
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"Required Runestone runtime surface is absent: {path.name}")

    js_before = js_path.read_bytes()
    candidates = set(
        re.findall(
            rb"(?:this\.)?API_KEY\s*=\s*[\"']([A-Za-z0-9_-]{16,128})[\"']",
            js_before,
        )
    )
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one Runestone Jobe client identifier, found {len(candidates)}")
    client_identifier = candidates.pop()

    records: list[dict[str, object]] = []
    identifier_occurrences = 0
    use_api_key_true_occurrences = 0
    for path in paths:
        before = path.read_bytes()
        identifier_count = before.count(client_identifier)
        identifier_occurrences += identifier_count
        after = before.replace(client_identifier, b"")
        after, minified_true = re.subn(
            rb"(\bUSE_API_KEY\s*=\s*)!0",
            rb"\g<1>!1",
            after,
        )
        after, source_true = re.subn(
            rb"(\bUSE_API_KEY\s*=\s*)true",
            rb"\g<1>false",
            after,
        )
        use_api_key_true_occurrences += minified_true + source_true
        if client_identifier in after:
            raise RuntimeError(f"Runestone client identifier remains in {path.name}")
        path.write_bytes(after)
        records.append(
            {
                "path": path.relative_to(destination).as_posix(),
                "before_bytes": len(before),
                "before_sha256": sha(before),
                "after_bytes": len(after),
                "after_sha256": sha(after),
                "identifier_occurrences_removed": identifier_count,
                "USE_API_KEY_true_assignments_disabled": minified_true + source_true,
            }
        )

    if identifier_occurrences != 2 or use_api_key_true_occurrences != 2:
        raise RuntimeError(
            "Unexpected Runestone Jobe sanitization topology: "
            f"identifier={identifier_occurrences}, enabled_assignments={use_api_key_true_occurrences}"
        )

    for source_path in paths:
        gzip_path = source_path.with_name(source_path.name + ".gz")
        if not gzip_path.is_file():
            raise RuntimeError(f"Required compressed Runestone surface is absent: {gzip_path.name}")
        before = gzip_path.read_bytes()
        compressed = deterministic_gzip(source_path.read_bytes())
        gzip_path.write_bytes(compressed)
        if gzip.decompress(compressed) != source_path.read_bytes() or client_identifier in gzip.decompress(compressed):
            raise RuntimeError(f"Compressed Runestone sanitization replay failed: {gzip_path.name}")
        records.append(
            {
                "path": gzip_path.relative_to(destination).as_posix(),
                "before_bytes": len(before),
                "before_sha256": sha(before),
                "after_bytes": len(compressed),
                "after_sha256": sha(compressed),
                "operation": "deterministic gzip replay of sanitized uncompressed peer",
            }
        )

    return {
        "result": "pass",
        "classification": "upstream publicly committed Runestone Jobe client identifier; not a Floris credential",
        "public_runtime_disposition": "identifier removed and USE_API_KEY disabled",
        "corresponding_source_disposition": "unmodified pinned upstream source retained separately for source and license fidelity",
        "identifier_occurrences_removed": identifier_occurrences,
        "USE_API_KEY_true_assignments_disabled": use_api_key_true_occurrences,
        "files": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=DEST)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination != DEST.resolve():
        raise RuntimeError("Destination differs from the fixed R012 public-reader path")
    if destination.exists():
        raise RuntimeError("Destination already exists; refusing to overwrite")
    base = tree_stats(BASE)
    if base != (BASE_FILES, BASE_BYTES, BASE_MANIFEST):
        raise RuntimeError(f"Rights-pruned base reader drifted: {base}")
    css_base = BASE / "_static" / "appcomb-id.css"
    if css_base.stat().st_size != BASE_CSS_BYTES or file_sha(css_base) != BASE_CSS_SHA:
        raise RuntimeError("Edition stylesheet differs from the frozen base")
    shutil.copytree(BASE, destination)
    changes = [
        inject(
            destination / "app-comb-2.html",
            '<section class="frontmatter" id="app-comb-2"><h1 class="heading"><span class="title">Kombinatorika Terapan</span></h1>',
        ),
        inject(
            destination / "app-comb.html",
            '<section class="book" id="app-comb"><h1 class="heading ptx-toc-heading">Daftar Isi</h1>',
        ),
    ]
    css_path = destination / "_static" / "appcomb-id.css"
    css_before = css_path.read_bytes()
    css_after = css_before + CSS_APPEND.encode("utf-8")
    css_path.write_bytes(css_after)
    changes.append({
        "path": "_static/appcomb-id.css",
        "before_bytes": len(css_before),
        "before_sha256": sha(css_before),
        "after_bytes": len(css_after),
        "after_sha256": sha(css_after),
        "operation": "append responsive release-metadata styling",
    })
    metadata_change_paths = [destination / row["path"] for row in changes]
    jobe_sanitization = sanitize_jobe_client_identifier(destination)
    changes.extend(jobe_sanitization["files"])
    forbidden: list[str] = []
    patterns = (b"249.7ec032cf", b"580.284285", b"sql-wasm.wasm")
    # The exact base tree already passed a runtime-aware whole-tree request
    # closure.  This metadata step can only introduce a new executable
    # reference through one of the three files it changes, so scan precisely
    # those surfaces; retained source maps may lawfully mention excluded source
    # strings without creating an emitted request.
    for path in metadata_change_paths:
        raw = path.read_bytes()
        if any(pattern in raw for pattern in patterns):
            forbidden.append(path.relative_to(destination).as_posix())
    if forbidden:
        raise RuntimeError(f"Public reader reintroduced excluded runtime references: {forbidden[:20]}")
    unavailable_markers = (
        b"github.com/" + b"KokunoYumeto",
        b"kokunoyumeto." + b"github.io",
        b"publikasi GitHub masih tertunda",
    )
    unavailable_hits: list[str] = []
    for path in sorted(p for p in destination.rglob("*") if p.is_file()):
        raw = path.read_bytes()
        if any(marker in raw for marker in unavailable_markers):
            unavailable_hits.append(path.relative_to(destination).as_posix())
    if unavailable_hits:
        raise RuntimeError(f"Public reader retains unavailable edition-repository references: {unavailable_hits[:20]}")
    enabled_key_hits: list[str] = []
    enabled_key_patterns = (
        re.compile(rb"API_KEY\s*=\s*\\?[\"'][A-Za-z0-9_-]{16,128}\\?[\"']"),
        re.compile(rb"USE_API_KEY\s*=\s*(?:true|!0)"),
    )
    for path in sorted(p for p in destination.rglob("*") if p.is_file() and not p.name.endswith(".gz")):
        raw = path.read_bytes()
        if any(pattern.search(raw) for pattern in enabled_key_patterns):
            enabled_key_hits.append(path.relative_to(destination).as_posix())
    if enabled_key_hits:
        raise RuntimeError(f"Public reader retains enabled credential-like runtime assignments: {enabled_key_hits[:20]}")
    final_files, final_bytes, final_manifest = tree_stats(destination)
    receipt = {
        "schema": "r012.html-release-metadata-injection",
        "schema_version": "1.0.0",
        "evidence_date": "2026-08-22",
        "result": "pass",
        "base": {"path": BASE.relative_to(ROOT).as_posix(), "files": base[0], "bytes": base[1], "manifest_sha256": base[2]},
        "output": {"path": destination.relative_to(ROOT).as_posix(), "files": final_files, "bytes": final_bytes, "manifest_sha256": final_manifest},
        "release_identity": {"version": VERSION, "version_doi": VERSION_DOI, "concept_doi": CONCEPT_DOI, "canonical_public_repository": PUBLIC_RECORD, "source_commit": SOURCE_COMMIT},
        "modified_files": changes,
        "forbidden_runtime_reference_count": 0,
        "forbidden_runtime_reference_patterns": [pattern.decode("ascii") for pattern in patterns],
        "unavailable_edition_repository_reference_count": 0,
        "jobe_client_identifier_sanitization": jobe_sanitization,
        "enabled_credential_like_runtime_assignment_count": 0,
        "limitations": ["This artifact-only metadata layer does not alter the canonical translated PreTeXt source; the deterministic injector is included with the editable source package."],
    }
    raw = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    RECEIPT.write_bytes(raw)
    print(json.dumps({"status": "pass", "files": final_files, "bytes": final_bytes, "manifest_sha256": final_manifest, "receipt": RECEIPT.relative_to(ROOT).as_posix(), "receipt_bytes": len(raw), "receipt_sha256": sha(raw)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
