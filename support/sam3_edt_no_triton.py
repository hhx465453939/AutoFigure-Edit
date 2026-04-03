# SPDX-License-Identifier: Apache-2.0
#
# Drop-in replacement for facebookresearch/sam3 `sam3.model.edt` when Triton is
# unavailable (typical on Windows). Registered by autofigure2 before importing
# sam3.model_builder. Semantics match upstream docstring: batched cv2.distanceTransform(..., DIST_L2, 0).

"""Euclidean distance transform without Triton (SciPy)."""

from __future__ import annotations

import numpy as np
import torch


def edt_triton(data: torch.Tensor) -> torch.Tensor:
    """
    Computes the Euclidean Distance Transform (EDT) of a batch of binary images.

    Args:
        data: A tensor of shape (B, H, W) representing a batch of binary images.

    Returns:
        A tensor of the same shape as data containing the EDT (float32 on same device).
    """
    assert data.dim() == 3
    try:
        from scipy.ndimage import distance_transform_edt
    except ImportError as e:
        raise RuntimeError(
            "本地 SAM3 在无 Triton 环境下需要 SciPy 做距离变换。请执行: pip install scipy"
        ) from e

    B, H, W = data.shape
    device = data.device
    if data.dtype != torch.bool:
        data = data.bool()

    out = torch.empty(B, H, W, dtype=torch.float32, device=device)
    for b in range(B):
        m = data[b].detach().cpu().numpy()
        # distance_transform_edt: distance to nearest 0; use 1 inside region, 0 outside
        src = np.where(m, 1, 0).astype(np.uint8)
        dt = distance_transform_edt(src).astype(np.float32)
        out[b] = torch.from_numpy(dt).to(device=device)
    return out
