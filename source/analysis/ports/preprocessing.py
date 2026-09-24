"""Profile-specific transforms (CLR / Yeo-Johnson), RobustScaler, and KNN imputation."""

import logging
from typing import Any
import numpy as np
import pandas as pd
from scipy.stats import skew
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import (
    RobustScaler,
    PowerTransformer,
    FunctionTransformer,
)
from sklearn.impute import KNNImputer

from source.analysis.ports.array_types import FloatArray
from source.config.logger import setup_logging

logger = setup_logging(__name__)


def optimize_memory_usage(df: pd.DataFrame) -> pd.DataFrame:
    initial_mem = df.memory_usage(deep=True).sum() / 1024**2
    df = df.copy()

    for col in df.columns:
        col_type = df[col].dtype

        if pd.api.types.is_object_dtype(col_type):
            num_unique = df[col].nunique()
            num_total = len(df)
            if num_unique / max(num_total, 1) < 0.5:
                df[col] = df[col].astype("category")

        elif pd.api.types.is_integer_dtype(col_type):
            c_min = df[col].min()
            c_max = df[col].max()
            if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                df[col] = df[col].astype(np.int8)
            elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                df[col] = df[col].astype(np.int16)
            elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                df[col] = df[col].astype(np.int32)

        elif pd.api.types.is_float_dtype(col_type):
            df[col] = df[col].astype(np.float32)

    final_mem = df.memory_usage(deep=True).sum() / 1024**2
    reduction = (1 - final_mem / max(initial_mem, 1e-9)) * 100
    logger.info(
        f"Memory optimized: {initial_mem:.1f} MB -> {final_mem:.1f} MB "
        f"({reduction:.0f}% reduction)"
    )
    return df


def centered_log_ratio_transform(X_comp: FloatArray, pseudocount: float = 0.01) -> FloatArray:
    X = np.asarray(X_comp, dtype=np.float64).copy()

    X = np.where(X == 0, pseudocount, X)

    row_sums = X.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    X = X / row_sums

    # CLR: log(x_i / geometric_mean(x))
    log_X = np.log(X)
    mean_log = np.mean(log_X, axis=1, keepdims=True)
    X_clr = log_X - mean_log

    return X_clr


def _clr_wrapper(X: FloatArray) -> FloatArray:
    return centered_log_ratio_transform(X, pseudocount=0.01)


SKEWNESS_THRESHOLD = 0.75


def detect_skewed_columns(df: pd.DataFrame, cols: list[str]) -> list[str]:
    skewness = df[cols].apply(lambda x: skew(x.dropna()))
    skewed = skewness[abs(skewness) > SKEWNESS_THRESHOLD].index.tolist()
    if skewed:
        logger.info(f"Detected {len(skewed)} skewed columns: {skewed}")
    return skewed


PROFILE_TRANSFORMS = {
    "fleet_mix": {
        "transform": "clr",
        "scaler": "robust",
    },
    "operations": {
        "transform": "yeo_johnson",
        "scaler": "robust",
    },
    "scale": {
        "transform": "yeo_johnson",
        "scaler": "robust",
    },
    "infrastructure": {
        "transform": None,  # Ordinal features – no power transform needed
        "scaler": "robust",
    },
    "temporal": {
        "transform": "yeo_johnson",
        "scaler": "robust",
    },
    "connectivity": {
        "transform": "yeo_johnson",
        "scaler": "robust",
    },
}


def build_profile_preprocessor(profile_id: str, feature_cols: list[str]) -> Pipeline:
    if profile_id not in PROFILE_TRANSFORMS:
        raise ValueError(
            f"Unknown profile '{profile_id}'. "
            f"Valid profiles: {list(PROFILE_TRANSFORMS.keys())}"
        )

    config = PROFILE_TRANSFORMS[profile_id]
    steps: list[tuple[str, Any]] = []

    if config["transform"] == "clr":
        steps.append(("clr", FunctionTransformer(_clr_wrapper, validate=False)))
    elif config["transform"] == "yeo_johnson":
        steps.append(("yeo_johnson", PowerTransformer(method="yeo-johnson", standardize=False)))

    if config["scaler"] == "robust":
        steps.append(("scaler", RobustScaler()))

    pipeline = Pipeline(steps)
    logger.info(
        f"Built preprocessor for profile '{profile_id}' "
        f"({len(feature_cols)} features, steps: {[s[0] for s in steps]})"
    )
    return pipeline


def robust_imputation(
    df: pd.DataFrame,
    feature_cols: list[str],
    n_neighbors: int = 5,
) -> pd.DataFrame:
    data = df[feature_cols].copy()
    n_missing = data.isna().sum().sum()

    if n_missing == 0:
        logger.info("No missing values found – skipping imputation.")
        return df

    logger.info(f"Imputing {n_missing} missing values across {len(feature_cols)} features...")

    scaler = RobustScaler()
    data_scaled = scaler.fit_transform(data)

    imputer = KNNImputer(n_neighbors=n_neighbors, weights="distance")
    data_imputed_scaled = imputer.fit_transform(data_scaled)

    data_imputed = scaler.inverse_transform(data_imputed_scaled)

    result = df.copy()
    result[feature_cols] = data_imputed

    logger.info(f"Imputation complete. {n_missing} values filled.")
    return result
