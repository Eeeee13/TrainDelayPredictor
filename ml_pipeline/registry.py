"""One publication lock shared by evaluation, activation, and rollback."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path


@contextmanager
def publication_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def reference_identity(root, default_model):
    root = Path(root)
    pointer = root / 'active.json'
    meta = json.loads(pointer.read_text()) if pointer.exists() else {'version':'bundled', 'bundle_version':1}
    if pointer.exists() and Path(meta['version']).name != meta['version']:
        raise ValueError('invalid model version')
    path = root / meta['version'] / 'model.txt' if pointer.exists() else Path(default_model)
    digest = hashlib.sha256(json.dumps(meta, sort_keys=True).encode())
    for filename in ['model.txt', 'classifier.txt', 'calibrator.json', 'metadata.json']:
        file = path.parent / filename
        if file.exists():
            digest.update(filename.encode())
            digest.update(file.read_bytes())
    return path, {'version':meta['version'], 'bundle_version':meta.get('bundle_version',1), 'fingerprint':digest.hexdigest()}
