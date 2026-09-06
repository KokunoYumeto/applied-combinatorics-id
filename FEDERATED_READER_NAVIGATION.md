# Federated reader navigation

Every HTML document deployed to GitHub Pages receives one prominent,
keyboard-accessible navigation bar linking to:

- the C70 course card in the Indonesian program;
- the C70 course card in the English program; and
- the authoritative original *Applied Combinatorics* site.

The source release archive remains immutable. The Pages workflow first verifies
that archive's SHA-256, file count, and uncompressed byte count; it then applies
`scripts/apply-federated-reader-nav.py` to the extracted deployment tree. A
second, independent `--check` pass fails closed if any HTML document is missing
the marker or any required link. Re-applying the transformation is idempotent.
