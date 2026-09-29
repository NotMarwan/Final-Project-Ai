# SPDX-License-Identifier: UNLICENSED
"""WT-16 inference-acceleration measurement harness (bench/accel namespace).

Owned by WT-16 (InferenceAccel) per the S-20 split: everything in this package
is measurement code for runtime/export/precision acceleration experiments
(EXP-01..EXP-07, docs/campaign/experiments/). It never mutates the environment:
no pip installs, no model writes; artifacts land in bench/results/.
"""
