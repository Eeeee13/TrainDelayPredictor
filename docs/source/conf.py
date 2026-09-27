import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / "backend"), str(root), str(root / "model")]

project = "TrainDelayPredictor"
author = "Мосгортранс"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]
autodoc_default_options = {"members": True, "undoc-members": True}
autodoc_mock_imports = ["openai"]

# Import before autodoc: a later import under Sphinx makes Pydantic treat
# ``model_fields`` as a field of the inference request models.
import inference.app  # noqa: E402,F401
