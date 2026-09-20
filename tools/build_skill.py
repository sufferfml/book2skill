"""Build deterministic portable runtime, including the pinned PDF parser."""

import json
import hashlib
import importlib.metadata
import importlib.util
import shutil
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from book2skill.contracts import SCHEMAS, schema  # noqa: E402
from book2skill import __version__  # noqa: E402


def build():
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT / name, ROOT / "skill/book2skill" / name)
    output = ROOT / "skill/book2skill/scripts/book2skill.pyz"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {"__main__.py": b"from book2skill.cli import main\nraise SystemExit(main())\n"}
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        files[name] = (ROOT / name).read_bytes()
    for path in sorted((ROOT / "src/book2skill").glob("*.py")):
        files["book2skill/" + path.name] = path.read_bytes()
    dependency = importlib.metadata.distribution("pypdf")
    if dependency.version != "6.10.0":
        raise RuntimeError("Build requires pypdf==6.10.0; install project dependencies first")
    package_dir = Path(importlib.util.find_spec("pypdf").origin).parent
    for path in sorted(package_dir.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            files["pypdf/" + path.relative_to(package_dir).as_posix()] = path.read_bytes()
    license_name = "pypdf-6.10.0.dist-info/licenses/LICENSE"
    for name in (license_name, "pypdf-6.10.0.dist-info/METADATA", "pypdf-6.10.0.dist-info/WHEEL"):
        files[name] = Path(dependency.locate_file(name)).read_bytes()
    license_output = ROOT / "skill/book2skill/licenses/pypdf-LICENSE.txt"
    license_output.parent.mkdir(parents=True, exist_ok=True)
    license_output.write_bytes(files[license_name])
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    schemas = ROOT / "schemas"
    schemas.mkdir(exist_ok=True)
    for kind in SCHEMAS:
        (schemas / f"{kind}.schema.json").write_text(json.dumps(schema(kind), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    release = ROOT / "dist"
    release.mkdir(exist_ok=True)
    archive = release / f"book2skill-{__version__}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted((ROOT / "skill/book2skill").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                info = zipfile.ZipInfo(path.relative_to(ROOT / "skill").as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, path.read_bytes())
    manifest = {"version": __version__, "runtime": "Python >=3.11, macOS/Linux; pypdf 6.10.0 bundled, no runtime install",
                "bundled_dependencies": {"pypdf": {"version": dependency.version,
                    "license_sha256": hashlib.sha256(files[license_name]).hexdigest(),
                    "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items()) if name.startswith("pypdf/")}}},
                "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "zipapp_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "src/book2skill").glob("*.py"))}}
    manifest_path = release / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (release / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in (archive, manifest_path)
    ), encoding="utf-8")
    print(output)
    print(archive)


if __name__ == "__main__":
    build()
