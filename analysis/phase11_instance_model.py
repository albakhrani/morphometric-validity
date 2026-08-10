#!/usr/bin/env python3
"""
Phase 11 - Instance-preserving model + loss  (Paper 2, Option B)
================================================================
Extends the Paper-1 backbone (AdvancedUNetPlusPlus) with an instance-aware head
without editing the original model file.

  InstancePreservingUNetPlusPlus(AdvancedUNetPlusPlus)
      Adds two sibling heads on the deepest top-row node X^{0, depth-1}
      (the same feature map the foreground FinalConv reads):
          dist_head : per-cell distance map      (watershed markers)
          bnd_head  : instance boundary logits    (auxiliary, sharpens edges)
      The foreground path (incl. deep supervision) is byte-identical to Paper 1,
      so the checkpoint transfers exactly and only the two heads start fresh.

      forward(x) -> dict:
          'fg'   : list[Tensor] (deep supervision) or Tensor  - foreground logits
          'dist' : Tensor (B,1,H,W) - distance logits (apply sigmoid -> [0,1])
          'bnd'  : Tensor (B,1,H,W) - boundary logits

  load_paper1_backbone(model, ckpt)
      Transfers Paper-1 weights into the shared backbone. Refuses to proceed if
      any checkpoint tensor is unused (config mismatch) or any backbone tensor is
      missing; the only tensors allowed to be missing are the two new heads.

  instance_loss(out, batch)
      BCE+Dice on foreground (averaged over deep-supervision heads) + L1 on the
      distance map + weighted BCE on boundaries.

This module imports the real model on the user's machine:
    from src.models.unet_plus_plus import AdvancedUNetPlusPlus
    from src.models.blocks import FinalConv
Run it from the project root so those imports resolve.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Dict, List, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

log = logging.getLogger("instance_model")

# Make the project root importable when run as a script from anywhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from src.models.unet_plus_plus import AdvancedUNetPlusPlus   # noqa: E402
from src.models.blocks import FinalConv                       # noqa: E402


# ============================================================================
# MODEL
# ============================================================================

class InstancePreservingUNetPlusPlus(AdvancedUNetPlusPlus):
    """Paper-1 U-Net++ backbone + distance/boundary heads for instance recovery."""

    NEW_HEAD_PREFIXES = ("dist_head", "bnd_head")

    def __init__(self, use_distance_head: bool = True,
                 use_boundary_head: bool = True, **kwargs):
        """Each head can be disabled independently, which is what the ablation
        needs. Both default to True, so every existing call site and every
        existing checkpoint behaves exactly as before."""
        kwargs.setdefault("use_dense_skip", True)
        super().__init__(**kwargs)
        if not self.use_dense_skip:
            raise ValueError("instance extension requires use_dense_skip=True")
        if not (use_distance_head or use_boundary_head):
            raise ValueError("at least one instance head must be enabled")

        self.use_distance_head = use_distance_head
        self.use_boundary_head = use_boundary_head

        bc = self.base_channels
        self.dist_head = FinalConv(in_channels=bc, num_classes=1) if use_distance_head else None
        self.bnd_head = FinalConv(in_channels=bc, num_classes=1) if use_boundary_head else None

        # initialise only the new heads (backbone is loaded from Paper 1)
        new = [h for h in (self.dist_head, self.bnd_head) if h is not None]
        for m in [mm for h in new for mm in h.modules()]:
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
        names = " + ".join(n for n, h in (("dist_head", self.dist_head),
                                          ("bnd_head", self.bnd_head)) if h is not None)
        log.info("instance heads added: %s (%.3fM extra params)", names,
                 sum(p.numel() for h in new for p in h.parameters()) / 1e6)

    def _build_nodes(self, x: torch.Tensor) -> Dict:
        """Recompute the nested nodes exactly as AdvancedUNetPlusPlus.forward does
        (dense-skip path), so we can tap the deepest top-row feature map."""
        nodes = {}
        for i in range(self.depth):
            src = x if i == 0 else self.pool(nodes[(i - 1, 0)])
            nodes[(i, 0)] = self.encoder_blocks[i](src)
        for j in range(1, self.depth):
            for i in range(self.depth - 1 - j, -1, -1):
                key = f"{i}_{j}"
                same = [nodes[(i, k)] for k in range(j)]
                up = self.nested_upsamples[key](nodes[(i + 1, j - 1)])
                if up.shape[-2:] != same[0].shape[-2:]:
                    up = F.interpolate(up, size=same[0].shape[-2:],
                                       mode="bilinear", align_corners=False)
                nodes[(i, j)] = self.nested_blocks[key](*(same + [up]))
        return nodes

    def forward(self, x: torch.Tensor, return_features: bool = False
                ) -> Dict[str, Union[torch.Tensor, List[torch.Tensor]]]:
        if x.dim() != 4:
            raise ValueError(f"expected 4D input, got {x.dim()}D")
        nodes = self._build_nodes(x)
        feat = nodes[(0, self.depth - 1)]

        if self.deep_supervision:
            fg = [self.final_convs[j - 1](nodes[(0, j)]) for j in range(1, self.depth)]
        else:
            fg = self.final_convs[0](feat)

        out = {"fg": fg}
        if self.dist_head is not None:
            out["dist"] = self.dist_head(feat)
        if self.bnd_head is not None:
            out["bnd"] = self.bnd_head(feat)
        if return_features:
            out["feat"] = feat
        return out


# ============================================================================
# WEIGHT TRANSFER
# ============================================================================

def load_paper1_backbone(model: InstancePreservingUNetPlusPlus,
                         ckpt_path: str,
                         verbose: bool = True) -> InstancePreservingUNetPlusPlus:
    """Load Paper-1 weights into the shared backbone; leave the new heads fresh.

    Raises if the checkpoint config does not match the backbone (unused tensors)
    or if any backbone tensor is absent (only the two heads may be missing).
    """
    obj = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    sd = obj
    for k in ("model_state_dict", "state_dict", "model"):
        if isinstance(sd, dict) and k in sd:
            sd = sd[k]
            break
    sd = {k.replace("module.", "", 1): v for k, v in sd.items()}

    missing, unexpected = model.load_state_dict(sd, strict=False)

    if unexpected:
        raise RuntimeError(
            f"{len(unexpected)} checkpoint tensors are not used by the model - "
            f"the architecture config does not match the checkpoint. "
            f"First few: {list(unexpected)[:6]}")
    non_head_missing = [k for k in missing
                        if not k.startswith(InstancePreservingUNetPlusPlus.NEW_HEAD_PREFIXES)]
    if non_head_missing:
        raise RuntimeError(
            f"{len(non_head_missing)} backbone tensors are missing from the "
            f"checkpoint (only the new heads may be missing). "
            f"First few: {non_head_missing[:6]}")

    if verbose:
        transferred = len(sd)
        new_heads = sorted({k.split(".")[0] for k in missing})
        log.info("backbone transfer OK: %d tensors loaded from Paper 1; "
                 "randomly-initialised heads: %s", transferred, new_heads)
        if isinstance(obj, dict):
            for k in ("epoch", "val_iou", "best_iou"):
                if k in obj:
                    log.info("  checkpoint %s = %s", k, obj[k])
    return model


# ============================================================================
# LOSS
# ============================================================================

def _dice_loss(logits: torch.Tensor, target: torch.Tensor, eps: float = 1.0) -> torch.Tensor:
    p = torch.sigmoid(logits)
    num = 2.0 * (p * target).sum(dim=(2, 3)) + eps
    den = (p + target).sum(dim=(2, 3)) + eps
    return (1.0 - num / den).mean()


def instance_loss(out: Dict,
                  batch: Dict,
                  w_dist: float = 1.0,
                  w_bnd: float = 1.0,
                  bnd_pos_weight: float = 5.0):
    """Combined foreground + distance + boundary loss.

    Returns (total_loss, components_dict) where components are floats for logging.
    """
    fg_t = batch["fg"]
    fg = out["fg"]
    if isinstance(fg, (list, tuple)):
        fg_loss = sum(F.binary_cross_entropy_with_logits(o, fg_t) + _dice_loss(o, fg_t)
                      for o in fg) / len(fg)
    else:
        fg_loss = F.binary_cross_entropy_with_logits(fg, fg_t) + _dice_loss(fg, fg_t)

    # A head that is switched off contributes no output and therefore no loss
    # term. Ablation runs A and B rely on this.
    if "dist" in out:
        dist_loss = F.l1_loss(torch.sigmoid(out["dist"]), batch["dist"])
    else:
        dist_loss = torch.zeros((), device=fg_loss.device, dtype=fg_loss.dtype)

    if "bnd" in out:
        pos_w = torch.as_tensor(bnd_pos_weight, device=out["bnd"].device,
                                dtype=out["bnd"].dtype)
        bnd_loss = F.binary_cross_entropy_with_logits(out["bnd"], batch["bnd"],
                                                      pos_weight=pos_w)
    else:
        bnd_loss = torch.zeros((), device=fg_loss.device, dtype=fg_loss.dtype)

    total = fg_loss + w_dist * dist_loss + w_bnd * bnd_loss
    return total, {"fg": float(fg_loss.detach()),
                   "dist": float(dist_loss.detach()),
                   "bnd": float(bnd_loss.detach()),
                   "total": float(total.detach())}


# ============================================================================
# BUILD HELPER (trained Paper-1 config)
# ============================================================================

def build_instance_model(base_channels: int = 32,
                         depth: int = 4,
                         attention_type: str = "dual_cbam",
                         attention_reduction: int = 16,
                         deep_supervision: bool = True,
                         **extra) -> InstancePreservingUNetPlusPlus:
    """Build the instance model with Paper-1's *trained* configuration.

    Defaults match models/unetpp_ds_best.pt: depth 4, base 32, dual CBAM,
    deep supervision. Override only if the checkpoint differs.
    """
    from types import SimpleNamespace
    attn = SimpleNamespace(enabled=True, type=attention_type, reduction=attention_reduction)
    return InstancePreservingUNetPlusPlus(
        in_channels=1, num_classes=1,
        base_channels=base_channels, depth=depth,
        use_dense_skip=True, bilinear_upsample=False,
        attention_config=attn, activation="swish",
        dropout=0.0, use_batch_norm=True,
        deep_supervision=deep_supervision, **extra)
