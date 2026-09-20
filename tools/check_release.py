"""Check public source/portable artifacts. Not a comprehensive rights or secret audit."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from book2skill import __version__


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scan(name, data):
    require(not any(p in PurePosixPath(name).parts for p in
                    ("workspaces", "artifacts", "business-design", "audit", "excerpts", ".git")),
            f"Private path in public distribution: {name}")
    require(PurePosixPath(name).suffix.lower() not in (".epub", ".pdf", ".mobi", ".azw"),
            f"Book file in public distribution: {name}")
    if name.endswith(".pyz"):
        return  # Nested archive checked separately below.
    text = data.decode("utf-8", errors="replace")
    # Construct patterns in parts so the scanner's own source is not a false positive.
    private_markers = ("/Users/" + "morrow/", "z-library" + ".sk", "1lib" + ".sk",
                       "商业模式" + "新生代", "发现" + "利润区")
    require(not any(marker in text for marker in private_markers), f"Private case/path content: {name}")
    patterns = (r"-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                r"gh[pousr]_" + r"[A-Za-z0-9]{30,}",
                r"github_pat_" + r"[A-Za-z0-9_]{40,}",
                r"sk-(?:proj-|ant-)?" + r"[A-Za-z0-9_-]{40,}")
    require(not any(re.search(pattern, text) for pattern in patterns), f"Potential secret: {name}")


def main():
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT).decode().split("\0")
    names = sorted(set(filter(None, names)))
    require(bool(names), "No public files found")
    allowed_roots = {".github", "docs", "examples", "schemas", "skill", "src", "tests", "tools"}
    allowed_files = {".gitignore", "README.md", "README.zh-CN.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
                     "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "pyproject.toml"}
    for name in names:
        path = ROOT / name
        require(not path.is_symlink(), f"Symlink in public files: {name}")
        require(name in allowed_files or ("/" in name and name.split("/")[0] in allowed_roots),
                f"Unexpected public path: {name}")
        if name.startswith("skill/"):
            require(name.startswith("skill/book2skill/"), f"Unexpected application skill: {name}")
        scan(name, path.read_bytes())

    skill = ROOT / "skill/book2skill"
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        require((ROOT / name).read_bytes() == (skill / name).read_bytes(), f"License drift: {name}")
    archive = ROOT / "dist" / f"book2skill-{__version__}.zip"
    manifest_path = ROOT / "dist/release-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require(manifest["version"] == __version__, "Release version mismatch")
    require(sha(archive.read_bytes()) == manifest["zip_sha256"], "Release ZIP hash mismatch")
    for name, expected in manifest["source_hashes"].items():
        require(sha((ROOT / name).read_bytes()) == expected, f"Source hash mismatch: {name}")
    with zipfile.ZipFile(archive) as z:
        expected = {"book2skill/" + p.relative_to(skill).as_posix() for p in skill.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts}
        require(set(z.namelist()) == expected and len(z.namelist()) == len(expected), "ZIP inventory mismatch")
        for name in z.namelist():
            data = z.read(name)
            require(data == (ROOT / "skill" / name).read_bytes(), f"ZIP content drift: {name}")
            scan(name, data)
        app = z.read("book2skill/scripts/book2skill.pyz")
    require(sha(app) == manifest["zipapp_sha256"], "Zipapp hash mismatch")
    with zipfile.ZipFile(io.BytesIO(app)) as z:
        for name in z.namelist():
            require(name in ("__main__.py", "LICENSE", "THIRD_PARTY_NOTICES.md") or name.startswith(("book2skill/", "pypdf/", "pypdf-6.10.0.dist-info/")),
                    f"Unexpected zipapp member: {name}")
            scan(name, z.read(name))
            if name.startswith("book2skill/"):
                require(z.read(name) == (ROOT / "src" / name).read_bytes(), f"Zipapp source drift: {name}")
        require(z.read("pypdf-6.10.0.dist-info/licenses/LICENSE") == (skill / "licenses/pypdf-LICENSE.txt").read_bytes(),
                "Third-party notice mismatch")
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            require(z.read(name) == (ROOT / name).read_bytes(), f"Zipapp notice drift: {name}")
    sums = (ROOT / "dist/SHA256SUMS").read_text().splitlines()
    require(sums == [f"{sha(p.read_bytes())}  {p.name}" for p in (archive, manifest_path)], "Checksum list mismatch")
    print(json.dumps({"status": "passed", "public_files": len(names), "version": __version__,
                      "zip_sha256": sha(archive.read_bytes()), "scope": "paths, selected content patterns, artifact hashes, licenses"}, indent=2))


if __name__ == "__main__":
    main()
