"""Historical replay: causal labels, complete model bundles, guarded publication."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from training import train as ml
from model.probability import (InsufficientProbabilityData, event_target, fit_probability,
                               probability_metrics, validate_bundle)
from ml_pipeline.registry import publication_lock, reference_identity

DATA = Path(os.getenv('DATASET_DIR', '/dataset'))
ARTIFACTS = Path(os.getenv('MODEL_DIR', '/models'))
WORK = Path(os.getenv('PIPELINE_WORK_DIR', '/pipeline-work'))
DEFAULT_MODEL = Path(os.getenv('DEFAULT_MODEL', '/opt/airflow/model/model.txt'))
SPEED = float(os.getenv('TRAIN_REPLAY_SPEED', '6'))
CACHE_VERSION = 'causal-bundle-v2'


def write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False))
    os.replace(tmp, path)


def _clock():
    WORK.mkdir(parents=True, exist_ok=True)
    anchor_file = WORK / 'replay_anchor.json'
    if anchor_file.exists():
        anchor = json.loads(anchor_file.read_text())
    else:
        dates = pd.to_datetime(pd.read_csv(DATA / 'train/schedule.csv', usecols=['time_begin']).time_begin, format='mixed')
        start = dates.min() + (dates.max() - dates.min()) / 2
        anchor = {'start': start.isoformat(), 'wall': dt.datetime.now(dt.timezone.utc).isoformat()}
        write_json(anchor_file, anchor)
    elapsed = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(anchor['wall'])
    return pd.Timestamp(anchor['start']) + elapsed * SPEED


def available_labels(labels, schedule, cutoff):
    """Join on the planned visit, never on proximity or planned time alone."""
    labels = labels.copy()
    schedule = schedule.copy()
    labels['T'] = pd.to_datetime(labels['T'], format='mixed', errors='coerce')
    labels['target_time_begin'] = pd.to_datetime(labels.target_time_begin, format='mixed', errors='coerce')
    schedule['time_begin'] = pd.to_datetime(schedule.time_begin, format='mixed', errors='coerce')
    schedule['time_fact_begin'] = pd.to_datetime(schedule.time_fact_begin, format='mixed', errors='coerce')
    keys = ['tr_id', 'target_stop_id', 'target_time_begin']
    facts = schedule.rename(columns={'tt_action_item_id':'target_stop_id', 'time_begin':'target_time_begin'})
    ambiguous = facts.duplicated(keys, keep=False)
    ambiguous_keys = facts.loc[ambiguous, keys].drop_duplicates().assign(ambiguous=True)
    facts = facts.loc[~ambiguous, keys + ['time_fact_begin']]
    joined = labels.merge(facts, on=keys, how='left', indicator=True).merge(ambiguous_keys, on=keys, how='left')
    invalid = joined[keys].isna().any(axis=1) | joined['T'].isna()
    for column in ['target_delay_s', 'cur_dev_s']:
        invalid |= ~np.isfinite(pd.to_numeric(joined[column], errors='coerce'))
    invalid |= joined.sample_id.isna() | joined.sample_id.duplicated(keep=False)
    is_ambiguous = joined.ambiguous.eq(True)
    missing = joined['_merge'].ne('both') & ~is_ambiguous
    bad_fact = joined.time_fact_begin.isna() & ~missing & ~is_ambiguous
    eligible = ~(invalid | is_ambiguous | missing | bad_fact)
    ready = eligible & (joined.time_fact_begin <= cutoff) & (joined['T'] <= cutoff)
    report = {'total':len(labels), 'invalid':int(invalid.sum()), 'ambiguous':int(is_ambiguous.sum()),
              'unmatched':int(missing.sum()), 'invalid_fact':int(bad_fact.sum()),
              'pending':int((eligible & ~ready).sum()), 'available':int(ready.sum())}
    return joined.loc[ready, labels.columns].reset_index(drop=True), report


def check_new_labels():
    cutoff = _clock()
    schedule = pd.read_csv(DATA / 'train/schedule.csv')
    labels, report = available_labels(pd.read_csv(DATA / 'labels/labels_train.csv'), schedule, cutoff)
    write_json(WORK / 'latest-label-report.json', report)
    if labels.empty:
        return None
    digest = hashlib.sha256(CACHE_VERSION.encode())
    for relative in ['train/schedule.csv', 'train/traffic.csv', 'labels/labels_train.csv',
                     'test/schedule.csv', 'test/traffic.csv', 'labels/labels_test.csv']:
        with (DATA / relative).open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
    # Includes causal generated targets becoming available even without new organizer labels.
    facts = pd.to_datetime(schedule.time_fact_begin, format='mixed', errors='coerce')
    digest.update(schedule.loc[facts <= cutoff].to_csv(index=False).encode())
    digest.update(labels.to_csv(index=False).encode())
    digest.update(json.dumps(ml.PARAMS, sort_keys=True).encode())
    digest.update(str(ml.N_ROUNDS).encode())
    identifier = CACHE_VERSION + '-' + digest.hexdigest()[:16]
    if (WORK / identifier / 'processed.json').exists():
        return None
    return json.dumps({'cutoff':cutoff.isoformat(), 'dataset_id':identifier, 'cache_version':CACHE_VERSION})


def snapshot(spec):
    params = json.loads(spec)
    path = WORK / params['dataset_id']
    path.mkdir(parents=True, exist_ok=True)
    if (path / 'snapshot.json').exists():
        return str(path)
    cutoff = pd.Timestamp(params['cutoff'])
    schedule = pd.read_csv(DATA / 'train/schedule.csv')
    labels, report = available_labels(pd.read_csv(DATA / 'labels/labels_train.csv'), schedule, cutoff)
    fact = pd.to_datetime(schedule.time_fact_begin, format='mixed', errors='coerce')
    ambiguous = schedule.duplicated(['tr_id', 'tt_action_item_id', 'time_begin'], keep=False)
    report['ambiguous_schedule_rows'] = int(ambiguous.sum())
    report['invalid_schedule_facts'] = int(fact.isna().sum())
    schedule['time_fact_begin'] = fact.mask((fact > cutoff) | ambiguous)
    traffic = pd.read_csv(DATA / 'train/traffic.csv')
    traffic = traffic[pd.to_datetime(traffic.event_time, format='mixed') <= cutoff]
    schedule.to_csv(path / 'schedule.csv', index=False)
    traffic.to_csv(path / 'traffic.csv', index=False)
    labels.to_csv(path / 'labels.csv', index=False)
    write_json(path / 'label-report.json', report)
    # Pin evaluation data as well: retries must use the same cohort.
    for name, relative in [('test-labels.csv','labels/labels_test.csv'), ('test-schedule.csv','test/schedule.csv'), ('test-traffic.csv','test/traffic.csv')]:
        shutil.copyfile(DATA / relative, path / name)
    write_json(path / 'snapshot.json', params)
    return str(path)


def generate_causal_points(sched, cutoff):
    rows = []
    for tr, s in sched.items():
        if tr >= 9_000_000 or len(s) < 2:
            continue
        s = s.copy()
        ambiguous = s.duplicated(['tt_action_item_id', 'time_begin'], keep=False)
        s.loc[ambiguous, 'time_fact_begin'] = pd.NaT
        tb = s.time_begin.to_numpy()
        facts = s.time_fact_begin.to_numpy()
        delay = (s.time_fact_begin-s.time_begin).dt.total_seconds().to_numpy()
        end = min(pd.Timestamp(tb[-1]), cutoff)
        for T in pd.date_range(pd.Timestamp(tb[0]).floor('min')-pd.Timedelta('15min'), end, freq='1min'):
            t = T.to_datetime64()
            target = np.searchsorted(tb, t+np.timedelta64(10,'m'), side='right')
            if target >= len(s) or tb[target] > t+np.timedelta64(15,'m'):
                continue
            if np.isnat(facts[target]) or facts[target] > cutoff.to_datetime64():
                continue
            past = np.flatnonzero(~np.isnat(facts) & (facts <= t))
            last = past[np.argmax(facts[past])] if len(past) else None
            current = float(delay[last]) if last is not None else 0.0
            rows.append((f'{tr}_{int(T.timestamp())}', tr, T, s.tt_action_item_id.iat[target], tb[target], current, float(delay[target])))
    return pd.DataFrame(rows, columns=['sample_id','tr_id','T','target_stop_id','target_time_begin','cur_dev_s','target_delay_s'])


def build_features(path):
    root = Path(path)
    if (root / 'features.pkl').exists():
        return path
    sched, traffic = ml.load_schedule(root / 'schedule.csv'), ml.load_traffic(root / 'traffic.csv')
    labels = pd.read_csv(root / 'labels.csv')
    cutoff = pd.Timestamp(json.loads((root / 'snapshot.json').read_text())['cutoff'])
    generated = generate_causal_points(sched, cutoff)
    # Avoid weighting the identical organizer point twice.
    generated = generated[~generated.sample_id.isin(labels.sample_id)]
    points = pd.concat([labels, generated], ignore_index=True)
    X = ml.build(points, sched, traffic)
    groups = np.array([ml.source_vehicle(v) for v in points.tr_id])
    mask = np.r_[labels.tr_id.to_numpy() < 9_000_000, np.zeros(len(generated), dtype=bool)]
    bundle = {'X': X, 'y':points.target_delay_s, 'groups':groups, 'calibration_mask':mask}
    pd.to_pickle(bundle, root / 'features.tmp')
    os.replace(root / 'features.tmp', root / 'features.pkl')
    write_json(root / 'example-counts.json', {'organizer':len(labels), 'generated':len(generated)})
    return path


def train_candidate(path):
    root = Path(path)
    if (root / 'training.json').exists():
        return path
    bundle = pd.read_pickle(root / 'features.pkl')
    try:
        probability = fit_probability(bundle['X'], bundle['y'], bundle['groups'], bundle['calibration_mask'], params=ml.PARAMS, rounds=ml.N_ROUNDS)
    except InsufficientProbabilityData as exc:
        write_json(root / 'training.json', {'status':'skipped', 'reason':str(exc)})
        return path
    model = ml.fit(bundle['X'], bundle['y'])
    model.save_model(str(root / 'model.txt'))
    probability.save(root)
    validate_bundle(root, required=True)
    write_json(root / 'training.json', {'status':'ready'})
    return path


def evaluate(path):
    root = Path(path)
    training = json.loads((root / 'training.json').read_text())
    if training['status'] != 'ready':
        write_json(root / 'evaluation.json', {'eligible':False, 'reason':training['reason']})
        return path
    with publication_lock(ARTIFACTS):
        reference, identity = reference_identity(ARTIFACTS, DEFAULT_MODEL)
        previous, previous_probability = validate_bundle(reference.parent, required=identity.get('bundle_version', 1) >= 2)
    candidate, probability = validate_bundle(root, required=True)
    labels = pd.read_csv(root / 'test-labels.csv')
    X = ml.build(labels, ml.load_schedule(root / 'test-schedule.csv'), ml.load_traffic(root / 'test-traffic.csv'))
    y = labels.target_delay_s.to_numpy()
    candidate_values, previous_values = ml.predict(candidate, X), ml.predict(previous, X)
    if not len(y) or not np.isfinite(np.r_[y, candidate_values, previous_values]).all():
        write_json(root / 'evaluation.json', {'eligible':False, 'reason':'nonfinite or empty evaluation', 'reference':identity})
        return path
    metrics = {'candidate_mae':ml.mae(y, candidate_values), 'reference_mae':ml.mae(y, previous_values),
               'candidate_probability':probability_metrics(event_target(y), probability.predict(X)), 'reference':identity,
               'evaluation_note':'Fixed test is used for selection. The bundled competition regressor was trained on test; comparison is not an independent quality estimate.'}
    if previous_probability:
        metrics['reference_probability'] = probability_metrics(event_target(y), previous_probability.predict(X))
    metrics['eligible'] = (metrics['candidate_mae'] < metrics['reference_mae'] and
        ('reference_probability' not in metrics or metrics['candidate_probability']['brier'] <= metrics['reference_probability']['brier']))
    write_json(root / 'evaluation.json', metrics)
    return path


def publish(path):
    root = Path(path)
    while True:
        metrics = json.loads((root / 'evaluation.json').read_text())
        changed = False
        with publication_lock(ARTIFACTS):
            if 'reference' in metrics:
                _, identity = reference_identity(ARTIFACTS, DEFAULT_MODEL)
                changed = identity != metrics['reference']
            if not changed:
                if not metrics['eligible']:
                    write_json(root / 'processed.json', {'published':False, 'metrics':metrics})
                    return False
                validate_bundle(root, required=True)
                version = root.name
                metadata = {'version':version, 'dataset_id':version, 'bundle_version':2,
                            'metrics':metrics, 'features':ml.FEATURES, 'delay_threshold_s':120}
                target = ARTIFACTS / version
                if not target.exists():
                    tmp = Path(tempfile.mkdtemp(prefix='.bundle-', dir=ARTIFACTS))
                    try:
                        for name in ['model.txt','classifier.txt','calibrator.json']:
                            shutil.copyfile(root / name, tmp / name)
                        write_json(tmp / 'metadata.json', metadata)
                        validate_bundle(tmp, required=True)
                        os.replace(tmp, target)
                    finally:
                        if tmp.exists():
                            shutil.rmtree(tmp)
                validate_bundle(target, required=True)
                write_json(ARTIFACTS / 'active.json', json.loads((target / 'metadata.json').read_text()))
                write_json(root / 'processed.json', {'published':True, 'metrics':metrics})
                return True
        evaluate(path)
