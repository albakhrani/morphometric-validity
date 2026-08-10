# Morphometric validity is not a scalar — code, measurements and weights

Supporting material for the manuscript *Morphometric validity is not a
scalar: segmentation accuracy does not predict which biological conclusions
survive measurement* (Alareqi, Luo, AL-Bakhrani).

Everything reported in the paper is reproducible from this repository plus
the public [LIVECell](https://sartorius-research.github.io/LIVECell/)
dataset, which is not redistributed here.

## What is here

| directory | contents |
|---|---|
| `analysis/` | the measurement and evaluation pipeline, one script per stage |
| `figures_code/` | one script per manuscript figure, plus the type-size checker |
| `data/` | per-image and per-lineage measurement tables backing every reported number |
| `weights/` | the trained instance-preserving checkpoint (2.22 M backbone + 66 head parameters) |

## Reproducing the reported numbers

Each table and figure traces to a file in `data/`:

| paper element | file |
|---|---|
| Table 1 (sample inventory) | no data file -- it tabulates the image counts the rows below are computed over |
| Table 2 (detection benchmark) + bootstrap CIs | `per_image_f1.csv`, `uncertainty.csv` |
| Table 3 (ablation) | `ablation_eval.csv` |
| Table 4 (operating points) + CIs | `per_image_tradeoff.csv`, `tradeoff_ci.csv` |
| Table 5 (inference cost) | no data file -- measured on hardware, not derived from a table |
| Table 6 (evidence-tiered atlas, all splits) | `atlas_lineage_table_allsplits.csv` |
| Table 7 (mask-source comparison) | `mask_source_comparison_per_image.csv`, `mask_source_trajectories.csv` |

Every table in the manuscript appears above. Tables 1 and 5 introduce no data file: the first is an inventory of the image counts used elsewhere, the second is a hardware measurement.
| coverage analysis | `coverage_by_lineage.csv`, `coverage_corrected_trajectories.csv`, `direction_counts.csv` |
| accuracy/validity envelope (Fig. 5A,B) | `envelope_v2_data.csv` |
| operating-point sweep (Fig. 5C,D) | `validation_sweep.csv`, `test_frozen.csv` |

The per-cell measurement table for the full atlas (1,085,227 cells) is 289 MB
and is not included; regenerate it with:

```bash
python analysis/phase1b_extract_features_8types.py \
  --coco livecell_coco_train.json livecell_coco_val.json livecell_coco_test.json \
  --out phase1_out_all
python analysis/phase4_final_table.py \
  --csv phase1_out_all/atlas_features_percell.csv \
  --coco livecell_coco_train.json livecell_coco_val.json livecell_coco_test.json \
  --out final_table_all
```

## Two scopes, deliberately different

The expert-only atlas uses **all 4,875** post-attachment annotated images
across the training, validation and test splits — it involves no model
prediction, so no leakage argument applies. The mask-source comparison uses
the **held-out test split only**, because evaluating model predictions on
training images would inflate our own results while leaving
connected-component labelling unaffected. Scripts and file names preserve
this distinction; do not merge the two.

## The boundary head does nothing

The released checkpoint carries both a distance head and a boundary head
(66 parameters total), because that is the model every reported number came
from. The ablation in `ablation_eval.csv` shows the boundary head
contributes under 0.01 in detection F1, and `phase13_watershed_infer.py`
never reads the boundary map during decoding — substituting an all-zero or
all-one boundary map leaves the recovered labels bit-identical. **A
reimplementation should build only the distance head: a single 1×1
convolution of 33 parameters.**

## Reproducibility

`phase12_train.py --seed N` seeds `torch`, `numpy` and `random`, sets
`cudnn.deterministic`, and passes the seed to the data loader. Two runs at
the same seed produce weight tensors with identical SHA-256 digests. Runs
without `--seed` warn that they are not reproducible.

## Figure typography

`figures_code/check_figure_type.py` reads the font-size operators out of
each figure PDF and reports the smallest size that actually reaches the
page, after the scale LaTeX applies at placement. Source font sizes are not
a reliable guide: matplotlib renders mathtext sub- and superscripts at
roughly 0.7× the base size. Run it after regenerating any figure.

## License

Code released under the MIT License. The LIVECell dataset is distributed by
its authors under its own terms and is not redistributed here.
