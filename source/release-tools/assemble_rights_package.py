#!/usr/bin/env python3
"""Assemble and verify the R012 release rights/corresponding-source package.

This script is deliberately bounded to exact, pinned R012 inputs.  It does not
build a reader, access the network, mutate source PTX/backend/reader files, or
inspect any path outside this lane.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import shutil
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "release" / "rights-and-corresponding-source"
QA_PATH = ROOT / "qa" / "RIGHTS_NOTICE_SOURCE_PACKAGE_QA_20260822_2.json"

PRETEXT_COMMIT = "5836dfcbdc342841acdbe266871a204c8a9dc8cc"
PRETEXT_ZIP = (
    ROOT
    / "tools"
    / "ptx-2.49.1"
    / "Lib"
    / "site-packages"
    / "pretext"
    / "resources"
    / "core.zip"
)
PRETEXT_ZIP_SHA256 = "c67e75545e91e1601ddff51edc69079bf24275cf0a1503cd4057c89c39d5ef3f"
PRETEXT_PREFIX = f"pretext-{PRETEXT_COMMIT}/"

RUNESTONE_COMMIT = "bccfe5e7ea3cfc03e7bf835fc72d64c4374e08ec"
RUNESTONE_ROOT = f"rs-{RUNESTONE_COMMIT}"
RUNESTONE_ARCHIVE = (
    PACKAGE
    / "runestone"
    / "corresponding-source"
    / f"runestone-rs-{RUNESTONE_COMMIT}.tar.gz"
)
RUNESTONE_ARCHIVE_SHA256 = "59076a0e7dea09aab7f0464682132d86abb043d92e88fae0b2981ed5ce221cf4"

OPEN_HTML = ROOT / "source" / "output" / "html-open-release-20260822-2"
CANONICAL_HTML = ROOT / "source" / "output" / "html"

GROUPS = {
    "0BSD": ["tslib@2.4.0"],
    "BSD-3-Clause": [
        "d3-array@2.12.1",
        "d3-collection@1.0.7",
        "d3-color@1.4.1",
        "d3-contour@1.3.2",
        "d3-dispatch@1.0.6",
        "d3-dsv@1.2.0",
        "d3-force@1.2.1",
        "d3-format@1.4.5",
        "d3-geo@1.12.1",
        "d3-hierarchy@1.1.9",
        "d3-interpolate@1.4.0",
        "d3-path@1.0.9",
        "d3-quadtree@1.0.7",
        "d3-scale@2.2.2",
        "d3-scale-chromatic@1.5.0",
        "d3-selection@1.4.2",
        "d3-shape@1.3.7",
        "d3-time-format@2.3.0",
        "d3-time@1.1.0",
        "d3-timer@1.0.10",
        "d3-voronoi@1.1.4",
        "highlight.js@11.7.0",
        "vega-canvas@1.2.6",
        "vega-crossfilter@3.0.1",
        "vega-dataflow@4.1.0",
        "vega-embed@3.14.0",
        "vega-encode@3.2.2",
        "vega-event-selector@2.0.6",
        "vega-expression@2.7.0",
        "vega-force@3.0.0",
        "vega-geo@3.1.1",
        "vega-hierarchy@3.1.0",
        "vega-lib@4.4.0",
        "vega-lite@2.7.0",
        "vega-loader@3.1.0",
        "vega-parser@3.9.0",
        "vega-projection@1.5.0",
        "vega-runtime@3.2.0",
        "vega-scale@2.5.1",
        "vega-scenegraph@3.2.3",
        "vega-schema-url-parser@1.1.0",
        "vega-statistics@1.8.0",
        "vega-themes@2.12.0",
        "vega-tooltip@0.11.0",
        "vega-transforms@2.3.1",
        "vega-util@1.17.0",
        "vega-view-transforms@2.0.3",
        "vega-view@3.4.1",
        "vega-voronoi@3.0.0",
        "vega-wordcloud@3.0.0",
    ],
    "BSD-or-MIT": ["pikaday@1.5.1"],
    "ISC": ["d3-geo-projection@4.0.0", "topojson-client@3.1.0"],
    "MIT": [
        "btm-expressions@0.1.12",
        "byte-base64@1.1.0",
        "codemirror@5.65.8",
        "core-js@3.25.1",
        "hot-formula-parser@3.0.2",
        "jquery-ui@1.10.4",
        "json-stable-stringify@1.0.1",
        "json-stringify-pretty-compact@1.2.0",
        "marked@18.0.2",
        "moment@2.20.1",
        "numbro@2.1.1",
        "sortablejs@1.15.0",
        "sql.js@1.5.0",
    ],
    "Public-Domain": ["jsonify@0.0.0"],
}

MIT_TEXT = """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the \"Software\"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

BSD3_TEXT = """BSD 3-Clause License

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS \"AS IS\"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

BSD2_TEXT = """BSD 2-Clause License

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS \"AS IS\"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

ISC_TEXT = """ISC License

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED \"AS IS\" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE
USE OR PERFORMANCE OF THIS SOFTWARE.
"""

ZERO_BSD_TEXT = """Zero-Clause BSD License (0BSD)

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED \"AS IS\" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE
USE OR PERFORMANCE OF THIS SOFTWARE.
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text.rstrip("\n") + "\n")


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise RuntimeError(f"Missing required input: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def extract_zip_member(archive: zipfile.ZipFile, member: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive.read(member))


def extract_tar_member(archive: tarfile.TarFile, member: str, target: Path) -> None:
    info = archive.getmember(member)
    if not info.isfile():
        raise RuntimeError(f"Required Runestone member is not a regular file: {member}")
    source = archive.extractfile(info)
    if source is None:
        raise RuntimeError(f"Could not read Runestone member: {member}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read())


def make_diff(before: bytes, after: bytes, before_name: str, after_name: str) -> str:
    old = before.decode("utf-8").splitlines(keepends=True)
    new = after.decode("utf-8").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old, new, fromfile=before_name, tofile=after_name, lineterm="\n")
    )


def main() -> None:
    PACKAGE.mkdir(parents=True, exist_ok=True)
    obsolete_evidence = PACKAGE / "evidence" / "RUNESTONE_OPEN_RUNTIME_RELEASE_COPY_20260822.json"
    if obsolete_evidence.exists():
        obsolete_evidence.unlink()
    errors: list[str] = []

    if sha256(PRETEXT_ZIP) != PRETEXT_ZIP_SHA256:
        raise RuntimeError("Pinned PreTeXt core.zip hash mismatch")
    if sha256(RUNESTONE_ARCHIVE) != RUNESTONE_ARCHIVE_SHA256:
        raise RuntimeError("Pinned Runestone source archive hash mismatch")

    copy_file(ROOT / "source" / "LICENSE.md", PACKAGE / "book" / "CC-BY-SA-4.0-LICENSE.txt")
    copy_file(PRETEXT_ZIP, PACKAGE / "pretext" / f"pretext-core-{PRETEXT_COMMIT}.zip")
    copy_file(
        ROOT / "scripts" / "prune_release_html_runtime.py",
        PACKAGE / "runestone" / "patches" / "prune_release_html_runtime.py",
    )
    copy_file(
        ROOT / "qa" / "RUNESTONE_RIGHTS_REMOTE_CLOSURE_20260822.json",
        PACKAGE / "evidence" / "RUNESTONE_RIGHTS_REMOTE_CLOSURE_20260822.json",
    )
    copy_file(
        ROOT / "qa" / "RUNESTONE_OPEN_RUNTIME_RELEASE_COPY_20260822_2.json",
        PACKAGE / "evidence" / "RUNESTONE_OPEN_RUNTIME_RELEASE_COPY_20260822_2.json",
    )
    copy_file(
        ROOT / "00_control" / "COMPONENT_RIGHTS.csv",
        PACKAGE / "evidence" / "COMPONENT_RIGHTS.csv",
    )

    with zipfile.ZipFile(PRETEXT_ZIP) as archive:
        names = set(archive.namelist())
        required = {
            PRETEXT_PREFIX + "COPYING": PACKAGE / "pretext" / "COPYING",
            PRETEXT_PREFIX + "legal/gpl-license-v3.txt": PACKAGE / "licenses" / "GPL-3.0.txt",
            PRETEXT_PREFIX + "js/src/read-aloud/strings.js": PACKAGE / "pretext" / "upstream-source" / "js" / "src" / "read-aloud" / "strings.js",
            PRETEXT_PREFIX + "js/dist/pretext-read-aloud.js": PACKAGE / "pretext" / "upstream-source" / "js" / "dist" / "pretext-read-aloud.js",
            PRETEXT_PREFIX + "script/jsbuilder/package.json": PACKAGE / "pretext" / "build-evidence" / "jsbuilder" / "package.json",
            PRETEXT_PREFIX + "script/jsbuilder/package-lock.json": PACKAGE / "pretext" / "build-evidence" / "jsbuilder" / "package-lock.json",
            PRETEXT_PREFIX + "script/jsbuilder/jsbuilder.mjs": PACKAGE / "pretext" / "build-evidence" / "jsbuilder" / "jsbuilder.mjs",
            PRETEXT_PREFIX + "script/cssbuilder/package.json": PACKAGE / "pretext" / "build-evidence" / "cssbuilder" / "package.json",
            PRETEXT_PREFIX + "script/cssbuilder/package-lock.json": PACKAGE / "pretext" / "build-evidence" / "cssbuilder" / "package-lock.json",
            PRETEXT_PREFIX + "js/jquery.min.js": PACKAGE / "pretext" / "upstream-source" / "js" / "jquery.min.js",
        }
        missing = sorted(set(required) - names)
        if missing:
            raise RuntimeError(f"Missing required PreTeXt archive members: {missing}")
        for member, target in required.items():
            extract_zip_member(archive, member, target)

        upstream_strings = archive.read(PRETEXT_PREFIX + "js/src/read-aloud/strings.js")
        upstream_dist = archive.read(PRETEXT_PREFIX + "js/dist/pretext-read-aloud.js")

    localized_strings_path = (
        OPEN_HTML / "_static" / "pretext" / "js" / "src" / "read-aloud" / "strings.js"
    )
    localized_dist_path = (
        OPEN_HTML / "_static" / "pretext" / "js" / "dist" / "pretext-read-aloud.js"
    )
    copy_file(
        localized_strings_path,
        PACKAGE / "pretext" / "indonesian-modification" / "js" / "src" / "read-aloud" / "strings.js",
    )
    copy_file(
        localized_dist_path,
        PACKAGE / "pretext" / "indonesian-modification" / "js" / "dist" / "pretext-read-aloud.js",
    )
    write_text(
        PACKAGE / "pretext" / "indonesian-modification" / "read-aloud-source.patch",
        make_diff(
            upstream_strings,
            localized_strings_path.read_bytes(),
            f"a/{PRETEXT_PREFIX}js/src/read-aloud/strings.js",
            "b/id-ID/js/src/read-aloud/strings.js",
        ),
    )
    write_text(
        PACKAGE / "pretext" / "indonesian-modification" / "read-aloud-built-output.patch",
        make_diff(
            upstream_dist,
            localized_dist_path.read_bytes(),
            f"a/{PRETEXT_PREFIX}js/dist/pretext-read-aloud.js",
            "b/id-ID/js/dist/pretext-read-aloud.js",
        ),
    )

    runestone_named = {
        "bases/rsptx/interactives/LICENSE.txt": PACKAGE / "runestone" / "LICENSE.txt",
        "bases/rsptx/interactives/package.json": PACKAGE / "runestone" / "build-evidence" / "bases-rsptx-interactives" / "package.json",
        "bases/rsptx/interactives/package-lock.json": PACKAGE / "runestone" / "build-evidence" / "bases-rsptx-interactives" / "package-lock.json",
        "bases/rsptx/interactives/webpack.config.js": PACKAGE / "runestone" / "build-evidence" / "bases-rsptx-interactives" / "webpack.config.js",
        "bases/rsptx/interactives/webpack.index.js": PACKAGE / "runestone" / "build-evidence" / "bases-rsptx-interactives" / "webpack.index.js",
        "projects/interactives/build.py": PACKAGE / "runestone" / "build-evidence" / "projects-interactives" / "build.py",
        "projects/interactives/pyproject.toml": PACKAGE / "runestone" / "build-evidence" / "projects-interactives" / "pyproject.toml",
    }
    with tarfile.open(RUNESTONE_ARCHIVE, "r:gz") as archive:
        members = archive.getmembers()
        roots = sorted({member.name.split("/")[0] for member in members})
        if roots != [RUNESTONE_ROOT]:
            raise RuntimeError(f"Runestone archive root mismatch: {roots}")
        for relative, target in runestone_named.items():
            extract_tar_member(archive, f"{RUNESTONE_ROOT}/{relative}", target)
        tar_stats = {
            "members": len(members),
            "regular_files": sum(member.isfile() for member in members),
            "regular_file_bytes": sum(member.size for member in members if member.isfile()),
            "root": RUNESTONE_ROOT,
        }

    for name, expected in {
        "prefix-runestone.bb5ac777721d4056.bundle.js.map": "a5ddb183fd6e213da734717bf816c98452f1cc89aff67e49d53330575e7463ef",
        "prefix-runestone.efe427683fc41f98.css.map": "858ca1bbdb8c96f03c89c5473e23917dbf735a03ded11dafc169a35ec18204b9",
    }.items():
        source = CANONICAL_HTML / "_static" / name
        if sha256(source) != expected:
            raise RuntimeError(f"Pinned Runestone source-map hash mismatch: {name}")
        copy_file(source, PACKAGE / "runestone" / "source-map-identity-evidence" / name)

    fragments_dir = OPEN_HTML / "_static"
    fragment_names = sorted(path.name for path in fragments_dir.glob("*.LICENSE.txt"))
    if not fragment_names:
        raise RuntimeError("No emitted Runestone license fragments found")
    for name in fragment_names:
        copy_file(fragments_dir / name, PACKAGE / "third-party" / "emitted-fragments" / name)

    all_packages = sorted(package for packages in GROUPS.values() for package in packages)
    if len(all_packages) != 68 or len(set(all_packages)) != 68:
        raise RuntimeError("Retained open package inventory is not exactly 68 unique packages")
    if any(package.startswith("handsontable@") for package in all_packages):
        raise RuntimeError("Handsontable must not appear in the retained open package inventory")

    lock_path = PACKAGE / "runestone" / "build-evidence" / "bases-rsptx-interactives" / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_packages = lock["packages"]
    rows = []
    for license_name in sorted(GROUPS):
        for package_id in sorted(GROUPS[license_name]):
            package, version = package_id.rsplit("@", 1)
            metadata = lock_packages.get(f"node_modules/{package}")
            if metadata is None or metadata.get("version") != version:
                errors.append(f"Runestone lock mismatch or missing package: {package_id}")
                resolved = ""
                integrity = ""
            else:
                resolved = metadata.get("resolved", "")
                integrity = metadata.get("integrity", "")
            rows.append((package, version, license_name, resolved, integrity))
    tsv = io.StringIO(newline="")
    writer = csv.writer(tsv, delimiter="\t", lineterminator="\n")
    writer.writerow(["package", "version", "license", "lock_resolved", "lock_integrity"])
    writer.writerows(rows)
    write_text(PACKAGE / "third-party" / "RETAINED-OPEN-PACKAGES.tsv", tsv.getvalue())

    sections = [
        "R012 RETAINED OPEN THIRD-PARTY NOTICES",
        "========================================",
        "",
        "This conservative notice set covers every one of the 68 open-license packages",
        "identified in the pinned Runestone 8.2.7 source-map/lock witness after removal",
        "of Handsontable 7.2.2 and its datafile loader. Copyright remains with each",
        "package's authors and contributors. Exact package/version, lock URL and lock",
        "integrity are recorded in RETAINED-OPEN-PACKAGES.tsv. Emitted webpack notices",
        "are preserved byte-for-byte in emitted-fragments/.",
        "",
    ]
    family_texts = {
        "0BSD": ZERO_BSD_TEXT,
        "BSD-3-Clause": BSD3_TEXT,
        "BSD-or-MIT": MIT_TEXT + "\nAlternative BSD 2-Clause terms:\n\n" + BSD2_TEXT,
        "ISC": ISC_TEXT,
        "MIT": MIT_TEXT,
        "Public-Domain": "Public-domain dedication/notice\n\njsonify@0.0.0 is identified by the pinned witness as Public Domain. No exclusive copyright license is asserted for that package.\n",
    }
    for family in sorted(GROUPS):
        sections.extend(
            [
                f"LICENSE FAMILY: {family}",
                "-" * (16 + len(family)),
                "Packages:",
                *[f"  - {package}" for package in sorted(GROUPS[family])],
                "",
                family_texts[family].rstrip(),
                "",
            ]
        )
    write_text(PACKAGE / "third-party" / "THIRD-PARTY-NOTICES.txt", "\n".join(sections))
    write_text(
        PACKAGE / "licenses" / "JQUERY-3.3.1-MIT.txt",
        """jQuery 3.3.1
Copyright JS Foundation and other contributors, https://js.foundation/

This software consists of voluntary contributions made by many individuals.
For exact contribution history, see the revision history available at
https://github.com/jquery/jquery.

"""
        + MIT_TEXT,
    )

    write_text(
        PACKAGE / "book" / "ATTRIBUTION-AND-CHANGES.md",
        """# Attribution and change notice

Book content: *Applied Combinatorics*, by Mitchel T. Keller and William T.
Trotter, official source repository <https://github.com/mitchkeller/applied-combinatorics>,
pinned at commit `33b20df670d1f8d98266cd2f4a287a79b01649ea`.

Indonesian edition title: *Kombinatorika Terapan*. Language: Bahasa Indonesia
(`id-ID`). This is an independent translation and localization produced on
2026-08-21 through 2026-08-22 at the user's request. It translates the complete
book, localizes reader chrome and read-aloud strings, adds a locale-neutral
modular backend, and records any mathematically determined source corrections
in the edition's correction ledger. The original authors remain fully credited.

Book content and the Indonesian adaptation are distributed under Creative
Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0). The complete
license text is `CC-BY-SA-4.0-LICENSE.txt` in this directory.

No endorsement: this independent edition does not imply sponsorship,
endorsement, approval, official status, or affiliation by or with Mitchel T.
Keller, William T. Trotter, their institutions, or the upstream project.

The HTML reader's software components are governed separately by the GPL and
third-party notices in this package; CC BY-SA does not replace those terms.
""",
    )

    write_text(
        PACKAGE / "pretext" / "BUILD-AND-MODIFICATION-NOTES.md",
        f"""# PreTeXt core corresponding source and Indonesian modification

Pinned source: `pretext-core-{PRETEXT_COMMIT}.zip`, SHA-256
`{PRETEXT_ZIP_SHA256}`. Its single root is `pretext-{PRETEXT_COMMIT}`.

The reader uses PreTeXt core under GPL-2.0-only or GPL-3.0-only at the
distributor's option; this release selects GPLv3 and includes the full text at
`../licenses/GPL-3.0.txt` plus the upstream `COPYING` notice here.

The Indonesian change dated 2026-08-22 localizes read-aloud strings in
`indonesian-modification/js/src/read-aloud/strings.js`. The upstream source,
localized source, localized built output, and unified source/built-output
patches are all included. No audible widget is enabled by this notice package.

Deterministic build inputs are preserved in the complete pinned core archive
and copied under `build-evidence/`. From the extracted source root, the upstream
JavaScript builder declares Node >=18; run `npm ci` and `npm run build` in
`script/jsbuilder`. CSS locks are in `script/cssbuilder`. These commands are a
corresponding-source recipe, not a claim that this package independently proved
a bit-for-bit rebuild.
""",
    )

    write_text(
        PACKAGE / "runestone" / "BUILD-AND-MODIFICATION-NOTES.md",
        f"""# Runestone corresponding source and open-release modification

The complete official repository snapshot is
`corresponding-source/runestone-rs-{RUNESTONE_COMMIT}.tar.gz`, SHA-256
`{RUNESTONE_ARCHIVE_SHA256}`, with the single root `{RUNESTONE_ROOT}`. The
retained first-party runtime is GPL-3.0-or-later; the exact upstream
`bases/rsptx/interactives/LICENSE.txt` and full GPLv3 text are included.

The pinned lock/config/build proof is copied under `build-evidence/`:
`package.json`, `package-lock.json`, `webpack.config.js`, `webpack.index.js`,
`projects/interactives/build.py`, and `projects/interactives/pyproject.toml`.
From the snapshot's `bases/rsptx/interactives`, the declared upstream recipe is
`npm ci` followed by `npm run dist`; `projects/interactives/build.py` supplies
the distribution packaging logic.

Source identity is supported by the two retained official distribution source
maps copied under `source-map-identity-evidence/`, whose 17 first-party source
contents matched this commit in the pinned rights witness. There is no public
8.2.7 source tag and the matching `pyproject.toml` still declares 8.2.6, so this
package does not claim a bit-for-bit reproducible rebuild.

Open-release modification date: 2026-08-22. The exact deterministic patch
source is `patches/prune_release_html_runtime.py`. It removes restricted and
unused runtime families, strips now-dangling map comments, and fail-closes the
corresponding loaders. The exclusions are itemized in the package-root
`OPEN-RUNTIME-EXCLUSIONS.md`.
""",
    )

    write_text(
        PACKAGE / "OPEN-RUNTIME-EXCLUSIONS.md",
        """# Open-runtime exclusions

The public HTML release-copy transform deliberately excludes:

- Handsontable 7.2.2 chunk family 249: 10 files, 9,267,918 bytes, manifest
  SHA-256 `38d84ac2169c3e1cda95c23935fee26fc5a9e71fc0d14b713702d4ebe5629b0a`.
- Runestone datafile loader family 580: 8 files, 14,254 bytes, manifest
  SHA-256 `e716e908ca33b523549f7ea82f520b5be403dc730703da65ab2a7895d0355631`.
- Orphan `sql-wasm.wasm`: 1 file, 1,183,841 bytes, SHA-256
  `962d056e419e3fa5cb2b1cc1a781b7dbf7e5c958341606310b07746e054f3294`.
- 272 AppleDouble metadata files (44,336 bytes), 51 stale Runestone 8.2.6
  files (9,659,109 bytes), and four obsolete source maps for patched
  entrypoints (279,725 bytes).

The release-copy receipt proves zero retained references to the removed
families and zero emitted datafile/disabled components. No Handsontable code,
license payload, source map, license key, or use authorization is asserted by
this edition. `sql.js@1.5.0` remains in the conservative notice registry even
though its executable WASM payload is absent.
""",
    )

    write_text(
        PACKAGE / "README.md",
        """# R012 rights and corresponding-source package

This package accompanies the Indonesian edition of *Applied Combinatorics*.
It separates CC BY-SA book rights from GPL/MIT/BSD/ISC/0BSD/public-domain HTML
reader rights, provides the complete pinned PreTeXt and Runestone source
snapshots, preserves exact lock/config/build and modification sources, supplies
all 68 retained open-package notices, and records the removal of Handsontable,
chunks 249/580, and orphan sql-wasm.

Use `FILE-INVENTORY.tsv` for deterministic byte/hash verification. The
inventory covers every package file except itself (a manifest cannot contain
its own final hash); its own bytes and SHA-256 are recorded in the external QA
receipt `qa/RIGHTS_NOTICE_SOURCE_PACKAGE_QA_20260822.json`.

This package is licensing evidence and corresponding source, not legal advice.
""",
    )

    inventory_path = PACKAGE / "FILE-INVENTORY.tsv"
    if inventory_path.exists():
        inventory_path.unlink()
    content_files = sorted(
        (path for path in PACKAGE.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(PACKAGE).as_posix(),
    )
    inventory = io.StringIO(newline="")
    writer = csv.writer(inventory, delimiter="\t", lineterminator="\n")
    writer.writerow(["path", "bytes", "sha256"])
    for path in content_files:
        writer.writerow([path.relative_to(PACKAGE).as_posix(), path.stat().st_size, sha256(path)])
    write_text(inventory_path, inventory.getvalue())

    package_files = sorted(path for path in PACKAGE.rglob("*") if path.is_file())
    package_bytes = sum(path.stat().st_size for path in package_files)
    receipt = {
        "artifact": {
            "path": "release/rights-and-corresponding-source",
            "file_count_including_inventory": len(package_files),
            "bytes_including_inventory": package_bytes,
            "inventory": "release/rights-and-corresponding-source/FILE-INVENTORY.tsv",
            "inventory_bytes": inventory_path.stat().st_size,
            "inventory_sha256": sha256(inventory_path),
            "inventory_record_count_excluding_self": len(content_files),
        },
        "book_rights": {
            "authors": ["Mitchel T. Keller", "William T. Trotter"],
            "license": "CC BY-SA 4.0",
            "pinned_authority_commit": "33b20df670d1f8d98266cd2f4a287a79b01649ea",
            "attribution_change_nonendorsement_notice": "release/rights-and-corresponding-source/book/ATTRIBUTION-AND-CHANGES.md",
            "full_license": "release/rights-and-corresponding-source/book/CC-BY-SA-4.0-LICENSE.txt",
        },
        "evidence_date": "2026-08-22",
        "errors": errors,
        "gaps": [],
        "pretext": {
            "core_commit": PRETEXT_COMMIT,
            "core_source_bytes": PRETEXT_ZIP.stat().st_size,
            "core_source_sha256": PRETEXT_ZIP_SHA256,
            "copying_sha256": sha256(PACKAGE / "pretext" / "COPYING"),
            "gplv3_sha256": sha256(PACKAGE / "licenses" / "GPL-3.0.txt"),
            "jquery_notice_sha256": sha256(PACKAGE / "licenses" / "JQUERY-3.3.1-MIT.txt"),
            "indonesian_modified_source_sha256": sha256(PACKAGE / "pretext" / "indonesian-modification" / "js" / "src" / "read-aloud" / "strings.js"),
            "source_patch_sha256": sha256(PACKAGE / "pretext" / "indonesian-modification" / "read-aloud-source.patch"),
        },
        "result": "fail" if errors else "pass",
        "runestone": {
            "commit": RUNESTONE_COMMIT,
            "source_archive_bytes": RUNESTONE_ARCHIVE.stat().st_size,
            "source_archive_sha256": RUNESTONE_ARCHIVE_SHA256,
            "archive_integrity": "pass",
            "archive_statistics": tar_stats,
            "license_sha256": sha256(PACKAGE / "runestone" / "LICENSE.txt"),
            "named_lock_config_build_files": [
                str(path.relative_to(PACKAGE)).replace("\\", "/")
                for path in sorted((PACKAGE / "runestone" / "build-evidence").rglob("*"))
                if path.is_file()
            ],
            "bit_for_bit_rebuild_claimed": False,
            "known_version_limit": "The matched source commit's pyproject.toml declares 8.2.6 while the distributed runtime identifies as 8.2.7; source-content identity is proven by the pinned witness, but a bit-for-bit rebuild is not claimed.",
        },
        "schema": "r012.rights-notice-corresponding-source-package-qa",
        "schema_version": "1.0.0",
        "third_party": {
            "retained_open_package_count": len(all_packages),
            "retained_open_package_ids": all_packages,
            "family_counts": {family: len(packages) for family, packages in sorted(GROUPS.items())},
            "handsontable_in_notice_registry": False,
            "emitted_notice_fragment_count": len(fragment_names),
            "notices": "release/rights-and-corresponding-source/third-party/THIRD-PARTY-NOTICES.txt",
            "lock_registry": "release/rights-and-corresponding-source/third-party/RETAINED-OPEN-PACKAGES.tsv",
        },
        "runtime_exclusions": {
            "handsontable_249": {"count": 10, "bytes": 9267918},
            "datafile_580": {"count": 8, "bytes": 14254},
            "sql_wasm": {"count": 1, "bytes": 1183841},
            "receipt": "release/rights-and-corresponding-source/evidence/RUNESTONE_OPEN_RUNTIME_RELEASE_COPY_20260822_2.json",
        },
        "limitations": [
            "The Runestone source snapshot is commit-pinned and complete, but a bit-for-bit rebuild of the 8.2.7 distribution is not claimed.",
            "The 68-package notice set deliberately errs toward inclusion; sql.js remains noticed although the final executable WASM payload is removed.",
            "The package inventory excludes only FILE-INVENTORY.tsv itself; the external QA receipt records that manifest's bytes and SHA-256.",
        ],
    }
    write_text(QA_PATH, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))

    print(f"result={receipt['result']}")
    print(f"package={PACKAGE}")
    print(f"files={len(package_files)}")
    print(f"bytes={package_bytes}")
    print(f"inventory_sha256={receipt['artifact']['inventory_sha256']}")
    print(f"qa={QA_PATH}")
    print(f"qa_sha256={sha256(QA_PATH)}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
