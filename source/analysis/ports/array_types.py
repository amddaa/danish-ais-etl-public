"""Shared NumPy array aliases compatible with sklearn / Pyrefly.

Bare ``np.ndarray`` and parameterized ``np.ndarray[Any, Any]`` are different
types in Pyrefly (see ``ndarray@NNNN`` identities). Always use these aliases
for arrays that cross function boundaries.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Parameterized form — matches sklearn stubs and avoids bare-ndarray identity mismatch
NdArray = np.ndarray[Any, Any]
FloatArray = NdArray  # alias kept for existing imports
