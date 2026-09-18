"""Patch classifier: vessel / wake / false positive.

Runs in Colab, not Earth Engine — Earth Engine cannot train a CNN. Input is the patches
exported by candidates.export_patches(), plus labels produced in the annotation tool.

Notes:
- Negatives matter as much as positives. Whitecaps, cloud edges, reef breaks and sun
  glint all look like bright specks; a model trained only on vessels flags them all.
- Report performance by vessel size, not as a single number. The minimum detectable
  size is a result of this project, not a footnote.
- Keep the held-out test AOIs out of training AND out of threshold tuning. Once a
  threshold has been tuned against test data the evaluation stops meaning anything,
  and it happens easily by accident.
- Recall here is conditional on candidate detection. Quote it alongside the
  exhaustively labelled scenes, which measure what the candidate step itself misses.
"""

from pathlib import Path
import numpy as np


def load_labels(path: Path) -> list[dict]:
    """Load labels from GeoJSON: coordinates, timestamp, scene ID, class, annotator,
    confidence."""
    raise NotImplementedError


def load_patches(patch_dir: Path, labels: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Match exported patches to labels. Returns (patches, class indices).

    Each sample should include both the candidate patch and the corresponding median
    background patch — the difference between them is the strongest signal available.
    """
    raise NotImplementedError


def train(patches: np.ndarray, labels: np.ndarray, **kwargs):
    """Train the patch classifier. Returns the fitted model.

    Start simple. With few hundred labels, a small CNN or even gradient boosting on
    hand-built features (peak residual, area, shape, spectral ratios) may beat a deep
    model. Record which was chosen in docs/decisions.md.
    """
    raise NotImplementedError


def predict(model, patches: np.ndarray) -> np.ndarray:
    """Predict class probabilities for candidate patches."""
    raise NotImplementedError


def evaluate(model, patches: np.ndarray, labels: np.ndarray,
             sizes_m: np.ndarray | None = None) -> dict:
    """Precision, recall and F1, broken down by vessel size where known.

    Size comes from the exhaustively labelled reference scenes and, where available,
    AIS matches within a couple of minutes of acquisition. AIS is a supporting check
    only: most small boats in Tonga carry no transponder, so absence of AIS says
    nothing about absence of a vessel.
    """
    raise NotImplementedError
