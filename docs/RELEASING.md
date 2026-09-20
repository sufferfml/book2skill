# Release procedure

Public releases contain only the generator, its skill, schemas, synthetic fixtures, tests, and public documentation. Book-specific skills and research archives belong in separate private repositories. Never merge private archive history into this repository.

1. Work from a clean checkout of this repository. Confirm the intended version in `pyproject.toml`, `src/book2skill/__init__.py`, skill instructions, and release notes.
2. Install dependencies; run the full unit suite and both synthetic demos in fresh directories. Do not interpret fixture success as semantic validation.
3. Run `python tools/build_skill.py`. It copies MIT and third-party notices into the portable skill and produces `dist/book2skill-<version>.zip`, `release-manifest.json`, and `SHA256SUMS`.
4. Run `python tools/check_release.py`. Review the actual public file list and changes as well: the script checks paths, selected sensitive patterns, hashes, zip contents, and license inclusion, not all possible secrets or copyright issues.
5. Commit generated tracked files; require CI to pass for the release commit. CI rebuilds artifacts and checks for drift.
6. Extract the ZIP into a temporary directory outside the checkout. Run its CLI with `python3 -S` and inspect the synthetic source. Confirm that it works without the developer virtual environment or source checkout.
7. Create an annotated `v<version>` tag, push it, and publish a GitHub prerelease with the ZIP, manifest, and checksums. Keep experimental status until evidence supports a stronger claim. Do not publish Python packages to a registry as part of this procedure.
8. Download the public assets without authentication and verify their checksums and portable CLI. Check that public branches/tags contain only reviewed public history.

For a downloaded release, keep its three assets together and run `shasum -a 256 -c SHA256SUMS` (macOS) or `sha256sum -c SHA256SUMS` (Linux). This verifies bytes, not publisher identity; use the official repository URL.

## Initial release validation scope

Version 0.0.4 has 80 engineering tests covering extraction, resumable workflow, review gates, multi-book integration, runtime compilation, bounded retrieval, and evaluation bookkeeping. Public CI runs Python 3.11 and 3.13 on Linux and Python 3.11 on macOS. Synthetic single-book and fusion demos exercise the local file workflow. These checks do not establish broad model/host compatibility, independent semantic review, or held-out transfer improvement.
