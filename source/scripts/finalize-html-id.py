#!/usr/bin/env python3
"""Deterministically localize PreTeXt 2.49 HTML-only accessibility chrome.

PreTeXt 2.49.1 hard-codes its read-aloud controls, spoken strings, logo alt
text, and long-description fallback in English rather than routing them through
the localization catalog.  This bounded post-build pass changes only those
exact implementation literals and fails closed if any source literal remains.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


HTML_REPLACEMENTS = (
    (b'alt="Logo image"', 'alt="Gambar logo"'.encode()),
    (b'alt="described in detail following the image"', 'alt="dijelaskan secara terperinci setelah gambar"'.encode()),
    (b'title="described in detail following the image"', 'title="dijelaskan secara terperinci setelah gambar"'.encode()),
    (b'<summary title="details">', '<summary title="perincian">'.encode()),
    (b'title="Read aloud" aria-expanded="false"', 'title="Bacakan" aria-expanded="false"'.encode()),
    (b'<span class="name">Read aloud</span>', '<span class="name">Bacakan</span>'.encode()),
    (b'role="group" aria-label="Read aloud"', 'role="group" aria-label="Kontrol pembacaan"'.encode()),
    (b'id="ptx-read-aloud-prev" class="button" title="Previous sentence"', 'id="ptx-read-aloud-prev" class="button" title="Kalimat sebelumnya"'.encode()),
    (b'id="ptx-read-aloud-toggle" class="ptx-read-aloud-toggle button" title="Play"', 'id="ptx-read-aloud-toggle" class="ptx-read-aloud-toggle button" title="Putar"'.encode()),
    (b'id="ptx-read-aloud-next" class="button" title="Next sentence"', 'id="ptx-read-aloud-next" class="button" title="Kalimat berikutnya"'.encode()),
    (b'id="ptx-read-aloud-continue" class="ptx-read-aloud-continue button" hidden="hidden">Continue', 'id="ptx-read-aloud-continue" class="ptx-read-aloud-continue button" hidden="hidden">Lanjutkan'.encode()),
    (b'id="ptx-read-aloud-settings-button" class="ptx-read-aloud-settings-button button" title="Reading settings"', 'id="ptx-read-aloud-settings-button" class="ptx-read-aloud-settings-button button" title="Pengaturan pembacaan"'.encode()),
    (b'<h2 class="heading">Read aloud settings</h2>', '<h2 class="heading">Pengaturan pembacaan</h2>'.encode()),
    (b'id="ptx-read-aloud-settings-close-button" title="Close"', 'id="ptx-read-aloud-settings-close-button" title="Tutup"'.encode()),
    (b'<label for="ptx-read-aloud-voice">', '<label for="ptx-read-aloud-voice">'.encode()),
    (b'<span>Voice</span></label><select id="ptx-read-aloud-voice">', '<span>Suara</span></label><select id="ptx-read-aloud-voice">'.encode()),
    (b'<span>Reading speed</span><output id="ptx-read-aloud-rate-value"', '<span>Kecepatan baca</span><output id="ptx-read-aloud-rate-value"'.encode()),
    (b'<span>Collapsed content</span></label><select id="ptx-read-aloud-asides">', '<span>Konten terlipat</span></label><select id="ptx-read-aloud-asides">'.encode()),
    (b'<option value="skip">Announce, do not read</option>', '<option value="skip">Umumkan, jangan bacakan</option>'.encode()),
    (b'<option value="read">Read automatically</option>', '<option value="read">Bacakan secara otomatis</option>'.encode()),
    (b'<span>Follow along (auto-scroll)</span>', '<span>Ikuti pembacaan (gulir otomatis)</span>'.encode()),
    (b'<span>Continue to the next page automatically</span>', '<span>Lanjutkan ke halaman berikut secara otomatis</span>'.encode()),
)

JS_REPLACEMENTS = (
    (b'"read-aloud-show": "Read aloud"', '"read-aloud-show": "Bacakan"'.encode()),
    (b'"read-aloud-hide": "Hide reading controls"', '"read-aloud-hide": "Sembunyikan kontrol pembacaan"'.encode()),
    (b'"read-aloud-play": "Play"', '"read-aloud-play": "Putar"'.encode()),
    (b'"read-aloud-pause": "Pause"', '"read-aloud-pause": "Jeda"'.encode()),
    (b'"read-aloud-skip-table": "Table. Skipping."', '"read-aloud-skip-table": "Tabel. Dilewati."'.encode()),
    (b'"read-aloud-skip-code": "Code. Skipping."', '"read-aloud-skip-code": "Kode. Dilewati."'.encode()),
    (b'"read-aloud-skip-interactive": "Interactive element. Skipping."', '"read-aloud-skip-interactive": "Elemen interaktif. Dilewati."'.encode()),
    (b'"read-aloud-interactive-kind": "{kind} exercise."', '"read-aloud-interactive-kind": "Latihan {kind}."'.encode()),
    (b'"read-aloud-interactive": "Interactive exercise."', '"read-aloud-interactive": "Latihan interaktif."'.encode()),
    (b'"read-aloud-equation-fallback": "equation"', '"read-aloud-equation-fallback": "persamaan"'.encode()),
    (b'"read-aloud-image-alt": "Image. Alt text is:"', '"read-aloud-image-alt": "Gambar. Teks alternatifnya:"'.encode()),
    (b'"read-aloud-continuing": "Continuing to the next page."', '"read-aloud-continuing": "Melanjutkan ke halaman berikutnya."'.encode()),
    (b'"read-aloud-open-hint": "Press space to open."', '"read-aloud-open-hint": "Tekan spasi untuk membuka."'.encode()),
    (b'footnote: "Footnote"', 'footnote: "Catatan kaki"'.encode()),
    (b'description: "Description"', 'description: "Deskripsi"'.encode()),
)


def atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def apply_replacements(path: Path, replacements: tuple[tuple[bytes, bytes], ...], check_only: bool) -> tuple[bool, dict[str, int]]:
    raw = path.read_bytes()
    changed = False
    counts: dict[str, int] = {}
    for source, target in replacements:
        if source == target:
            continue
        count = raw.count(source)
        counts[source.decode("utf-8")] = count
        if count:
            if check_only:
                raise RuntimeError(f"Unlocalized literal remains in {path}: {source!r}")
            raw = raw.replace(source, target)
            changed = True
    if changed:
        atomic_write(path, raw)
    return changed, counts


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html-root", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    root = args.html_root.resolve()
    if not (root / "index.html").is_file():
        raise RuntimeError(f"Not a PreTeXt HTML output root: {root}")

    edition_css_source = Path(__file__).resolve().parent.parent / "xsl" / "appcomb-id.css"
    edition_css_target = root / "_static" / "appcomb-id.css"
    if not edition_css_source.is_file():
        raise RuntimeError(f"Missing source-controlled edition stylesheet: {edition_css_source}")
    css_matches = (
        edition_css_target.is_file()
        and edition_css_target.stat().st_size == edition_css_source.stat().st_size
        and sha256_file(edition_css_target) == sha256_file(edition_css_source)
    )
    if args.check_only:
        if not css_matches:
            raise RuntimeError("Generated edition stylesheet is absent or differs from its source-controlled bytes")
    elif not css_matches:
        edition_css_target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=edition_css_target.parent,
            prefix=f".{edition_css_target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_css = Path(handle.name)
            try:
                with edition_css_source.open("rb") as source_handle:
                    shutil.copyfileobj(source_handle, handle)
                handle.flush()
                os.fsync(handle.fileno())
            except Exception:
                temporary_css.unlink(missing_ok=True)
                raise
        os.replace(temporary_css, edition_css_target)

    html_files = sorted(root.rglob("*.html"), key=lambda path: path.relative_to(root).as_posix().encode("utf-8"))
    changed_html = 0
    aggregate_counts: dict[str, int] = {}
    for path in html_files:
        changed, counts = apply_replacements(path, HTML_REPLACEMENTS, args.check_only)
        changed_html += int(changed)
        for key, value in counts.items():
            aggregate_counts[key] = aggregate_counts.get(key, 0) + value

    js_paths = (
        root / "_static/pretext/js/dist/pretext-read-aloud.js",
        root / "_static/pretext/js/src/read-aloud/strings.js",
    )
    changed_js = 0
    for path in js_paths:
        if not path.is_file():
            raise RuntimeError(f"Missing required read-aloud runtime file: {path}")
        changed, _ = apply_replacements(path, JS_REPLACEMENTS, args.check_only)
        changed_js += int(changed)

    # All intended Indonesian targets must exist after mutation/check.  This
    # catches upstream template drift that silently removes a control surface.
    optional_html_targets = {
        'title="dijelaskan secara terperinci setelah gambar"'.encode(),
    }
    target_counts = {target: 0 for source, target in HTML_REPLACEMENTS if source != target}
    for path in html_files:
        raw = path.read_bytes()
        for target in target_counts:
            target_counts[target] += raw.count(target)
    required_html_targets = [target for target in target_counts if target not in optional_html_targets]
    missing_targets = [target.decode("utf-8") for target in required_html_targets if target_counts[target] == 0]
    if missing_targets:
        raise RuntimeError(f"Expected localized HTML literals are absent: {missing_targets}")
    for path in js_paths:
        raw = path.read_bytes()
        missing = [target.decode("utf-8") for source, target in JS_REPLACEMENTS if target not in raw]
        if missing:
            raise RuntimeError(f"Expected localized read-aloud strings are absent from {path}: {missing}")

    result = {
        "status": "pass",
        "mode": "check-only" if args.check_only else "finalize",
        "html_files": len(html_files),
        "html_files_changed": changed_html,
        "javascript_files_checked": len(js_paths),
        "javascript_files_changed": changed_js,
        "edition_stylesheet_path": edition_css_target.relative_to(root).as_posix(),
        "edition_stylesheet_bytes": edition_css_target.stat().st_size,
        "edition_stylesheet_sha256": sha256_file(edition_css_target),
        "source_literal_counts_before": aggregate_counts,
        "localized_literal_counts_after": {key.decode("utf-8"): value for key, value in target_counts.items()},
        "read_aloud_dist_sha256": sha256_file(js_paths[0]),
        "read_aloud_source_strings_sha256": sha256_file(js_paths[1]),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
