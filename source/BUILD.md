# Editable PreTeXt source

This directory exposes the target-language PreTeXt source and build inputs for version `2026.08.22.1`. `ACTIVE_ASSET_MANIFEST.tsv` binds the 281 asset files referenced by the active source closure. Legacy/unreferenced assets, generated outputs, generated-assets, caches, logs, temporary renders, the 214 MB frozen authority archive, and public ZIP assets are intentionally absent from this repository tree.

The complete editable package, including generated assets and corresponding runtime source, is the release asset `01_KOMBINATORIKA_TERAPAN_ID-ID_CORRESPONDING_SOURCE_2026.08.22.1.zip`. Exact source authority and artifact hashes are in `../evidence/`.

Use a pinned-compatible PreTeXt toolchain from this directory to run `pretext build html` or `pretext build pdf`. The release tools used for final cover, HTML metadata, runtime pruning, and rights assembly are under `release-tools/`.
