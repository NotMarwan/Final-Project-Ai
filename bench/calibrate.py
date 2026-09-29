"""Reproducible candidate temperature calibration from independently labeled scores.

Input JSON: {model_sha256, observations:[{clip_id, source_sha256, split,
label, score, label_source}]}. One score per clip; split is calibration/test.
Labels must originate from publisher annotations or independent human review.
This creates a CANDIDATE artifact; it never enables calibrated runtime claims.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

HASH = re.compile(r'^[a-f0-9]{64}$')

def validate(payload):
    if not HASH.fullmatch(str(payload.get('model_sha256', ''))):
        raise ValueError('A SHA-256 of the scored model is required')
    rows = payload.get('observations', [])
    seen_ids, seen_sources = set(), set()
    for row in rows:
        if not row.get('clip_id') or row['clip_id'] in seen_ids:
            raise ValueError('Clip IDs must be unique and nonempty')
        source = row.get('source_sha256', '')
        if not HASH.fullmatch(source) or source in seen_sources:
            raise ValueError('Source hashes must be unique; duplicated clips leak across splits')
        seen_ids.add(row['clip_id']); seen_sources.add(source)
        if row.get('split') not in {'calibration', 'test'}:
            raise ValueError('Each clip needs a calibration/test split')
        if type(row.get('label')) is not int or row['label'] not in (0, 1):
            raise ValueError('Labels must be binary integers')
        score = row.get('score')
        if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Scores must be finite probabilities in [0,1]')
        if row.get('label_source') not in {'publisher', 'independent-human'}:
            raise ValueError('Model, pseudo and synthetic labels cannot establish evaluation truth')
    for split in ('calibration', 'test'):
        labels = {row['label'] for row in rows if row['split'] == split}
        if labels != {0, 1}:
            raise ValueError('Both classes are required independently in each split')
    return rows

def scale(score, temperature):
    p = min(1-1e-12, max(1e-12, score))
    logit = (math.log(p) - math.log1p(-p)) / temperature
    if logit >= 0:
        return 1/(1+math.exp(-logit))
    exponent = math.exp(logit)
    return exponent/(1+exponent)

def metrics(rows, temperature=1.0, bins=15):
    values = [(scale(row['score'], temperature), row['label']) for row in rows]
    count = len(values)
    if not count: raise ValueError('Cannot measure an empty split')
    nll = sum(-math.log(max(1e-12, p if y else 1-p)) for p, y in values)/count
    brier = sum((p-y)**2 for p, y in values)/count
    ece = 0.0
    for index in range(bins):
        group = [(p,y) for p,y in values if min(bins-1, int(p*bins)) == index]
        if group:
            ece += abs(sum(p-y for p,y in group))/count
    return {'count': count, 'nll': nll, 'brier': brier, 'ece': ece, 'ece_bins': bins}

def calibrate(payload):
    rows = validate(payload)
    train = [row for row in rows if row['split'] == 'calibration']
    test = [row for row in rows if row['split'] == 'test']
    # Fixed log grid is deterministic and has no optimizer or library dependency.
    temperatures = [math.exp(math.log(.05)+i/600*math.log(400)) for i in range(601)] + [1.0]
    temperature = min(temperatures, key=lambda t: metrics(train,t)['nll'])
    return {'schema_version':1, 'status':'candidate-not-runtime-validated',
        'method':'binary-temperature-scaling', 'temperature':temperature,
        'model_sha256':payload['model_sha256'], 'calibration':metrics(train,temperature),
        'held_out_before':metrics(test), 'held_out_after':metrics(test,temperature),
        'reference':'https://proceedings.mlr.press/v70/guo17a.html',
        'limitations':['Scores are supplied measurements, not produced or verified by this tool.',
            'Label provenance is declared by the caller; no automatic assertion validates it.',
            'Clip-level calibration does not establish window-level calibration or camera-domain accuracy.',
            'No acceptance gate passes from creating this candidate artifact.']}

_TUNING_SPLITS = ('dev', 'val')  # val is WT-12's manifest name for the dev/tuning split


def _is_tuning(row):
    return row['split'] in _TUNING_SPLITS


def validate_sequences(payload, require_both_classes=True, model_sha256=None):
    """Validate per-window score sequences for N-of-M policy selection (EXP-20).

    ``require_both_classes=False`` enables the auxiliary false-positive screen
    (negatives-only evidence): it measures G-02 only and CANNOT select a policy.
    A bare list of sequence rows is accepted only when the caller supplies the
    scored-model SHA-256 explicitly (recorded in the report as externally bound).
    """
    if isinstance(payload, list):
        if not HASH.fullmatch(str(model_sha256 or '')):
            raise ValueError('A bare sequence list requires --model-sha256 binding the scored model')
        payload = {'model_sha256': model_sha256, 'sequences': payload}
    if not HASH.fullmatch(str(payload.get('model_sha256', ''))):
        raise ValueError('A SHA-256 of the scored model is required')
    rows = payload.get('sequences', [])
    if not rows:
        raise ValueError('At least one scored sequence is required')
    seen_ids, seen_sources = set(), set()
    for row in rows:
        clip_id = row.get('clip_id')
        if not clip_id or clip_id in seen_ids:
            raise ValueError('Clip IDs must be unique and nonempty')
        source = row.get('source_sha256', '')
        if not HASH.fullmatch(source) or source in seen_sources:
            raise ValueError('Source hashes must be unique; duplicated clips leak across splits')
        seen_ids.add(clip_id); seen_sources.add(source)
        if row.get('split') not in {'dev', 'val', 'test', 'train', 'calibration'}:
            raise ValueError('Split must be dev/val (tuning), test (reported once) or train/calibration (excluded)')
        if type(row.get('label')) is not int or row['label'] not in (0, 1):
            raise ValueError('Labels must be binary integers')
        if row.get('label_source') not in {'publisher', 'independent-human'}:
            raise ValueError('Model, pseudo and synthetic labels cannot establish evaluation truth')
        scores, valid = row.get('scores'), row.get('valid', [True] * len(row.get('scores') or []))
        starts = row.get('start_s')
        if not isinstance(scores, list) or not scores:
            raise ValueError('Each sequence needs a nonempty scores list')
        if not isinstance(valid, list) or len(valid) != len(scores):
            raise ValueError('valid flags must align with scores')
        if not isinstance(starts, list) or len(starts) != len(scores) or any(
                isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) or s < 0 for s in starts):
            raise ValueError('Each sequence needs per-window start_s timestamps (needed for cooldown replay)')
        for score in scores:
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Scores must be finite probabilities in [0,1]')
        if any(s1 <= s0 for s0, s1 in zip(starts, starts[1:])):
            raise ValueError('start_s must be strictly increasing within a sequence')
    for split in ('dev', 'val', 'test'):
        labels = {r['label'] for r in rows if r['split'] == split}
        if require_both_classes and labels and labels != {0, 1}:
            raise ValueError(f'Both classes are required independently in the {split} split')
    if require_both_classes and {r['label'] for r in rows if _is_tuning(r)} != {0, 1}:
        raise ValueError('The tuning split must contain both classes (nothing is tuned on test)')
    if not [r for r in rows if _is_tuning(r)]:
        raise ValueError('The tuning split must contain at least one scored sequence')
    return rows


def replay_sequence(row, policy_values):
    """Replay recorded windows through the REAL decision layer (no reimplementation)."""
    import sys
    from pathlib import Path as _Path
    root = _Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from backend.decision_config import DecisionConfig
    from backend.live_alert_decision import LiveAlertDecisionLayer
    layer = LiveAlertDecisionLayer(config=DecisionConfig.from_mapping(policy_values))
    votes_to_confirm = None
    confirmations = 0
    for index, (score, ok, start) in enumerate(zip(row['scores'], row['valid'], row['start_s'])):
        if not ok:
            continue
        result = layer.update(score, sample_time=float(start), sample_id=index + 1)
        if result['confirmed_alert']:
            confirmations += 1
            if votes_to_confirm is None:
                votes_to_confirm = index + 1
    return {'confirmed': confirmations > 0, 'confirmations': confirmations,
            'votes_to_confirm': votes_to_confirm}


def _max_weight_sum(policy):
    """Highest achievable confidence weight sum for a policy (feasibility bound)."""
    return policy['confirm_m'] * (1.0 + policy['confirm_weight_gain'])


def policy_grid(base):
    """Pre-registered EXP-20 grid; all candidates come from thresholds.toml defaults.

    ``confirm_threshold`` and ``watch_threshold`` are swept as the EXP-20 card
    declares; ``watch_threshold`` is held at min(0.45, confirm_threshold) because
    it only selects the WATCH/NORMAL display state and never affects confirmation.
    """
    candidates = []
    for confirm_threshold in (0.45, 0.5, 0.55, 0.6, 0.65):
        watch_threshold = min(base['watch_threshold'], confirm_threshold)
        for confirm_m in (3, 4, 5):
            for confirm_n in (2, 3):
                if confirm_n > confirm_m:
                    continue
                for weight_sum in (float(confirm_n), confirm_n + 0.5, confirm_n + 1.0, confirm_n + 1.5):
                    for gain in (0.0, 0.5, 1.0):
                        for gate in (0.0, 0.7, 0.8, 0.9):
                            candidates.append({**base, 'confirm_threshold': confirm_threshold,
                                               'watch_threshold': watch_threshold,
                                               'confirm_m': confirm_m, 'confirm_n': confirm_n,
                                               'confirm_weight_sum': weight_sum, 'confirm_weight_gain': gain,
                                               'cascade_gate_threshold': gate})
    return candidates


def select_policy(payload, grid=None, negatives_only=False, screen_splits=None, include_test=False,
                  model_sha256=None):
    """Select a confirmation policy on the tuning split only; report test once (EXP-20).

    ``negatives_only=True`` runs the auxiliary G-02 false-positive screen on
    negative-only evidence: it ranks candidates by measured confirmed false
    positives and explicitly DEFERS selection (no positive-class evidence
    exists, so no operating point may be claimed). ``screen_splits`` selects
    which non-test splits form the screening set (default: the tuning split);
    the test split can only enter with ``include_test=True``, which is recorded
    in the report as a consumed test split.
    """
    from pathlib import Path as _Path
    import sys
    root = _Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from backend.decision_config import load_decision_config
    rows = validate_sequences(payload, require_both_classes=not negatives_only,
                              model_sha256=model_sha256)
    model_binding = model_sha256 if isinstance(payload, list) else payload.get('model_sha256')
    tuning = [r for r in rows if _is_tuning(r)]
    test = [r for r in rows if r['split'] == 'test']
    excluded = {split: sum(1 for r in rows if r['split'] == split) for split in ('train', 'calibration')}
    excluded = {split: count for split, count in excluded.items() if count}
    if negatives_only:
        wanted = tuple(screen_splits) if screen_splits else _TUNING_SPLITS
        if 'test' in wanted and not include_test:
            raise ValueError('Refusing to screen on the test split without include_test=True (it would consume it)')
        dev = [r for r in rows if r['split'] in wanted]
        if not dev:
            raise ValueError(f'No rows match screen splits {sorted(wanted)}')
        excluded = {split: sum(1 for r in rows if r['split'] == split and split not in wanted)
                    for split in ('train', 'calibration', 'test')}
        excluded = {split: count for split, count in excluded.items() if count}
    else:
        dev = tuning
    base = load_decision_config().to_dict()
    candidates = grid if grid is not None else policy_grid(base)
    evaluated = []
    for policy_values in candidates:
        fp = tp = 0
        negatives = positives = 0
        votes = []
        confirmations = 0
        for row in dev:
            outcome = replay_sequence(row, policy_values)
            confirmations += outcome['confirmations']
            if row['label'] == 1:
                positives += 1
                tp += 1 if outcome['confirmed'] else 0
                if outcome['votes_to_confirm'] is not None:
                    votes.append(outcome['votes_to_confirm'])
            else:
                negatives += 1
                fp += 1 if outcome['confirmed'] else 0
        evaluated.append({
            'policy': {key: policy_values[key] for key in (
                'confirm_threshold', 'watch_threshold', 'confirm_n', 'confirm_m', 'confirm_weight_sum',
                'confirm_weight_gain', 'cascade_gate_threshold')},
            'true_positives': tp, 'positives': positives,
            'false_positives': fp, 'negatives': negatives,
            'total_confirmations': confirmations,
            'max_achievable_weight_sum': round(_max_weight_sum(policy_values), 4),
            'feasible': policy_values['confirm_weight_sum'] <= _max_weight_sum(policy_values) + 1e-9,
            'tp_rate': (tp / positives) if positives else None,
            'mean_votes_to_confirm': (sum(votes) / len(votes)) if votes else None,
        })
    feasible = [entry for entry in evaluated if entry['feasible']]
    if not feasible:
        raise ValueError('No feasible candidate policy in the grid (all weight sums exceed the reachable bound)')

    def rank(entry):
        return (entry['false_positives'], -(entry['tp_rate'] or 0.0),
                entry['policy']['confirm_weight_sum'], entry['mean_votes_to_confirm'] or float('inf'))
    selected = min(feasible, key=rank)
    meets = selected['false_positives'] == 0 and (selected['tp_rate'] or 0.0) >= 0.9
    if negatives_only:
        return {
            'schema_version': 1,
            'mode': 'false-positive-screen',
            'criteria': {'max_false_positives': 0, 'min_tp_rate': None, 'selection_split': 'dev',
                         'deferred': 'no positive-class evidence; G-02 only, no operating point claimed'},
            'selected': None,
            'meets_criteria': None,
            'feasible_policies': len(feasible),
            'infeasible_policies': len(evaluated) - len(feasible),
            'lowest_false_positive_policy': selected,
            'screen_splits': sorted(wanted),
            'model_sha256': model_binding,
            'test_consumed': 'test' in wanted,
            'rows_screened': len(dev),
            'windows_screened': sum(len(r['scores']) for r in dev),
            'excluded_rows': excluded,
            'dev': evaluated,
            'test': None,
        }
    report = {
        'schema_version': 1,
        'mode': 'selection',
        'criteria': {'max_false_positives': 0, 'min_tp_rate': 0.9, 'selection_split': 'dev'},
        'selected': selected,
        'meets_criteria': meets,
        'feasible_policies': len(feasible),
        'infeasible_policies': len(evaluated) - len(feasible),
        'model_sha256': model_binding,
        'excluded_rows': excluded,
        'dev': evaluated,
        'test': None,
    }
    if test:
        policy_values = {**base, **selected['policy']}
        test_rows = []
        for row in test:
            outcome = replay_sequence(row, policy_values)
            test_rows.append({'clip_id': row['clip_id'], 'label': row['label'], **outcome})
        report['test'] = {
            'rows': test_rows,
            'true_positives': sum(1 for r in test_rows if r['label'] == 1 and r['confirmed']),
            'positives': sum(1 for r in test_rows if r['label'] == 1),
            'false_positives': sum(1 for r in test_rows if r['label'] == 0 and r['confirmed']),
            'negatives': sum(1 for r in test_rows if r['label'] == 0),
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scores', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--select-policy', action='store_true',
                        help='treat the input as per-window sequences and run the EXP-20 policy sweep')
    parser.add_argument('--false-positive-screen', action='store_true',
                        help='negatives-only G-02 screen (ranks candidates, defers selection)')
    parser.add_argument('--screen-splits', default=None,
                        help='comma list of non-test splits forming the screen set (default: tuning splits)')
    parser.add_argument('--include-test-negatives', action='store_true',
                        help='acknowledge that screening consumes the test split (recorded in the report)')
    parser.add_argument('--model-sha256', default=None,
                        help='scored-model SHA-256 when the input is a bare sequence list')
    args = parser.parse_args()
    raw = args.scores.read_bytes()
    if args.select_policy or args.false_positive_screen:
        screen_splits = tuple(s.strip() for s in args.screen_splits.split(',')) if args.screen_splits else None
        try:
            result = select_policy(json.loads(raw), negatives_only=args.false_positive_screen,
                                   screen_splits=screen_splits,
                                   include_test=args.include_test_negatives,
                                   model_sha256=args.model_sha256)
        except (ValueError, TypeError, KeyError) as exc:
            parser.error(str(exc))
        result['input_sha256'] = hashlib.sha256(raw).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write('\n')
        headline = result['selected'] or result['lowest_false_positive_policy']
        print(json.dumps({'mode': result['mode'], 'headline_policy': headline['policy'],
                          'meets_criteria': result['meets_criteria']}))
        return
    try:
        result = calibrate(json.loads(raw))
    except (ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    result['input_sha256'] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an earlier calibration without an explicit distinct output path.
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write('\n')
    print(json.dumps(result['held_out_after']))

if __name__=='__main__': main()
