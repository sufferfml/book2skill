"""Immutable snapshots and an atomic HEAD pointer. flock releases on process death."""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

from .contracts import Invalid


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise Invalid(f"duplicate JSON key: {k}")
            d[k] = v
        return d
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda s: (_ for _ in ()).throw(Invalid(f"invalid number: {s}")))
    except (OSError, ValueError) as exc:
        raise Invalid(f"cannot read JSON {path}: {exc}") from exc


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


@contextlib.contextmanager
def lock(root):
    import fcntl
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Invalid("another writer holds this run; retry after it finishes") from exc
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def load(root):
    root = Path(root)
    head = load_json(root / "HEAD.json")
    name = head["snapshot"]
    if Path(name).name != name:
        raise Invalid("invalid snapshot path")
    state = load_json(root / "checkpoints" / name / "state.json")
    if digest(state) != head["sha256"]:
        raise Invalid("snapshot integrity failed; do not continue from altered state")
    return state


def commit(root, state, action):
    root = Path(root)
    state["revision"] += 1
    state["events"].append({"revision": state["revision"], "at": now(), "action": action})
    state["updated_at"] = now()
    snapshots = root / "checkpoints"
    snapshots.mkdir(exist_ok=True)
    name = f"{state['revision']:06d}-{uuid.uuid4().hex[:12]}"
    pending = snapshots / (".pending-" + name)
    pending.mkdir()
    try:
        write_json(pending / "state.json", state)
        os.rename(pending, snapshots / name)
        sync_dir(snapshots)
        # A crash before this single atomic replace leaves the old snapshot active.
        write_json(root / "HEAD.json", {"snapshot": name, "sha256": digest(state)})
    finally:
        if pending.exists():
            shutil.rmtree(pending)


def history(root):
    return load(root)["events"]


def require(condition, message):
    if not condition:
        raise Invalid(message)

