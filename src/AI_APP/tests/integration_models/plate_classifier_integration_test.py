"""
Integration test: validate PlateClassifier against real crop images.

Run from repository root:

    # Default (license plates, default crops folder)
    PYTHONPATH=src uv run --active pytest -q \
        src/AI_APP/tests/integration_models/plate_classifier_integration_test.py \
        -m integration_model

    # Hazard plates from custom folder
    PYTHONPATH=src uv run --active pytest -q \
        src/AI_APP/tests/integration_models/plate_classifier_integration_test.py \
        -m integration_model --plate-type hazard_plate --crops-dir ../hazard_plate_crops
"""

from pathlib import Path

import cv2
import pytest

from AI_APP.shared.src.plate_classifier import PlateClassifier


pytestmark = pytest.mark.integration_model


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def classifier():
    return PlateClassifier()


@pytest.fixture
def expected_type(request):
    return request.config.getoption("--plate-type")


@pytest.fixture
def crop_files(request):
    crops_dir = request.config.getoption("--crops-dir", default=None)
    if crops_dir:
        crops_dir = Path(crops_dir)
    else:
        crops_dir = Path(__file__).resolve().parents[2] / "crops"

    if not crops_dir.exists():
        pytest.skip(f"Crops directory not found: {crops_dir}")

    files = sorted(f for f in crops_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not files:
        pytest.skip("No crop images found")

    return files


# =============================================================================
# Test
# =============================================================================

def test_classify_all_crops(classifier, crop_files, expected_type):
    """Every image in the crops directory should match the expected plate type."""
    total = 0
    correct = 0
    failed = []

    for f in crop_files:
        img = cv2.imread(str(f))
        if img is None:
            continue

        total += 1
        h, w = img.shape[:2]
        result = classifier.classify(img)

        if result == expected_type:
            correct += 1
        else:
            failed.append(f"{f.name}  AR={w/h:.2f}  got={result}")

    # --- Summary ---
    wrong = total - correct
    accuracy = (correct / total * 100) if total > 0 else 0

    print(f"\n{'=' * 50}")
    print(f"  Expected type : {expected_type}")
    print(f"  Total crops   : {total}")
    print(f"  Correct       : {correct}")
    print(f"  Wrong         : {wrong}")
    print(f"  Accuracy      : {accuracy:.1f}%")
    print(f"{'=' * 50}")

    if failed:
        print("\n  Misclassified:")
        for line in failed:
            print(f"    - {line}")
        print()

    assert wrong == 0, f"{wrong}/{total} crops misclassified (see above)"