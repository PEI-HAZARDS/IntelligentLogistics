"""
Integration test: all crops in src/crops/ are license plates.
Validates that PlateClassifier does not misclassify any as HAZARD_PLATE.

Run: cd src/shared && python -m pytest tests/plate_classifier_integration_test.py -v
"""

import cv2
import pytest
from pathlib import Path

from plate_classifier import PlateClassifier

CROPS_DIR = Path(__file__).resolve().parents[2] / "crops"


@pytest.fixture
def classifier():
    return PlateClassifier()


@pytest.fixture
def crop_files():
    if not CROPS_DIR.exists():
        pytest.skip(f"Crops directory not found: {CROPS_DIR}")
    files = sorted(f for f in CROPS_DIR.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not files:
        pytest.skip("No crop images found")
    return files


def test_all_crops_are_license_plates(classifier, crop_files):
    """Every image in src/crops/ should be classified as LICENSE_PLATE."""
    failed = []

    for f in crop_files:
        img = cv2.imread(str(f))
        if img is None:
            continue
        h, w = img.shape[:2]
        result = classifier.classify(img)
        if result != PlateClassifier.LICENSE_PLATE:
            failed.append(f"{f.name}  AR={w/h:.2f}  got={result}")

    assert len(failed) == 0, (
        f"{len(failed)} crops misclassified:\n" + "\n".join(failed)
    )
