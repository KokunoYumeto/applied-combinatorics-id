#!/usr/bin/env python3
"""Prepend a deterministic DOI-bound release cover to the verified reader PDF."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


TITLE = "Kombinatorika Terapan"
SUBTITLE = "Edisi Bahasa Indonesia lengkap"
AUTHORS = "Mitchel T. Keller dan William T. Trotter"
VERSION = "2026.08.22.2"
LANGUAGE = "Bahasa Indonesia (id-ID)"
VERSION_DOI = "10.5281/zenodo.22062005"
CONCEPT_DOI = "10.5281/zenodo.22058531"
PUBLIC_RECORD = "https://zenodo.org/records/22062005"
SOURCE_REPOSITORY = "https://github.com/mitchkeller/applied-combinatorics"
SOURCE_COMMIT = "33b20df670d1f8d98266cd2f4a287a79b01649ea"
LICENSE = "Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def draw_paragraph(c: canvas.Canvas, text: str, style: ParagraphStyle, x: float, y: float, width: float) -> float:
    paragraph = Paragraph(text, style)
    _, height = paragraph.wrap(width, 10 * inch)
    paragraph.drawOn(c, x, y - height)
    return y - height


def make_cover() -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter, invariant=1, pageCompression=1)
    width, height = letter
    navy = colors.HexColor("#183153")
    blue = colors.HexColor("#2B6CB0")
    muted = colors.HexColor("#4A5568")
    pale = colors.HexColor("#EDF4FB")

    c.setFillColor(navy)
    c.rect(0, height - 1.42 * inch, width, 1.42 * inch, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 27)
    c.drawString(0.68 * inch, height - 0.72 * inch, TITLE)
    c.setFont("Helvetica", 15)
    c.drawString(0.70 * inch, height - 1.08 * inch, SUBTITLE)

    body = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=10.2,
        leading=14.2,
        textColor=colors.HexColor("#1A202C"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    small = ParagraphStyle(
        "small",
        parent=body,
        fontSize=8.7,
        leading=12.2,
        textColor=muted,
    )
    label = ParagraphStyle(
        "label",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=navy,
    )

    left = 0.72 * inch
    content_width = width - 1.44 * inch
    y = height - 1.83 * inch
    y = draw_paragraph(c, f"<b>Penulis asli:</b> {AUTHORS}", body, left, y, content_width)
    y -= 0.09 * inch
    y = draw_paragraph(c, f"<b>Bahasa:</b> {LANGUAGE} &nbsp;&nbsp; <b>Versi:</b> {VERSION}", body, left, y, content_width)
    y -= 0.27 * inch

    c.setFillColor(pale)
    c.roundRect(left, y - 1.34 * inch, content_width, 1.34 * inch, 8, stroke=0, fill=1)
    box_x = left + 0.20 * inch
    box_y = y - 0.18 * inch
    box_width = content_width - 0.40 * inch
    box_y = draw_paragraph(c, "<b>Identitas edisi</b>", label, box_x, box_y, box_width)
    box_y -= 0.05 * inch
    box_y = draw_paragraph(
        c,
        f'DOI versi: <link href="https://doi.org/{VERSION_DOI}" color="#2B6CB0">{VERSION_DOI}</link>',
        body,
        box_x,
        box_y,
        box_width,
    )
    box_y -= 0.02 * inch
    box_y = draw_paragraph(
        c,
        f'DOI konsep: <link href="https://doi.org/{CONCEPT_DOI}" color="#2B6CB0">{CONCEPT_DOI}</link>',
        body,
        box_x,
        box_y,
        box_width,
    )
    box_y -= 0.02 * inch
    draw_paragraph(
        c,
        f'Repositori publik edisi: '
        f'<link href="{PUBLIC_RECORD}" color="#2B6CB0">{PUBLIC_RECORD}</link>',
        small,
        box_x,
        box_y,
        box_width,
    )
    y -= 1.68 * inch

    y = draw_paragraph(c, "<b>Cakupan</b>", label, left, y, content_width)
    y -= 0.06 * inch
    y = draw_paragraph(
        c,
        "Edisi lengkap buku <i>Applied Combinatorics</i>, termasuk materi awal, 16 bab, latihan, "
        "petunjuk/jawaban/solusi yang tersedia, catatan akhir, dan lampiran latar belakang.",
        body,
        left,
        y,
        content_width,
    )
    y -= 0.24 * inch
    y = draw_paragraph(c, "<b>Sumber yang dibekukan</b>", label, left, y, content_width)
    y -= 0.06 * inch
    y = draw_paragraph(
        c,
        f'<link href="{SOURCE_REPOSITORY}" color="#2B6CB0">{SOURCE_REPOSITORY}</link><br/>'
        f'Commit: <font name="Courier">{SOURCE_COMMIT}</font>',
        small,
        left,
        y,
        content_width,
    )
    y -= 0.23 * inch
    y = draw_paragraph(c, "<b>Lisensi dan keterangan produksi</b>", label, left, y, content_width)
    y -= 0.06 * inch
    y = draw_paragraph(
        c,
        f"Karya turunan ini diterbitkan berdasarkan {LICENSE}. Atribusi kedua penulis, "
        "pemberitahuan perubahan, dan ketentuan ShareAlike dipertahankan. Edisi ini diproduksi "
        "dengan OpenAI Codex gpt-5.6-sol, Ultra. Pekerjaan ini dilakukan atas permintaan pengguna. "
        "Karya ini bukan edisi yang didukung "
        "atau disahkan oleh penulis asli.",
        small,
        left,
        y,
        content_width,
    )

    c.setStrokeColor(blue)
    c.setLineWidth(1)
    c.line(left, 0.72 * inch, width - left, 0.72 * inch)
    footer = "Gunakan DOI versi untuk mengutip berkas tepat ini; gunakan DOI konsep untuk edisi Indonesia terbaru."
    c.setFillColor(muted)
    c.setFont("Helvetica", 7.9)
    if stringWidth(footer, "Helvetica", 7.9) > content_width:
        raise ValueError("Footer unexpectedly exceeds the content width")
    c.drawString(left, 0.49 * inch, footer)
    c.showPage()
    c.save()
    return buffer.getvalue()


def count_outline_leaves(items: list[object]) -> int:
    total = 0
    for item in items:
        if isinstance(item, list):
            total += count_outline_leaves(item)
        else:
            total += 1
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    receipt_path = args.receipt.resolve()
    if input_path == output_path:
        raise ValueError("Input and output paths must differ")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)

    base = PdfReader(str(input_path))
    cover = PdfReader(io.BytesIO(make_cover()))
    base_outline_count = count_outline_leaves(base.outline)

    writer = PdfWriter()
    writer.append(cover, import_outline=False)
    writer.append(base, import_outline=True)
    writer.add_metadata(
        {
            "/Title": f"{TITLE} - {SUBTITLE}",
            "/Author": "Mitchel T. Keller; William T. Trotter",
            "/Subject": f"Edisi Bahasa Indonesia lengkap, versi {VERSION}, DOI {VERSION_DOI}",
            "/Keywords": "kombinatorika, matematika diskret, Bahasa Indonesia, id-ID",
            "/Creator": "PreTeXt and Codex release assembly",
            "/Producer": "pypdf",
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as stream:
        writer.write(stream)

    reopened = PdfReader(str(output_path))
    output_outline_count = count_outline_leaves(reopened.outline)
    if len(reopened.pages) != len(base.pages) + 1:
        raise RuntimeError("Release PDF page count does not equal base page count plus one cover")
    if output_outline_count != base_outline_count:
        raise RuntimeError("Outline leaf count changed while adding the release cover")

    cover_page = reopened.pages[0]
    cover_text = cover_page.extract_text() or ""
    cover_text_search = " ".join(cover_text.split())
    cover_uris: set[str] = set()
    for annotation_reference in cover_page.get("/Annots", []):
        annotation = annotation_reference.get_object()
        action = annotation.get("/A")
        if action is not None and action.get("/URI") is not None:
            cover_uris.add(str(action.get("/URI")))
    cover_checks = {
        "contains_version_doi": VERSION_DOI in cover_text_search and f"https://doi.org/{VERSION_DOI}" in cover_uris,
        "contains_concept_doi": CONCEPT_DOI in cover_text_search and f"https://doi.org/{CONCEPT_DOI}" in cover_uris,
        "contains_public_record": PUBLIC_RECORD in cover_text_search and PUBLIC_RECORD in cover_uris,
        "unavailable_edition_repository_absent": all(
            marker not in cover_text_search and all(marker not in uri for uri in cover_uris)
            for marker in (
                "github.com/" + "KokunoYumeto",
                "kokunoyumeto." + "github.io",
                "publikasi GitHub masih tertunda",
            )
        ),
        "contains_frozen_source_commit": SOURCE_COMMIT in cover_text_search,
        "contains_coverage_statement": "Edisi lengkap buku" in cover_text_search,
        "contains_license_change_nonendorsement_statement": all(
            marker in cover_text_search
            for marker in (
                "Creative Commons Attribution-ShareAlike 4.0 International",
                "Karya turunan",
                "bukan edisi yang didukung atau disahkan oleh penulis asli",
            )
        ),
    }
    failed_cover_checks = [name for name, passed in cover_checks.items() if not passed]
    if failed_cover_checks:
        raise RuntimeError(f"Release-cover identity checks failed: {failed_cover_checks}")

    receipt = {
        "schema": "r012.pdf-release-cover-assembly",
        "schema_version": "1.0.0",
        "result": "pass",
        "version": VERSION,
        "language": "id-ID",
        "version_doi": VERSION_DOI,
        "concept_doi": CONCEPT_DOI,
        "input": {
            "path": args.input.as_posix(),
            "bytes": input_path.stat().st_size,
            "sha256": sha256(input_path),
            "pages": len(base.pages),
            "outline_leaves": base_outline_count,
        },
        "output": {
            "path": args.output.as_posix(),
            "bytes": output_path.stat().st_size,
            "sha256": sha256(output_path),
            "pages": len(reopened.pages),
            "outline_leaves": output_outline_count,
        },
        "cover": {"pages_added": 1, **cover_checks, "uri_links": sorted(cover_uris)},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt["output"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
