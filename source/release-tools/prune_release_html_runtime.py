#!/usr/bin/env python3
"""Prepare a fail-closed HTML release copy with proven runtime exclusions.

This script never edits the canonical source/output/html tree. It validates the
pinned rights witness, computes the exact allowed removal set, and scans all
retained HTML/runtime bytes for references to removed assets. A destination
copy is created only when the reference scan is empty.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit


LANE_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_HTML = (LANE_ROOT / "source" / "output" / "html").resolve()
BACKEND_CONFIG = LANE_ROOT / "backend" / "config.json"
STATIC_DIRNAME = "_static"
HASH_TOKEN_RE = re.compile(r"^[0-9a-f]{12,64}$")
RUNTIME_JS = "prefix-runtime.7d3f08d51c2b60f8.bundle.js"
RUNESTONE_JS = "prefix-runestone.bb5ac777721d4056.bundle.js"
ORPHAN_SQL_WASM = "sql-wasm.wasm"
DISABLED_COMPONENTS = ("activecode", "datafile", "hparsons", "timedAssessment")
BLOCKED_CHUNK_IDS = (249, 580)
PATCH_INPUT_SHA256 = {
    RUNTIME_JS: "597146c965da57f8020103dfae89bc9d35a575e091cd710ae5102e9cb2d68367",
    f"{RUNTIME_JS}.gz": "f1b0f2e0c5a864363e83579d7b6982eb6d48834c09c36ce6a391788dde05a77d",
    RUNESTONE_JS: "fb70c1a2ecafba862945fd84ff3e514753f4eeb62655b5a07b54c50538de01e4",
    f"{RUNESTONE_JS}.gz": "1a93020855729cd6c307cbb2b7a3fa789d1ee1230ec9da72ad8856e1f30eec34",
}
STALE_MODIFIED_MAPS = {
    f"{RUNTIME_JS}.map": "7647159d7e989609ae63f10e27de931ac8089ad3eacff47581978a92860fa674",
    f"{RUNTIME_JS}.map.gz": "34778291083c4d6a8fa7b45dc768f5906eb9d8d44a46fd04a97aa74afc49ca2a",
    f"{RUNESTONE_JS}.map": "a5ddb183fd6e213da734717bf816c98452f1cc89aff67e49d53330575e7463ef",
    f"{RUNESTONE_JS}.map.gz": "0a6066162c2b81975e93793fd05128454d45d0348aa652301dcca3c37569c8dd",
}
ORPHAN_SQL_WASM_SHA256 = "962d056e419e3fa5cb2b1cc1a781b7dbf7e5c958341606310b07746e054f3294"
REMEDIATION_RECEIPT = LANE_ROOT / "qa" / "RUNESTONE_OPEN_RUNTIME_REMEDIATION_20260822.json"
DANGLING_MAP_HINT_INPUT_SHA256 = {
    "pretext/js/dist/knowl.js": "f429723c31ed42797a8455a14d5d2ed0d7e630f0d9117b2df4e5d472a36ad6d1",
    "pretext/js/dist/lti_iframe_resizer.js": "23aad08ebe66594020606025b71d3c3dd444e31b5376225a4df6c1275a500cb9",
    "pretext/js/dist/mathjax_startup.js": "6bbd24969fc7e70688a57d2d0f85543f91db3fe9f5fe1372348b7130f38f7931",
    "pretext/js/dist/pretext-core.js": "bee0e02ea04c78704fd8382bd2c00195ff4ca68429322f8542a793a6e5c509f5",
    "pretext/js/dist/pretext-read-aloud.js": "0998765398390ee9aa35ffe7e9476a7e5b2d142c99e461bf5b4cf4789d866ac5",
    "pretext/js/dist/pretext-webwork.js": "25529fdbb3db5a55bcbd024c3df89243ce922fb52f5ba409dcbf2ae763ed9b5a",
    "pretext/js/dist/pretext_search.js": "7e1e1e44641cbb3b60328f6ac232b71c2ed7c6e1b3b96ce4e838632dc965a163",
    "pretext/js/dist/ptx_scorm_events.js": "d774d7da0617134333fac1f0c8af3f1944e574523f04275f2a775f8ad0d2e374",
    "pretext/js/dist/pretext-stack/stackapicalls.js": "a377a2fe90c253b8f76a00b8b37ea606518cf11d4f4cea78c8a9058cf2ac3d02",
    "pretext/js/dist/pretext-stack/stackjsvle.js": "aad75addb6c825a8ea94e99d71ba6ae2b47147b71cf37d8f76eb2a87c3ca9d10",
    "pretext/js/dist/prism/gdscript-prism.js": "6af5af6996bc8111f93d49a434dc48573f34983aefb8fddd0c7f7c542a304824",
}


class PruningError(RuntimeError):
    """Raised when the release-copy pruning gate cannot be proven."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ordinal_key(value: str) -> bytes:
    return value.encode("utf-8")


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def manifest_sha256(records: Iterable[dict[str, Any]]) -> str:
    payload = "".join(
        f"{row['path']}\t{row['bytes']}\t{row['sha256']}\n"
        for row in sorted(records, key=lambda row: ordinal_key(row["path"]))
    ).encode("utf-8")
    return sha256_bytes(payload)


def tree_records(root: Path) -> list[dict[str, Any]]:
    return [
        file_record(path, root)
        for path in sorted(
            (candidate for candidate in root.rglob("*") if candidate.is_file()),
            key=lambda candidate: ordinal_key(candidate.relative_to(root).as_posix()),
        )
    ]


def require_inventory(
    records: list[dict[str, Any]],
    expected: dict[str, Any],
    label: str,
) -> None:
    actual = {
        "count": len(records),
        "bytes": sum(int(row["bytes"]) for row in records),
        "manifest_sha256": manifest_sha256(records),
    }
    wanted = {
        "count": expected.get("count"),
        "bytes": expected.get("bytes"),
        "manifest_sha256": expected.get("manifest_sha256"),
    }
    if actual != wanted:
        raise PruningError(f"{label} inventory differs from the pinned witness: {actual} != {wanted}")


def ensure_beneath(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PruningError(f"{label} escapes its allowed root: {path}") from exc
    return resolved


def load_witness() -> tuple[dict[str, Any], Path, bytes]:
    config = json.loads(BACKEND_CONFIG.read_text(encoding="utf-8"))
    witness_rel = config.get("rights_qa_witness")
    if not isinstance(witness_rel, str) or not witness_rel:
        raise PruningError("Backend config lacks rights_qa_witness")
    witness_path = ensure_beneath(LANE_ROOT / witness_rel, LANE_ROOT, "rights witness")
    raw = witness_path.read_bytes()
    if (
        len(raw) != config.get("rights_qa_witness_bytes")
        or sha256_bytes(raw) != config.get("rights_qa_witness_sha256")
    ):
        raise PruningError("Rights witness fails the backend config's exact size/SHA-256 gate")
    try:
        witness = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PruningError("Rights witness is not valid UTF-8 JSON") from exc
    if witness.get("artifact", {}).get("path") != witness_rel:
        raise PruningError("Rights witness self-identity differs from backend config")
    if not any(
        isinstance(row, dict)
        and row.get("blocker") == "Handsontable 7.2.2 restrictive license"
        for row in witness.get("unresolved_blockers", [])
    ):
        raise PruningError("Rights witness no longer records the Handsontable blocker")
    return witness, witness_path, raw


def exact_static_path(static: Path, name: str, label: str) -> Path:
    if not name or Path(name).name != name or "/" in name or "\\" in name:
        raise PruningError(f"{label} is not an exact top-level _static basename: {name!r}")
    path = static / name
    ensure_beneath(path, static, label)
    if not path.is_file():
        raise PruningError(f"{label} is missing: {path}")
    return path


def replace_once(raw: bytes, old: bytes, new: bytes, label: str) -> bytes:
    count = raw.count(old)
    if count != 1:
        raise PruningError(f"Expected exactly one {label} patch site, found {count}")
    return raw.replace(old, new, 1)


def patch_runtime_javascript(raw: bytes) -> bytes:
    if sha256_bytes(raw) != PATCH_INPUT_SHA256[RUNTIME_JS]:
        raise PruningError("Active webpack runtime differs from the exact reviewed patch input")
    patched = replace_once(
        raw,
        b"d.e=e=>Promise.all(Object.keys(d.f).reduce",
        b'd.e=e=>249===e||580===e?Promise.reject(new Error("Disabled non-open Runestone chunk")):Promise.all(Object.keys(d.f).reduce',
        "blocked-chunk guard",
    )
    for old in (
        b',249:"7ec032cf0b3ede9a"',
        b',580:"28428521d8f13ec7"',
        b',249:"6ca19da539a8ed1a"',
        b',580:"22958d4327b0425a"',
        b",249:1",
        b",580:1",
    ):
        patched = replace_once(patched, old, b"", f"runtime mapping {old!r}")
    patched = replace_once(
        patched,
        f"\n//# sourceMappingURL={RUNTIME_JS}.map".encode("ascii"),
        b"\n",
        "stale runtime source-map reference",
    )
    for token in (
        b"7ec032cf0b3ede9a",
        b"28428521d8f13ec7",
        b"6ca19da539a8ed1a",
        b"22958d4327b0425a",
    ):
        if token in patched:
            raise PruningError(f"Forbidden chunk hash survived runtime patch: {token!r}")
    guard = b'249===e||580===e?Promise.reject(new Error("Disabled non-open Runestone chunk"))'
    if patched.count(guard) != 1:
        raise PruningError("Blocked-chunk guard is not exact after runtime patch")
    return patched


def patch_runestone_javascript(raw: bytes) -> bytes:
    if sha256_bytes(raw) != PATCH_INPUT_SHA256[RUNESTONE_JS]:
        raise PruningError("Active Runestone entrypoint differs from the exact reviewed patch input")
    replacements = {
        b"activecode:()=>Promise.all([n.e(249),n.e(428),n.e(764),n.e(717)]).then(n.bind(n,87257))": b'activecode:()=>Promise.reject(new Error("Runestone component disabled in open release: activecode"))',
        b"datafile:()=>n.e(580).then(n.bind(n,33580))": b'datafile:()=>Promise.reject(new Error("Runestone component disabled in open release: datafile"))',
        b"hparsons:()=>Promise.all([n.e(249),n.e(583),n.e(49)]).then(n.bind(n,97401))": b'hparsons:()=>Promise.reject(new Error("Runestone component disabled in open release: hparsons"))',
        b"timedAssessment:()=>Promise.all([n.e(249),n.e(428),n.e(764),n.e(717),n.e(420),n.e(139),n.e(349),n.e(919),n.e(566),n.e(529),n.e(662),n.e(819),n.e(506)]).then(n.bind(n,46424))": b'timedAssessment:()=>Promise.reject(new Error("Runestone component disabled in open release: timedAssessment"))',
    }
    patched = raw
    for old, new in replacements.items():
        patched = replace_once(patched, old, new, f"disabled component loader {new!r}")
    patched = replace_once(
        patched,
        f"\n//# sourceMappingURL={RUNESTONE_JS}.map".encode("ascii"),
        b"\n",
        "stale Runestone source-map reference",
    )
    for chunk_id in BLOCKED_CHUNK_IDS:
        if f".e({chunk_id})".encode("ascii") in patched:
            raise PruningError(f"Blocked dynamic chunk call survived Runestone patch: {chunk_id}")
    for component in DISABLED_COMPONENTS:
        marker = f"Runestone component disabled in open release: {component}".encode("ascii")
        if patched.count(marker) != 1:
            raise PruningError(f"Disabled component marker is not exact: {component}")
    return patched


def build_replacements(static: Path) -> tuple[dict[Path, bytes], list[dict[str, Any]]]:
    originals: dict[str, bytes] = {}
    for name, expected_sha in PATCH_INPUT_SHA256.items():
        path = exact_static_path(static, name, "reviewed runtime patch input")
        raw = path.read_bytes()
        if sha256_bytes(raw) != expected_sha:
            raise PruningError(f"Runtime patch input identity mismatch: {name}")
        originals[name] = raw
    if gzip.decompress(originals[f"{RUNTIME_JS}.gz"]) != originals[RUNTIME_JS]:
        raise PruningError("Runtime gzip does not decode to the reviewed runtime JS")
    if gzip.decompress(originals[f"{RUNESTONE_JS}.gz"]) != originals[RUNESTONE_JS]:
        raise PruningError("Runestone gzip does not decode to the reviewed Runestone JS")

    patched_runtime = patch_runtime_javascript(originals[RUNTIME_JS])
    patched_runestone = patch_runestone_javascript(originals[RUNESTONE_JS])
    replacement_by_name = {
        RUNTIME_JS: patched_runtime,
        f"{RUNTIME_JS}.gz": gzip.compress(patched_runtime, compresslevel=9, mtime=0),
        RUNESTONE_JS: patched_runestone,
        f"{RUNESTONE_JS}.gz": gzip.compress(patched_runestone, compresslevel=9, mtime=0),
    }
    replacements = {static / name: raw for name, raw in replacement_by_name.items()}
    summary: list[dict[str, Any]] = []
    for name in sorted(replacement_by_name, key=ordinal_key):
        before = originals[name]
        after = replacement_by_name[name]
        summary.append({
            "path": f"{STATIC_DIRNAME}/{name}",
            "input_bytes": len(before),
            "input_sha256": sha256_bytes(before),
            "output_bytes": len(after),
            "output_sha256": sha256_bytes(after),
            "operation": "exact fail-closed loader/mapping patch" if name.endswith(".js") else "deterministic gzip of patched JS (mtime=0)",
            "scope": "runestone-active-runtime",
        })

    for rel, expected_sha in sorted(DANGLING_MAP_HINT_INPUT_SHA256.items(), key=lambda item: ordinal_key(item[0])):
        path = ensure_beneath(static / rel, static, "PreTeXt dangling-map patch input")
        if not path.is_file():
            raise PruningError(f"PreTeXt dangling-map patch input is missing: {rel}")
        before = path.read_bytes()
        if sha256_bytes(before) != expected_sha:
            raise PruningError(f"PreTeXt dangling-map patch input identity mismatch: {rel}")
        marker = f"//# sourceMappingURL={Path(rel).name}.map\n".encode("ascii")
        if not before.endswith(marker) or before.count(marker) != 1:
            raise PruningError(f"PreTeXt dangling source-map hint is not exact: {rel}")
        after = before[: -len(marker)]
        replacements[path] = after
        summary.append({
            "path": f"{STATIC_DIRNAME}/{rel}",
            "input_bytes": len(before),
            "input_sha256": sha256_bytes(before),
            "output_bytes": len(after),
            "output_sha256": sha256_bytes(after),
            "operation": "remove one exact dangling non-executable sourceMappingURL comment",
            "scope": "pretext-core-runtime",
        })
    summary.sort(key=lambda row: ordinal_key(row["path"]))
    return replacements, summary


def build_removal_set(
    source: Path,
    witness: dict[str, Any],
) -> tuple[set[Path], dict[str, Any]]:
    static = source / STATIC_DIRNAME
    if not static.is_dir():
        raise PruningError(f"HTML source lacks {STATIC_DIRNAME}: {source}")

    inventories = witness["runestone_8_2_7"]["inventories"]
    families = witness["handsontable"]["prunable_families"]

    family_paths: dict[str, list[Path]] = {}
    for key in ("249_handsontable_and_sql_vendor_family", "580_datafile_loader_family"):
        names = families[key].get("files")
        if not isinstance(names, list) or not names:
            raise PruningError(f"Rights witness lacks the exact {key} file list")
        paths = [exact_static_path(static, name, key) for name in names]
        records = [file_record(path, static) for path in paths]
        require_inventory(records, families[key], key)
        family_paths[key] = paths

    stale_names = inventories.get("stale_8_2_6_regular_files")
    if not isinstance(stale_names, list) or not stale_names:
        raise PruningError("Rights witness lacks the exact stale 8.2.6 file list")
    stale_paths = [
        exact_static_path(static, name, "stale 8.2.6 asset")
        for name in stale_names
    ]
    require_inventory(
        [file_record(path, static) for path in stale_paths],
        inventories["stale_8_2_6_regular"],
        "stale 8.2.6 regular",
    )

    appledouble_paths = sorted(
        (path for path in source.rglob("*") if path.is_file() and path.name.startswith("._")),
        key=lambda path: ordinal_key(path.relative_to(source).as_posix()),
    )
    outside_static = [path for path in appledouble_paths if path.parent.resolve() != static.resolve()]
    if outside_static:
        raise PruningError(
            "AppleDouble files outside the proven top-level _static inventory: "
            + ", ".join(path.relative_to(source).as_posix() for path in outside_static)
        )
    require_inventory(
        [file_record(path, static) for path in appledouble_paths],
        inventories["all_local_appledouble"],
        "all local AppleDouble",
    )

    stale_map_paths: list[Path] = []
    for name, expected_sha in STALE_MODIFIED_MAPS.items():
        path = exact_static_path(static, name, "stale source map for patched entrypoint")
        if sha256_file(path) != expected_sha:
            raise PruningError(f"Modified-entrypoint source map identity mismatch: {name}")
        stale_map_paths.append(path)

    orphan_sql_wasm = exact_static_path(static, ORPHAN_SQL_WASM, "orphan sql.js WASM")
    if sha256_file(orphan_sql_wasm) != ORPHAN_SQL_WASM_SHA256:
        raise PruningError("sql-wasm.wasm identity differs from the pinned rights witness")

    removal_paths = set(stale_paths) | set(appledouble_paths) | set(stale_map_paths) | {orphan_sql_wasm}
    for paths in family_paths.values():
        removal_paths.update(paths)
    if len(removal_paths) != len(stale_paths) + len(appledouble_paths) + len(stale_map_paths) + 1 + sum(
        len(paths) for paths in family_paths.values()
    ):
        raise PruningError("Pinned removal classes overlap unexpectedly")

    summary = {
        "appledouble": {
            "count": len(appledouble_paths),
            "bytes": sum(path.stat().st_size for path in appledouble_paths),
        },
        "handsontable_249": {
            "count": len(family_paths["249_handsontable_and_sql_vendor_family"]),
            "bytes": sum(
                path.stat().st_size
                for path in family_paths["249_handsontable_and_sql_vendor_family"]
            ),
        },
        "datafile_580": {
            "count": len(family_paths["580_datafile_loader_family"]),
            "bytes": sum(
                path.stat().st_size
                for path in family_paths["580_datafile_loader_family"]
            ),
        },
        "stale_8_2_6": {
            "count": len(stale_paths),
            "bytes": sum(path.stat().st_size for path in stale_paths),
        },
        "stale_maps_for_patched_entrypoints": {
            "count": len(stale_map_paths),
            "bytes": sum(path.stat().st_size for path in stale_map_paths),
            "files": [path.name for path in sorted(stale_map_paths, key=lambda item: ordinal_key(item.name))],
        },
        "orphan_sql_wasm": {
            "count": 1,
            "bytes": orphan_sql_wasm.stat().st_size,
            "files": [ORPHAN_SQL_WASM],
        },
    }
    summary["total"] = {
        "count": len(removal_paths),
        "bytes": sum(path.stat().st_size for path in removal_paths),
    }
    return removal_paths, summary


def reference_tokens(
    source: Path,
    removal_paths: set[Path],
    witness: dict[str, Any],
) -> dict[bytes, set[str]]:
    family_names = {
        name
        for family in witness["handsontable"]["prunable_families"].values()
        for name in family["files"]
    }
    stale_names = set(
        witness["runestone_8_2_7"]["inventories"]["stale_8_2_6_regular_files"]
    )
    tokens: dict[bytes, set[str]] = {}
    for name in sorted(family_names | stale_names, key=ordinal_key):
        tokens.setdefault(name.encode("utf-8"), set()).add(name)
        for piece in name.split("."):
            if HASH_TOKEN_RE.fullmatch(piece):
                tokens.setdefault(piece.encode("ascii"), set()).add(name)
    for path in removal_paths:
        if path.name != ORPHAN_SQL_WASM:
            tokens.setdefault(path.name.encode("utf-8"), set()).add(
                path.relative_to(source).as_posix()
            )
    return tokens


def scan_references(
    source: Path,
    removal_paths: set[Path],
    witness: dict[str, Any],
    replacements: dict[Path, bytes] | None = None,
    candidate_paths: Iterable[Path] | None = None,
) -> list[dict[str, Any]]:
    replacements = replacements or {}
    tokens = reference_tokens(source, removal_paths, witness)
    token_pattern = re.compile(
        b"|".join(re.escape(token) for token in sorted(tokens, key=lambda item: (-len(item), item)))
    )
    hits: dict[tuple[str, str, str], set[str]] = {}
    candidates = candidate_paths if candidate_paths is not None else source.rglob("*")
    retained_files = [
        path
        for path in candidates
        if path.is_file()
        and path.resolve() not in removal_paths
        and (
            path.name.lower().endswith((".html", ".js", ".css", ".map", ".xml", ".json", ".txt", ".svg", ".gz"))
            or path.name in {"LICENSE", "COPYING"}
        )
    ]
    for path in retained_files:
        raw = replacements.get(path, path.read_bytes())
        payloads = [("raw", raw)]
        if path.suffix.lower() == ".gz":
            try:
                payloads.append(("gzip-decoded", gzip.decompress(raw)))
            except (gzip.BadGzipFile, EOFError, OSError) as exc:
                raise PruningError(f"Cannot inspect retained gzip payload: {path}") from exc
        for mode, payload in payloads:
            rel = path.relative_to(source).as_posix()
            for token in set(token_pattern.findall(payload)):
                key = (rel, token.decode("utf-8"), mode)
                hits.setdefault(key, set()).update(tokens[token])
    return [
        {
            "retained_path": path,
            "token": token,
            "scan_mode": mode,
            "removed_assets": sorted(assets, key=ordinal_key),
        }
        for (path, token, mode), assets in sorted(
            hits.items(),
            key=lambda row: (
                ordinal_key(row[0][0]),
                ordinal_key(row[0][1]),
                ordinal_key(row[0][2]),
            ),
        )
    ]


def html_component_counts(source: Path) -> dict[str, int]:
    data_component = re.compile(rb"""data-component\s*=\s*["'][^"']+["']""")
    datafile = re.compile(rb"""data-component\s*=\s*["']datafile["']""")
    disabled = re.compile(
        rb"""data-component\s*=\s*["'](?:activecode|datafile|hparsons|timedAssessment)["']"""
    )
    webwork = re.compile(rb"""class\s*=\s*["'][^"']*\bwebwork-button\b[^"']*["']""")
    counts = {
        "data_component_attributes": 0,
        "datafile_components": 0,
        "disabled_component_attributes": 0,
        "webwork_buttons": 0,
    }
    for path in source.rglob("*.html"):
        raw = path.read_bytes()
        counts["data_component_attributes"] += len(data_component.findall(raw))
        counts["datafile_components"] += len(datafile.findall(raw))
        counts["disabled_component_attributes"] += len(disabled.findall(raw))
        counts["webwork_buttons"] += len(webwork.findall(raw))
    return counts


def is_request_capable(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".map") or name.endswith(".map.gz"):
        return False
    return any(name.endswith(suffix) for suffix in (".html", ".js", ".css", ".xml", ".html.gz", ".js.gz", ".css.gz", ".xml.gz"))


def scan_orphan_wasm_requests(
    source: Path,
    removal_paths: set[Path],
    replacements: dict[Path, bytes],
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for path in source.rglob("*"):
        if not path.is_file() or path in removal_paths or not is_request_capable(path):
            continue
        raw = replacements.get(path, path.read_bytes())
        payloads = [("raw", raw)]
        if path.name.lower().endswith(".gz"):
            try:
                payloads.append(("gzip-decoded", gzip.decompress(raw)))
            except (gzip.BadGzipFile, EOFError, OSError) as exc:
                raise PruningError(f"Cannot inspect retained request-capable gzip: {path}") from exc
        for mode, payload in payloads:
            if ORPHAN_SQL_WASM.encode("ascii") in payload:
                hits.append({
                    "retained_path": path.relative_to(source).as_posix(),
                    "token": ORPHAN_SQL_WASM,
                    "scan_mode": mode,
                })
    return hits


def parse_chunk_mapping(raw: bytes, pattern: bytes, label: str) -> dict[int, str]:
    match = re.search(pattern, raw)
    if not match:
        raise PruningError(f"Cannot locate patched webpack {label} mapping")
    entries = {
        int(chunk): digest.decode("ascii")
        for chunk, digest in re.findall(rb'(\d+):"([0-9a-f]+)"', match.group(1))
    }
    if not entries:
        raise PruningError(f"Patched webpack {label} mapping is empty")
    return entries


def runtime_request_closure(
    source: Path,
    removal_paths: set[Path],
    replacements: dict[Path, bytes],
    component_counts: dict[str, int],
) -> dict[str, Any]:
    static = source / STATIC_DIRNAME
    runtime_path = static / RUNTIME_JS
    runestone_path = static / RUNESTONE_JS
    runtime = replacements.get(runtime_path, runtime_path.read_bytes())
    runestone = replacements.get(runestone_path, runestone_path.read_bytes())
    errors: list[str] = []

    guard = b'249===e||580===e?Promise.reject(new Error("Disabled non-open Runestone chunk"))'
    if runtime.count(guard) != 1:
        errors.append("The exact central blocked-chunk rejection guard is absent or duplicated.")
    for chunk_id in BLOCKED_CHUNK_IDS:
        if f".e({chunk_id})".encode("ascii") in runestone:
            errors.append(f"Runestone entrypoint retains a dynamic request for blocked chunk {chunk_id}.")
    for component in DISABLED_COMPONENTS:
        marker = f"Runestone component disabled in open release: {component}".encode("ascii")
        if runestone.count(marker) != 1:
            errors.append(f"The {component} loader is not replaced by its exact fail-closed stub.")
    if component_counts["disabled_component_attributes"]:
        errors.append("Emitted HTML contains a component whose loader is disabled by the open-release patch.")

    js_mapping = parse_chunk_mapping(
        runtime,
        rb'd\.u=e=>e\+"\."\+\{([^}]*)\}\[e\]\+"\.js"',
        "JavaScript chunk",
    )
    css_mapping = parse_chunk_mapping(
        runtime,
        rb'd\.miniCssF=e=>"prefix-"\+e\+"\."\+\{([^}]*)\}\[e\]\+"\.css"',
        "CSS chunk",
    )
    for chunk_id in BLOCKED_CHUNK_IDS:
        if chunk_id in js_mapping or chunk_id in css_mapping:
            errors.append(f"Blocked chunk {chunk_id} remains in a patched webpack filename mapping.")

    unresolved_dynamic: list[str] = []
    for chunk_id, digest in sorted(js_mapping.items()):
        name = f"{chunk_id}.{digest}.js"
        path = static / name
        if path in removal_paths or not path.is_file():
            unresolved_dynamic.append(name)
    for chunk_id, digest in sorted(css_mapping.items()):
        name = f"prefix-{chunk_id}.{digest}.css"
        path = static / name
        if path in removal_paths or not path.is_file():
            unresolved_dynamic.append(name)
    if unresolved_dynamic:
        errors.append("Mapped retained chunks are missing: " + ", ".join(unresolved_dynamic))

    html_static_refs: set[str] = set()
    unresolved_html: list[dict[str, str]] = []
    attr = re.compile(rb'(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.I)
    for html_path in source.rglob("*.html"):
        raw = replacements.get(html_path, html_path.read_bytes())
        for encoded in attr.findall(raw):
            value = encoded.decode("utf-8", errors="strict")
            split = urlsplit(value)
            if split.scheme or split.netloc or not split.path:
                continue
            local = unquote(split.path)
            if not local.startswith(f"{STATIC_DIRNAME}/") and f"/{STATIC_DIRNAME}/" not in local:
                continue
            candidate = (html_path.parent / local).resolve()
            try:
                rel = candidate.relative_to(source).as_posix()
            except ValueError:
                unresolved_html.append({"html": html_path.relative_to(source).as_posix(), "reference": value})
                continue
            html_static_refs.add(rel)
            if candidate in removal_paths or not candidate.is_file():
                unresolved_html.append({"html": html_path.relative_to(source).as_posix(), "reference": value})
    if unresolved_html:
        errors.append(f"{len(unresolved_html)} emitted HTML runtime references do not resolve after pruning.")

    unresolved_source_maps: list[dict[str, str]] = []
    source_map_re = re.compile(rb"sourceMappingURL=([^\s*]+)")
    for path in source.rglob("*"):
        if not path.is_file() or path in removal_paths or path.suffix.lower() not in {".js", ".css"}:
            continue
        raw = replacements.get(path, path.read_bytes())
        for encoded in source_map_re.findall(raw):
            value = encoded.decode("utf-8", errors="strict")
            if value.startswith("data:"):
                continue
            candidate = (path.parent / unquote(urlsplit(value).path)).resolve()
            if candidate in removal_paths or not candidate.is_file():
                unresolved_source_maps.append({"asset": path.relative_to(source).as_posix(), "reference": value})
    if unresolved_source_maps:
        errors.append(f"{len(unresolved_source_maps)} retained sourceMappingURL references do not resolve.")

    orphan_wasm_requests = scan_orphan_wasm_requests(source, removal_paths, replacements)
    if orphan_wasm_requests:
        errors.append("A retained executable/runtime surface still requests orphan sql-wasm.wasm.")

    return {
        "result": "pass" if not errors else "fail",
        "errors": errors,
        "central_blocked_chunk_guard_count": runtime.count(guard),
        "disabled_component_loader_count": sum(
            runestone.count(f"Runestone component disabled in open release: {name}".encode("ascii"))
            for name in DISABLED_COMPONENTS
        ),
        "disabled_component_html_count": component_counts["disabled_component_attributes"],
        "retained_js_chunk_mapping_count": len(js_mapping),
        "retained_css_chunk_mapping_count": len(css_mapping),
        "blocked_chunk_mapping_count": sum(chunk in js_mapping or chunk in css_mapping for chunk in BLOCKED_CHUNK_IDS),
        "mapped_retained_chunk_missing_count": len(unresolved_dynamic),
        "mapped_retained_chunk_missing": unresolved_dynamic,
        "distinct_emitted_html_static_reference_count": len(html_static_refs),
        "unresolved_emitted_html_static_reference_count": len(unresolved_html),
        "unresolved_emitted_html_static_references": unresolved_html,
        "unresolved_retained_source_map_reference_count": len(unresolved_source_maps),
        "unresolved_retained_source_map_references": unresolved_source_maps,
        "orphan_sql_wasm_executable_reference_count": len(orphan_wasm_requests),
        "orphan_sql_wasm_executable_references": orphan_wasm_requests,
    }


def source_snapshot(source: Path) -> dict[str, Any]:
    records = tree_records(source)
    return {
        "count": len(records),
        "bytes": sum(int(row["bytes"]) for row in records),
        "manifest_sha256": manifest_sha256(records),
        "records": records,
    }


def projected_records(
    source: Path,
    source_before: dict[str, Any],
    removal_paths: set[Path],
    replacements: dict[Path, bytes],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in source_before["records"]:
        source_path = (source / row["path"]).resolve()
        if source_path in removal_paths:
            continue
        if source_path in replacements:
            replacement = replacements[source_path]
            records.append({
                "path": row["path"],
                "bytes": len(replacement),
                "sha256": sha256_bytes(replacement),
            })
        else:
            records.append(row)
    return records


def copy_without_removals(
    source: Path,
    destination: Path,
    removal_paths: set[Path],
    replacements: dict[Path, bytes],
    source_before: dict[str, Any],
) -> dict[str, Any]:
    if destination.exists():
        raise PruningError(f"Destination already exists; refusing to overwrite: {destination}")
    destination_parent = destination.parent.resolve()
    if not destination_parent.is_dir():
        raise PruningError(f"Destination parent does not exist: {destination_parent}")
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise PruningError("Destination and canonical source overlap")

    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination_parent))
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True, copy_function=shutil.copy2)
        for source_path in sorted(
            removal_paths,
            key=lambda path: ordinal_key(path.relative_to(source).as_posix()),
        ):
            staged_path = stage / source_path.relative_to(source)
            if not staged_path.is_file():
                raise PruningError(f"Staged removal target is missing: {staged_path}")
            staged_path.unlink()

        for source_path, replacement in sorted(
            replacements.items(),
            key=lambda item: ordinal_key(item[0].relative_to(source).as_posix()),
        ):
            staged_path = stage / source_path.relative_to(source)
            if not staged_path.is_file():
                raise PruningError(f"Staged patch target is missing: {staged_path}")
            staged_path.write_bytes(replacement)

        expected_records = projected_records(source, source_before, removal_paths, replacements)
        actual_records = tree_records(stage)
        if actual_records != expected_records:
            raise PruningError("Pruned staged tree differs from the exact source-minus-removals set")
        source_after_copy = source_snapshot(source)
        if source_after_copy != source_before:
            raise PruningError("Canonical HTML source changed during release-copy preparation")
        if destination.exists():
            raise PruningError(f"Destination appeared during staging; refusing to overwrite: {destination}")
        os.replace(stage, destination)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise

    return {
        "destination": str(destination),
        "files": len(actual_records),
        "bytes": sum(int(row["bytes"]) for row in actual_records),
        "manifest_sha256": manifest_sha256(actual_records),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=CANONICAL_HTML,
        help="Canonical HTML tree; must resolve to this lane's source/output/html",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        help="Nonexistent destination for the pruned copy; required unless --check-only",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate inventories and references without creating a copy",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Optional JSON receipt path beneath this lane's qa directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if source != CANONICAL_HTML:
        raise PruningError(f"Source must be the exact canonical HTML tree: {CANONICAL_HTML}")
    if not source.is_dir():
        raise PruningError(f"Canonical HTML tree is missing: {source}")
    if args.check_only and args.destination is not None:
        raise PruningError("--destination is not accepted with --check-only")
    if not args.check_only and args.destination is None:
        raise PruningError("--destination is required unless --check-only is used")

    receipt_path: Path | None = None
    if args.receipt is not None:
        candidate = args.receipt if args.receipt.is_absolute() else LANE_ROOT / args.receipt
        receipt_path = ensure_beneath(candidate, LANE_ROOT / "qa", "runtime remediation receipt")
        if receipt_path.suffix.lower() != ".json":
            raise PruningError("Runtime remediation receipt must be a JSON file beneath qa")

    witness, witness_path, witness_raw = load_witness()
    component_rights_path = LANE_ROOT / "00_control" / "COMPONENT_RIGHTS.csv"
    component_rights_raw = component_rights_path.read_bytes()
    for required in (b"R012-RUNESTONE,", b"R012-RUNESTONE-3P,", b"publication_blocker"):
        if required not in component_rights_raw:
            raise PruningError(f"Component-rights control lacks required marker: {required!r}")
    source_before = source_snapshot(source)
    removals, removal_summary = build_removal_set(source, witness)
    replacements, patch_summary = build_replacements(source / STATIC_DIRNAME)
    component_counts = html_component_counts(source)
    pre_patch_candidates = [source / STATIC_DIRNAME / name for name in PATCH_INPUT_SHA256]
    pre_patch_references = scan_references(
        source,
        removals,
        witness,
        candidate_paths=pre_patch_candidates,
    )
    post_patch_references = scan_references(source, removals, witness, replacements)
    request_closure = runtime_request_closure(
        source,
        removals,
        replacements,
        component_counts,
    )
    projected = projected_records(source, source_before, removals, replacements)
    pruning_gate_passed = not post_patch_references and request_closure["result"] == "pass"

    active = witness["runestone_8_2_7"]["inventories"]["active_regular_runtime"]
    active_removed_bytes = (
        removal_summary["handsontable_249"]["bytes"]
        + removal_summary["datafile_580"]["bytes"]
        + removal_summary["stale_maps_for_patched_entrypoints"]["bytes"]
        + removal_summary["orphan_sql_wasm"]["bytes"]
    )
    runestone_patch_delta = sum(
        row["output_bytes"] - row["input_bytes"]
        for row in patch_summary
        if row["scope"] == "runestone-active-runtime"
    )
    pretext_patch_delta = sum(
        row["output_bytes"] - row["input_bytes"]
        for row in patch_summary
        if row["scope"] == "pretext-core-runtime"
    )
    retained_active_count = (
        int(active["count"])
        - removal_summary["handsontable_249"]["count"]
        - removal_summary["datafile_580"]["count"]
        - removal_summary["stale_maps_for_patched_entrypoints"]["count"]
        - removal_summary["orphan_sql_wasm"]["count"]
    )
    retained_active_bytes = int(active["bytes"]) - active_removed_bytes + runestone_patch_delta
    report: dict[str, Any] = {
        "schema": "r012.release-runtime-open-remediation",
        "schema_version": "2.0.0",
        "evidence_date": "2026-08-22",
        "source": str(source),
        "source_files": source_before["count"],
        "source_bytes": source_before["bytes"],
        "source_manifest_sha256": source_before["manifest_sha256"],
        "final_build_status": "not asserted; this check is against the current canonical HTML witness and must be rerun after the final build",
        "rights_witness": witness_path.relative_to(LANE_ROOT).as_posix(),
        "rights_witness_bytes": len(witness_raw),
        "rights_witness_sha256": sha256_bytes(witness_raw),
        "component_rights_control": component_rights_path.relative_to(LANE_ROOT).as_posix(),
        "component_rights_control_bytes": len(component_rights_raw),
        "component_rights_control_sha256": sha256_bytes(component_rights_raw),
        "component_rights_disposition": {
            "current_status": "Keep R012-RUNESTONE and R012-RUNESTONE-3P at publication_blocker while the canonical/final build still contains the unpruned distribution and until notices, source, release-copy, and browser gates pass.",
            "admission_condition": "Only a final release-copy receipt proving this exact transform plus complete notices/corresponding source and browser request/console QA can clear the Handsontable-specific blocker.",
            "control_file_mutated_by_this_check": False,
        },
        "removal_summary": removal_summary,
        "retained_runtime_families": {
            "active_runestone_8_2_7_after_open_release_transform": {
                "count": retained_active_count,
                "bytes": retained_active_bytes,
                "definition": "Pinned active 8.2.7 regular runtime minus families 249/580, obsolete maps for the two patched entrypoints, and orphan sql-wasm.wasm, with four exact patched JS/gzip entrypoint bytes substituted.",
            },
            "patched_runtime_surfaces": {
                "count": len(patch_summary),
                "files": patch_summary,
            },
            "local_reader_runtime": {
                "pretext_core_file_count": witness["pretext_core"]["local_comparison"]["local_file_count"],
                "pretext_core_input_bytes": witness["pretext_core"]["local_comparison"]["local_bytes"],
                "pretext_core_projected_bytes": witness["pretext_core"]["local_comparison"]["local_bytes"] + pretext_patch_delta,
                "runestone_local_specific_file_count": witness["runestone_8_2_7"]["inventories"]["local_specific_non_cdn"]["count"],
                "runestone_local_specific_bytes": witness["runestone_8_2_7"]["inventories"]["local_specific_non_cdn"]["bytes"],
            },
        },
        "projected_release_tree": {
            "files": len(projected),
            "bytes": sum(int(row["bytes"]) for row in projected),
            "manifest_sha256": manifest_sha256(projected),
            "definition": "Exact canonical source tree minus removal set plus all exact replacement byte streams listed in patched_runtime_surfaces.",
        },
        "html_component_counts": component_counts,
        "pre_patch_retained_reference_count": len(pre_patch_references),
        "pre_patch_retained_references": pre_patch_references,
        "post_patch_retained_reference_count": len(post_patch_references),
        "post_patch_retained_references": post_patch_references,
        "request_closure": request_closure,
        "pruning_gate_passed": pruning_gate_passed,
        "copy_created": False,
        "overall_release_ready": False,
        "notices_and_source_obligations": {
            "book_content": "Keep the CC BY-SA 4.0 book attribution/change notice separate from runtime licensing.",
            "pretext_core": "Include GPLv3, the exact PreTeXt COPYING notice and core source snapshot, the Indonesian read-aloud modified source/patch with prominent date/change notice, deterministic locks/build instructions, and the full jQuery 3.3.1 MIT license.",
            "runestone_first_party": "Include GPLv3, Runestone LICENSE.txt, the pinned bccfe5e7ea3cfc03e7bf835fc72d64c4374e08ec source snapshot with lock/config/build files, and this exact pruning script as corresponding patch source; prominently identify the 2026-08-22 open-release runtime modifications.",
            "retained_open_third_party": "Preserve emitted notices and include a conservative complete notice set for all 68 open-license packages listed by the pinned rights witness; later exact retained-package deduplication may reduce but must not omit a required notice.",
            "handsontable": "Handsontable 7.2.2 code, source maps, license payload, and the dependent datafile chunk families 249/580 are absent from the projected release; no Handsontable license/key claim is made.",
            "sql_js": "Remove orphan sql-wasm.wasm together with vendor family 249. Keeping the sql.js MIT notice in the conservative third-party notice set is permitted even if the final executable dependency audit confirms no sql.js payload remains.",
            "modified_source_maps": "Do not distribute the four now-inaccurate source-map/map-gzip files for the patched Runestone entrypoints. Strip the 11 exact dangling PreTeXt sourceMappingURL comments only in the release copy. The pinned upstream source snapshots plus this deterministic patch script supply the modification closure.",
        },
        "exact_next_commands": [
            "python scripts/prune_release_html_runtime.py --check-only --receipt qa/RUNESTONE_OPEN_RUNTIME_REMEDIATION_20260822.json",
            "python scripts/prune_release_html_runtime.py --destination source/output/html-open-release-20260822 --receipt qa/RUNESTONE_OPEN_RUNTIME_RELEASE_COPY_20260822.json",
            "python -m http.server 8765 --directory source/output/html-open-release-20260822",
        ],
        "remaining_release_gates": [
            "Rerun the first command against the final HTML build; any changed runtime identity, forbidden component instance, removed-family reference, missing mapped chunk, or unresolved runtime URL fails closed.",
            "Run the second command only after the final-build check passes; it creates a non-overwriting exact release copy and never edits source/output/html.",
            "Assemble the complete notices/corresponding-source package described above.",
            "Serve the created release copy with the third command and perform browser QA with request and console capture; no request for chunk 249, chunk 580, sql-wasm.wasm, or a missing source map is permitted.",
            "Do not publish until the static gate, release-copy identity, notice/source closure, and browser request/console QA all pass.",
        ],
    }

    if pruning_gate_passed and not args.check_only:
        destination = args.destination.resolve()
        report["copy"] = copy_without_removals(
            source,
            destination,
            removals,
            replacements,
            source_before,
        )
        report["copy_created"] = True

    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if receipt_path is not None:
        receipt_path.write_text(serialized, encoding="utf-8", newline="\n")
        written = receipt_path.read_bytes()
        if written != serialized.encode("utf-8"):
            raise PruningError("Runtime remediation receipt write/readback differs")
    print(serialized, end="")
    return 0 if pruning_gate_passed else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PruningError as exc:
        print(
            json.dumps(
                {
                    "schema": "r012.release-runtime-pruning-check",
                    "schema_version": "1.0.0",
                    "pruning_gate_passed": False,
                    "copy_created": False,
                    "overall_release_ready": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
