"""Select an existing trained model version without retraining."""
from __future__ import annotations

import argparse
import json
import os
from ml_pipeline.registry import publication_lock
from model.probability import validate_bundle
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    args = parser.parse_args()
    root = Path(os.getenv("MODEL_DIR", "/models"))
    version = Path(args.version).name
    model = root / version / "model.txt"
    metadata = root / version / "metadata.json"
    if not model.is_file() or not metadata.is_file():
        parser.error(f"unknown model version: {version}")
    with publication_lock(root):
        content = json.loads(metadata.read_text())
        if content.get("version") != version:
            parser.error("metadata version mismatch")
        validate_bundle(root / version, required=content.get("bundle_version", 1) >= 2)
        temp = root / "active.tmp"
        temp.write_text(json.dumps(content))
        os.replace(temp, root / "active.json")
    print(version)


if __name__ == "__main__":
    main()
