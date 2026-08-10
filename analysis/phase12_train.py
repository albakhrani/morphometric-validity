#!/usr/bin/env python3
"""
Phase 12 - Train the instance-preserving model  (Paper 2, Option B)
===================================================================
Fine-tunes InstancePreservingUNetPlusPlus starting from the Paper-1 backbone.

Key features
  - Transfer init from models/unetpp_ds_best.pt (backbone), heads trained fresh.
  - Mixed precision (bf16 on RTX 4080) + optional gradient checkpointing.
  - Cosine LR with warm-up; AdamW.
  - Validation each epoch: foreground IoU + distance-map MAE; best checkpoint by
    a combined score (IoU up, distance error down).
  - Resume from checkpoint.
  - --overfit N : sanity mode. Trains on a single fixed batch for N steps and
    prints the loss each step; it MUST fall toward zero within ~50 steps if the
    whole learning path is wired correctly. Run this (a few seconds) before any
    long run.

Typical use
  # 1) sanity check (seconds) - loss must drop:
  python phase12_train.py --overfit 60 \
      --train-images data/raw/livecell_train_images --train-targets instance_targets/train \
      --ckpt models/unetpp_ds_best.pt

  # 2) real training:
  python phase12_train.py \
      --train-images data/raw/livecell_train_images --train-targets instance_targets/train \
      --val-images   data/raw/livecell_val_images   --val-targets   instance_targets/val \
      --ckpt models/unetpp_ds_best.pt \
      --epochs 40 --batch-size 2 --crop 512 --out runs/instance
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from typing import Dict

import numpy as np
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from phase10_dataset import make_loader                       # noqa: E402
from phase11_instance_model import (                          # noqa: E402
    build_instance_model, load_paper1_backbone, instance_loss)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("train")


# --------------------------------------------------------------------------
def iou_and_dist_error(model, loader, device, amp_dtype, max_batches=None):
    """Foreground IoU (threshold 0.5) and distance-map MAE over the loader."""
    model.eval()
    inter = union = 0
    dist_abs = dist_n = 0.0
    with torch.no_grad():
        for k, batch in enumerate(loader):
            if max_batches and k >= max_batches:
                break
            img = batch["image"].to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=amp_dtype,
                                enabled=(device.type == "cuda")):
                out = model(img)
            fg = out["fg"][-1] if isinstance(out["fg"], (list, tuple)) else out["fg"]
            pred = (torch.sigmoid(fg) > 0.5).float().cpu()
            gt = batch["fg"]
            inter += float((pred * gt).sum())
            union += float(((pred + gt) >= 1).sum())
            if "dist" in out:                      # absent in the boundary-only ablation
                dpred = torch.sigmoid(out["dist"]).float().cpu()
                dist_abs += float((dpred - batch["dist"]).abs().sum())
                dist_n += batch["dist"].numel()
    iou = inter / union if union > 0 else 0.0
    mae = dist_abs / dist_n if dist_n > 0 else float("nan")
    return iou, mae


def cosine_lr(step, total, base_lr, warmup):
    if step < warmup:
        return base_lr * (step + 1) / max(1, warmup)
    p = (step - warmup) / max(1, total - warmup)
    return 0.5 * base_lr * (1 + math.cos(math.pi * min(1.0, p)))


def move(batch, device):
    return {k: (v.to(device, non_blocking=True) if torch.is_tensor(v) else v)
            for k, v in batch.items()}


# --------------------------------------------------------------------------
def overfit(model, loader, device, amp_dtype, steps, w_dist, w_bnd):
    """Train on ONE fixed batch; loss must fall toward zero."""
    batch = move(next(iter(loader)), device)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    model.train()
    log.info("overfit sanity: %d steps on one fixed batch (loss should drop)", steps)
    first = None
    for s in range(steps):
        with torch.autocast(device_type=device.type, dtype=amp_dtype,
                            enabled=(device.type == "cuda")):
            out = model(batch["image"])
            loss, comp = instance_loss(out, batch, w_dist=w_dist, w_bnd=w_bnd)
        opt.zero_grad(); loss.backward(); opt.step()
        first = first if first is not None else comp["total"]
        if s % max(1, steps // 12) == 0 or s == steps - 1:
            log.info("  step %3d  total %.4f  (fg %.3f dist %.3f bnd %.3f)",
                     s, comp["total"], comp["fg"], comp["dist"], comp["bnd"])
    drop = 100.0 * (1 - comp["total"] / first) if first else 0.0
    ok = comp["total"] < 0.6 * first
    log.info("overfit result: %.4f -> %.4f  (%.0f%% drop)  %s",
             first, comp["total"], drop,
             "PASS - learning path works" if ok else "WARN - loss did not drop enough")
    return ok


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Train instance-preserving U-Net++")
    ap.add_argument("--train-images", required=True)
    ap.add_argument("--train-targets", required=True)
    ap.add_argument("--val-images", default=None)
    ap.add_argument("--val-targets", default=None)
    ap.add_argument("--ckpt", default=None, help="Paper-1 checkpoint for transfer init")
    ap.add_argument("--out", default="runs/instance")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--crop", type=int, default=512)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--w-dist", type=float, default=1.0)
    ap.add_argument("--w-bnd", type=float, default=1.0)
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--num-workers", type=int, default=0)
    ap.add_argument("--seed", type=int, default=None,
                    help="seed torch/numpy/random and make cuDNN deterministic; "
                         "required for any run that must be reproducible")
    ap.add_argument("--no-distance-head", action="store_true",
                    help="ablation: train without the distance head")
    ap.add_argument("--no-boundary-head", action="store_true",
                    help="ablation: train without the boundary head")
    ap.add_argument("--grad-checkpoint", action="store_true")
    ap.add_argument("--resume", default=None)
    ap.add_argument("--overfit", type=int, default=0,
                    help="run the single-batch sanity check for N steps and exit")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    # Seed everything BEFORE the model is built, so head initialisation is part
    # of what the seed controls. Without this the four ablation runs would
    # differ by initialisation and augmentation as well as by architecture,
    # which makes the comparison meaningless.
    if a.seed is not None:
        import random as _random
        _random.seed(a.seed)
        np.random.seed(a.seed)
        torch.manual_seed(a.seed)
        torch.cuda.manual_seed_all(a.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        os.environ.setdefault("PYTHONHASHSEED", str(a.seed))
        log.info("seeded run: seed=%d, cudnn.deterministic=True", a.seed)
    else:
        log.warning("no --seed given: this run is NOT reproducible")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp_dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
    log.info("device %s | amp %s", device, amp_dtype if device.type == "cuda" else "off")

    model = build_instance_model(base_channels=a.base_channels, depth=a.depth,
                                 gradient_checkpointing=a.grad_checkpoint,
                                 use_distance_head=not a.no_distance_head,
                                 use_boundary_head=not a.no_boundary_head)
    if a.ckpt and not a.resume:
        load_paper1_backbone(model, a.ckpt)
    model.to(device)

    train_loader = make_loader(a.train_images, a.train_targets,
                               batch_size=a.batch_size, crop_size=a.crop,
                               augment=True, shuffle=True, num_workers=a.num_workers,
                               seed=a.seed)

    # ---- sanity mode ----
    if a.overfit:
        overfit(model, train_loader, device, amp_dtype, a.overfit, a.w_dist, a.w_bnd)
        return 0

    val_loader = None
    if a.val_images and a.val_targets:
        val_loader = make_loader(a.val_images, a.val_targets,
                                 batch_size=1, crop_size=0, augment=False,
                                 shuffle=False, num_workers=a.num_workers,
                                 seed=a.seed)

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    steps_per_epoch = max(1, len(train_loader))
    total_steps = a.epochs * steps_per_epoch

    start_epoch, best_score, gstep = 0, -1.0, 0
    if a.resume and os.path.isfile(a.resume):
        ck = torch.load(a.resume, map_location="cpu", weights_only=False)
        model.load_state_dict(ck["model_state_dict"])
        opt.load_state_dict(ck["optimizer_state_dict"])
        start_epoch = ck.get("epoch", 0) + 1
        best_score = ck.get("best_score", -1.0)
        gstep = ck.get("gstep", 0)
        log.info("resumed from %s at epoch %d", a.resume, start_epoch)

    log.info("training: %d epochs x %d steps = %d total; %d train images%s",
             a.epochs, steps_per_epoch, total_steps, len(train_loader.dataset),
             f", {len(val_loader.dataset)} val" if val_loader else "")

    for epoch in range(start_epoch, a.epochs):
        model.train()
        t0 = time.time(); run = 0.0
        for batch in train_loader:
            lr = cosine_lr(gstep, total_steps, a.lr, a.warmup)
            for g in opt.param_groups:
                g["lr"] = lr
            batch = move(batch, device)
            with torch.autocast(device_type=device.type, dtype=amp_dtype,
                                enabled=(device.type == "cuda")):
                out = model(batch["image"])
                loss, comp = instance_loss(out, batch, w_dist=a.w_dist, w_bnd=a.w_bnd)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            run += comp["total"]; gstep += 1

        tr_loss = run / steps_per_epoch
        msg = f"epoch {epoch:3d} | train loss {tr_loss:.4f} | lr {lr:.2e} | {time.time()-t0:.0f}s"

        score = -tr_loss
        if val_loader is not None:
            iou, mae = iou_and_dist_error(model, val_loader, device, amp_dtype)
            # A boundary-only ablation has no distance head, so mae is nan and
            # `iou - mae` is nan, which never beats best_score -- the run then
            # trains to completion and saves no best.pt at all. Fall back to
            # IoU alone when the distance term is undefined.
            if math.isnan(mae):
                score = iou
                msg += f" | val IoU {iou:.4f} | val dist-MAE n/a (no distance head)"
            else:
                score = iou - mae                   # IoU up, distance error down
                msg += f" | val IoU {iou:.4f} | val dist-MAE {mae:.4f}"

        # always save 'last'
        torch.save({"model_state_dict": model.state_dict(),
                    "optimizer_state_dict": opt.state_dict(),
                    "epoch": epoch, "best_score": best_score, "gstep": gstep,
                    "config": {"base_channels": a.base_channels, "depth": a.depth}},
                   os.path.join(a.out, "last.pt"))
        if score > best_score:
            best_score = score
            torch.save({"model_state_dict": model.state_dict(),
                        "epoch": epoch, "score": score,
                        "config": {"base_channels": a.base_channels, "depth": a.depth}},
                       os.path.join(a.out, "best.pt"))
            msg += "  <- best"
        log.info(msg)

    log.info("done. best score %.4f. checkpoints in %s", best_score, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
