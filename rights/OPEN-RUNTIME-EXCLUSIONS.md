# Open-runtime exclusions

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
