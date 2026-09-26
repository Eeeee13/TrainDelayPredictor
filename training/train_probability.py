"""Train probability only; preserve competition regression and submission files.

python -m training.train_probability --data /dataset --out /srv/model
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from training import train as ml
from model.probability import fit_probability


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    root = Path(args.data)
    labels, features = [], []
    train_schedule = None
    train_traffic = None
    for split in ['train', 'test']:
        lab = pd.read_csv(root / f'labels/labels_{split}.csv')
        sched = ml.load_schedule(root / f'{split}/schedule.csv')
        traffic = ml.load_traffic(root / f'{split}/traffic.csv')
        features.append(ml.build(lab, sched, traffic))
        labels.append(lab)
        if split == 'train':
            train_schedule, train_traffic = sched, traffic
    lab = pd.concat(labels, ignore_index=True)
    X = pd.concat(features, ignore_index=True)
    gen = ml.generate_points(train_schedule)
    # Same validate-neighborhood exclusion as the competition regression.
    val = pd.read_csv(root / 'validate/points.csv').assign(T=lambda f: pd.to_datetime(f['T']))
    merged = gen.merge(val[['tr_id', 'T']].rename(columns={'T': 'T_val'}), on='tr_id', how='left')
    bad = merged.loc[(merged['T']-merged.T_val).abs() < pd.Timedelta('5min'), 'sample_id'].unique()
    gen = gen[~gen.sample_id.isin(bad)].reset_index(drop=True)
    real = lab.tr_id.to_numpy() < 9_000_000
    # Preserve final regression ordering: real points, generated points, synthetic points.
    X = pd.concat([X[real], ml.build(gen, train_schedule, train_traffic), X[~real]], ignore_index=True)
    y = np.concatenate([lab.target_delay_s[real], gen.target_delay_s, lab.target_delay_s[~real]])
    tr = np.concatenate([lab.tr_id[real], gen.tr_id, lab.tr_id[~real]])
    groups = [ml.source_vehicle(v) for v in tr]
    mask = np.r_[np.ones(real.sum(), dtype=bool), np.zeros(len(gen)+(~real).sum(), dtype=bool)]
    probability = fit_probability(X, y, groups, mask, params=ml.PARAMS, rounds=ml.N_ROUNDS)
    probability.save(args.out)
    print(json.dumps(probability.calibration, indent=2))


if __name__ == '__main__':
    main()
