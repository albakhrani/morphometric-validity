#!/usr/bin/env python3
"""
Phase 10 - Instance-segmentation dataset  (Paper 2, Option B)
=============================================================
Pairs each LIVECell image with its instance targets (from phase 9) and serves
tensors for training the instance-preserving head.

Each item is a dict of full-resolution tensors:
    image  (1, H, W)  float32, percentile-normalised to [0, 1]  (matches the
                      inference normalisation that reproduces Paper-1 IoU)
    fg     (1, H, W)  float32 in {0,1}   foreground
    bnd    (1, H, W)  float32 in {0,1}   instance boundary
    dist   (1, H, W)  float32 in [0,1]   per-cell distance (watershed markers)
    name   str        source image filename

Augmentation (train only): random crop + horizontal/vertical flip + (for square
crops) 90-degree rotation. All transforms are isometries applied identically to
the image and every target, so the distance map stays valid.

Normalisation is percentile(1,99) clip, identical to phase5a's corrected
inference, so the model sees the same input statistics at train and test time.

Usage (as a library):
    from phase10_dataset import make_loader
    train = make_loader("data/raw/livecell_train_images",
                        "instance_targets/train", batch_size=2, crop_size=512)
"""
from __future__ import annotations

import logging
import os
from typing import List, Tuple

import numpy as np

try:
    import torch
    from torch.utils.data import Dataset, DataLoader
except Exception as exc:                      # pragma: no cover
    raise RuntimeError("PyTorch is required for phase10_dataset") from exc

log = logging.getLogger("dataset")

IMAGE_EXTS = (".tif", ".tiff", ".png", ".jpg", ".jpeg")


def _read_image(path: str) -> np.ndarray:
    """Read a (possibly LZW-compressed) image as a 2-D array; try several backends."""
    errs = []
    for loader in ("imageio", "PIL", "tifffile"):
        try:
            if loader == "imageio":
                import imageio.v2 as iio
                a = iio.imread(path)
            elif loader == "PIL":
                from PIL import Image
                a = np.array(Image.open(path))
            else:
                import tifffile
                a = tifffile.imread(path)
            return a[..., 0] if a.ndim == 3 else a
        except Exception as e:
            errs.append(f"{loader}: {e}")
    raise RuntimeError(f"cannot read {path} | " + "; ".join(errs))


def _percentile_norm(img: np.ndarray, lo_p: float = 1.0, hi_p: float = 99.0) -> np.ndarray:
    a = img.astype(np.float32)
    lo, hi = np.percentile(a, lo_p), np.percentile(a, hi_p)
    return np.clip((a - lo) / (hi - lo + 1e-6), 0.0, 1.0) if hi > lo else a * 0.0


class InstanceSegDataset(Dataset):
    def __init__(self,
                 image_dir: str,
                 target_dir: str,
                 crop_size: int = 512,
                 augment: bool = True,
                 norm: str = "percentile"):
        self.image_dir = image_dir
        self.target_dir = target_dir
        self.crop_size = crop_size
        self.augment = augment
        self.norm = norm

        targets = [f for f in os.listdir(target_dir) if f.endswith(".npz")]
        pairs: List[Tuple[str, str]] = []
        missing = 0
        for t in sorted(targets):
            stem = t[:-4]
            img_path = None
            for e in IMAGE_EXTS:
                p = os.path.join(image_dir, stem + e)
                if os.path.isfile(p):
                    img_path = p
                    break
            if img_path is None:
                missing += 1
                continue
            pairs.append((img_path, os.path.join(target_dir, t)))
        if not pairs:
            raise RuntimeError(
                f"no image/target pairs found: images in {image_dir!r} do not "
                f"match target stems in {target_dir!r}")
        if missing:
            log.warning("%d targets had no matching image and were skipped", missing)
        self.pairs = pairs
        log.info("dataset: %d pairs  (crop=%s, augment=%s)",
                 len(pairs), crop_size, augment)

    def __len__(self) -> int:
        return len(self.pairs)

    def _load(self, idx: int):
        img_path, tgt_path = self.pairs[idx]
        img = _read_image(img_path)
        if self.norm == "percentile":
            img = _percentile_norm(img)
        else:
            a = img.astype(np.float32)
            m = a.max()
            img = a / m if m > 1.5 else a
        d = np.load(tgt_path)
        fg = d["fg"].astype(np.float32)
        bnd = d["bnd"].astype(np.float32)
        dist = d["dist"].astype(np.float32)
        return img.astype(np.float32), fg, bnd, dist, os.path.basename(img_path)

    def __getitem__(self, idx: int):
        img, fg, bnd, dist, name = self._load(idx)
        H, W = img.shape
        cs = self.crop_size

        # Randomness comes from the TORCH generator, not the global np.random.
        # PyTorch reseeds each worker's torch RNG deterministically from the
        # DataLoader's generator and the epoch, so a seeded run reproduces
        # exactly while augmentation still varies between epochs. The previous
        # np.random calls were unseeded and identical across workers.
        def _randint(lo, hi):
            return int(torch.randint(lo, hi, (1,)).item())

        def _coin():
            return float(torch.rand(1).item()) < 0.5

        # crop
        if cs and (H > cs or W > cs):
            if self.augment:
                y0 = _randint(0, max(1, H - cs + 1))
                x0 = _randint(0, max(1, W - cs + 1))
            else:
                y0, x0 = (H - cs) // 2, (W - cs) // 2
            sl = (slice(y0, y0 + cs), slice(x0, x0 + cs))
            img, fg, bnd, dist = img[sl], fg[sl], bnd[sl], dist[sl]

        # augment (isometries only)
        if self.augment:
            if _coin():
                img, fg, bnd, dist = (a[:, ::-1] for a in (img, fg, bnd, dist))
            if _coin():
                img, fg, bnd, dist = (a[::-1, :] for a in (img, fg, bnd, dist))
            if img.shape[0] == img.shape[1] and _coin():
                k = _randint(1, 4)
                img, fg, bnd, dist = (np.rot90(a, k) for a in (img, fg, bnd, dist))

        def to_t(a):
            return torch.from_numpy(np.ascontiguousarray(a))[None].float()

        return {"image": to_t(img), "fg": to_t(fg), "bnd": to_t(bnd),
                "dist": to_t(dist), "name": name}


def make_loader(image_dir: str,
                target_dir: str,
                batch_size: int = 2,
                crop_size: int = 512,
                augment: bool = True,
                shuffle: bool = True,
                num_workers: int = 0,
                seed: int | None = None) -> DataLoader:
    """Convenience builder. num_workers=0 by default (safe on Windows).

    Pass `seed` to make shuffling and augmentation reproducible. Without it the
    loader behaves exactly as before.
    """
    ds = InstanceSegDataset(image_dir, target_dir, crop_size=crop_size, augment=augment)

    gen = None
    winit = None
    if seed is not None:
        gen = torch.Generator()
        gen.manual_seed(int(seed))

        def winit(worker_id: int) -> None:      # noqa: F811
            import random as _r
            s = (int(seed) + worker_id) % (2 ** 31 - 1)
            np.random.seed(s)
            _r.seed(s)

    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle,
                      num_workers=num_workers, pin_memory=torch.cuda.is_available(),
                      drop_last=augment, generator=gen, worker_init_fn=winit)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    ap = argparse.ArgumentParser(description="Inspect the instance dataset")
    ap.add_argument("--images", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--crop", type=int, default=512)
    a = ap.parse_args()
    ds = InstanceSegDataset(a.images, a.targets, crop_size=a.crop, augment=True)
    b = ds[0]
    print("one item:")
    for k in ("image", "fg", "bnd", "dist"):
        t = b[k]
        print(f"  {k:5s} shape {tuple(t.shape)}  range [{t.min():.3f}, {t.max():.3f}]")
    print("  name ", b["name"])
