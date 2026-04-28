"""
AI_APP-wide pytest configuration.

Stubs heavy ML libraries in sys.modules before any test module is imported.
GitHub Actions runners sometimes have partial CUDA installations (stub .so files
present but no GPU), causing torch._preload_cuda_lib() to raise a fatal SIGBUS
instead of a catchable ImportError — which kills the entire pytest process.

pytest loads conftest.py files before collecting test modules, so these stubs
are guaranteed to be in sys.modules when any AI_APP test file is imported.
"""

import sys
from unittest.mock import MagicMock

_ML_STUBS = [
    # PyTorch — crashes CI with SIGBUS on partial CUDA installations
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torch.cuda",
    "torch.utils",
    "torch.utils.data",
    # Ultralytics (YOLO) — imports torch unconditionally at package level
    "ultralytics",
    "ultralytics.utils",
    "ultralytics.models",
    "ultralytics.engine",
    # EasyOCR / PaddleOCR — also GPU-dependent
    "easyocr",
    "paddleocr",
    "paddle",
    "paddle.nn",
]

for _mod in _ML_STUBS:
    sys.modules.setdefault(_mod, MagicMock())
