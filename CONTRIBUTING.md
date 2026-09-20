# Contributing

Use Python 3.11+ on macOS/Linux. Install with `python -m pip install -e .` in a virtual environment, then run `python -m unittest discover -s tests -v`.

For a fix, describe the user-visible failure, provide a minimal synthetic or permission-cleared reproduction, and add a behavioral test where useful. Preserve source locations, uncertainty, boundaries, and compatibility with stored runs. Do not weaken evidence/review gates merely to make fixtures pass.

Never attach commercial books, private research runs, credentials, or identifiable case data to issues or pull requests. Use invented fixtures. Contributions are submitted under the project's MIT license; only submit material you have the right to contribute.

When changing code or schemas, run `python tools/build_skill.py` and commit the regenerated zipapp and schemas. Run `python tools/check_release.py`; keep distributable license notices intact. Do not commit `dist/`, run outputs, or local planning documents.

For evaluation changes, distinguish fixture behavior, source review, and measured transfer quality. Do not report character counts as token savings or scripted fixture results as model performance.
