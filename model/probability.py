"""Calibrated P(delay > 120 s); JSON calibration needs no sklearn at inference."""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

THRESHOLD_S = 120
CLASSIFIER_FILE = 'classifier.txt'
CALIBRATOR_FILE = 'calibrator.json'


class InsufficientProbabilityData(ValueError):
    pass


def event_target(delay):
    return (np.asarray(delay, dtype=float) > THRESHOLD_S).astype(int)


class DelayProbability:
    def __init__(self, classifier, calibration):
        self.classifier = classifier
        self.calibration = calibration
        if calibration['threshold_s'] != THRESHOLD_S:
            raise ValueError('unsupported probability threshold')
        if calibration['features'] != classifier.feature_name():
            raise ValueError('classifier/calibrator feature mismatch')
        if not np.isfinite([calibration['coefficient'], calibration['intercept']]).all():
            raise ValueError('nonfinite calibration')

    @classmethod
    def load(cls, root, required=False):
        root = Path(root)
        model, cal = root / CLASSIFIER_FILE, root / CALIBRATOR_FILE
        if not model.exists() and not cal.exists() and not required:
            return None
        return cls(lgb.Booster(model_file=str(model)), json.loads(cal.read_text()))

    def predict(self, X):
        raw = self.classifier.predict(X[self.calibration['features']], raw_score=True)
        z = np.asarray(raw) * self.calibration['coefficient'] + self.calibration['intercept']
        probabilities = 1 / (1 + np.exp(-np.clip(z, -700, 700)))
        if not np.isfinite(probabilities).all():
            raise ValueError('nonfinite probabilities')
        return probabilities

    def save(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.classifier.save_model(str(root / CLASSIFIER_FILE))
        (root / CALIBRATOR_FILE).write_text(json.dumps(self.calibration, indent=2, allow_nan=False))


def fit_probability(X, delay, groups, calibration_mask, params=None, rounds=600):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold

    y = event_target(delay)
    groups = np.asarray(groups)
    mask = np.asarray(calibration_mask, dtype=bool)
    vehicles = np.unique(groups[mask])
    if len(vehicles) < 2 or np.unique(y[mask]).size < 2:
        raise InsufficientProbabilityData('need >=2 real vehicle groups and both classes for calibration')
    params = dict(params or {}, objective='binary', metric='binary_logloss', verbose=-1)
    oof = np.full(len(y), np.nan)
    for _, held in GroupKFold(min(6, len(vehicles))).split(vehicles, groups=vehicles):
        excluded = np.isin(groups, vehicles[held])
        if np.unique(y[~excluded]).size < 2:
            raise InsufficientProbabilityData('a training fold has only one class')
        model = lgb.train(params, lgb.Dataset(X.loc[~excluded], label=y[~excluded]), num_boost_round=rounds)
        idx = excluded & mask
        oof[idx] = model.predict(X.loc[idx], raw_score=True)
    if not np.isfinite(oof[mask]).all():
        raise ValueError('missing OOF predictions')
    calibration = LogisticRegression(random_state=42).fit(oof[mask].reshape(-1, 1), y[mask])
    classifier = lgb.train(params, lgb.Dataset(X, label=y), num_boost_round=rounds)
    result = DelayProbability(classifier, {
        'threshold_s': THRESHOLD_S, 'features': list(X.columns),
        'coefficient': float(calibration.coef_[0, 0]), 'intercept': float(calibration.intercept_[0]),
        'calibration_method': 'sigmoid on grouped OOF raw scores, real organizer points only',
        'calibration_examples': int(mask.sum()), 'vehicle_groups': int(len(vehicles)),
    })
    p = calibration.predict_proba(oof[mask].reshape(-1, 1))[:, 1]
    result.calibration['calibration_fit_metrics_not_independent'] = probability_metrics(y[mask], p)
    return result


def probability_metrics(y, p):
    y, p = np.asarray(y), np.asarray(p)
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError('invalid probabilities')
    clipped = np.clip(p, 1e-15, 1-1e-15)
    return {'brier': float(np.mean((p-y)**2)),
            'log_loss': float(-np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped)))}


def validate_bundle(root, required=False):
    root = Path(root)
    regression = lgb.Booster(model_file=str(root / 'model.txt'))
    probability = DelayProbability.load(root, required=required)
    if probability and regression.feature_name() != probability.calibration['features']:
        raise ValueError('regressor/classifier feature mismatch')
    return regression, probability
