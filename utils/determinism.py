"""Utilities to configure deterministic behaviour across supported libraries."""

from __future__ import annotations

import os
import random
from typing import Optional

import numpy as np

try:  # pragma: no cover - torch is optional at runtime
    import torch
except Exception:  # pragma: no cover - gracefully ignore when torch missing
    torch = None  # type: ignore[assignment]


def configure_determinism(seed: int, enable: bool = True) -> None:
    """Seed common RNG backends and enforce deterministic execution when possible.

    Parameters
    ----------
    seed:
        Integer seed applied to Python, NumPy, and PyTorch RNGs.
    enable:
        If False, the function returns immediately without touching RNG state.
    """

    if not enable:
        return

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)

    if torch is None:
        return

    try:
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        torch.backends.cudnn.deterministic = True  # type: ignore[attr-defined]
        torch.backends.cudnn.benchmark = False  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        # warn_only avoids raising if an operator lacks a deterministic implementation
        torch.use_deterministic_algorithms(True, warn_only=True)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - compatibility with older torch versions
        pass
