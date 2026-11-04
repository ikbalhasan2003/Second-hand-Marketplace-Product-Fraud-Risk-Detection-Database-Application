"""Serializable preprocessing fitted only on training rows."""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted

from ml.contract import FEATURE_NAMES


class FeatureImputer(TransformerMixin, BaseEstimator):
    """Median imputation; all-null price/location columns use contract constants."""

    def fit(self, values, y=None):
        values = np.asarray(values, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(FEATURE_NAMES):
            raise ValueError("Unexpected feature matrix shape")
        self.n_features_in_ = values.shape[1]
        self.statistics_ = np.array([
            float(np.median(column[~np.isnan(column)])) if (~np.isnan(column)).any()
            else (1.0 if FEATURE_NAMES[index] == "price_ratio" else 0.0)
            for index, column in enumerate(values.T)
        ])
        return self

    def transform(self, values):
        check_is_fitted(self, "statistics_")
        values = np.asarray(values, dtype=float)
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError("Unexpected feature matrix shape")
        if np.isinf(values).any():
            raise ValueError("Infinite predictors are prohibited")
        return np.where(np.isnan(values), self.statistics_, values)


def matrix(records):
    return np.asarray([
        [np.nan if record["features"][name] is None else record["features"][name] for name in FEATURE_NAMES]
        for record in records
    ], dtype=float)
