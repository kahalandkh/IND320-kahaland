import math

import numpy as np
import pandas as pd
from river import time_series
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def combine_weekly_data(reservoir, sources=None):
    """Join selected weekly data to the reservoir history."""
    return reservoir.join(list((sources or {}).values()), how="left")


def calendar_features(date):
    """Represent the annual cycle using sine and cosine features."""
    angle = 2 * math.pi * (pd.Timestamp(date).dayofyear - 1) / 365.25
    return {"annual_sin": math.sin(angle), "annual_cos": math.cos(angle)}


def forecast_reservoir(data, params, training_weeks=780, horizon=4, cutoff=None,
                       columns=None, exog_lag=None, use_calendar=True):
    """Forecast weekly reservoir filling using River's SNARIMAX model."""
    target = "reservoir_fill_ratio"

    if not isinstance(data, pd.DataFrame) or target not in data.columns:
        raise ValueError(f"Data must contain {target!r}.")
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.hasnans or data.index.has_duplicates:
        raise ValueError("Data must have unique, valid Sunday dates as its index.")
    if data.index.tz is not None or not (data.index.weekday == 6).all() or not (data.index == data.index.normalize()).all():
        raise ValueError("Data must use timezone-naive Sunday date labels.")
    if not isinstance(training_weeks, (int, np.integer)) or isinstance(training_weeks, (bool, np.bool_)) or training_weeks < 1:
        raise ValueError("training_weeks must be a positive integer.")
    if not isinstance(horizon, (int, np.integer)) or isinstance(horizon, (bool, np.bool_)) or horizon < 1:
        raise ValueError("horizon must be a positive integer.")
    if not isinstance(params, dict):
        raise ValueError("params must be a dictionary of SNARIMAX parameters.")

    # Use only explicitly selected external variables
    if columns is None:
        selected = []
    elif isinstance(columns, str):
        raise ValueError("columns must be a list of column names, not a string.")
    else:
        selected = list(columns)

    if target in selected or len(set(selected)) != len(selected):
        raise ValueError("External columns must be unique and must not include reservoir filling.")
    missing = set(selected) - set(data.columns)
    if missing:
        raise ValueError(f"Unknown external columns: {sorted(missing)}")

    # Use the forecast horizon as the default lag to avoid using future observations
    lag = horizon if exog_lag is None else exog_lag
    if selected and (not isinstance(lag, (int, np.integer)) or isinstance(lag, (bool, np.bool_)) or lag < horizon):
        raise ValueError(f"exog_lag must be an integer of at least {horizon} weeks.")

    # Use the latest available reservoir observation if no cutoff is specified
    data = data.sort_index()
    if cutoff is None:
        cutoff = data[target].last_valid_index()
    if cutoff is None:
        raise ValueError("No reservoir filling observations are available.")

    cutoff = pd.Timestamp(cutoff)
    if cutoff.tz is not None or cutoff.weekday() != 6 or cutoff != cutoff.normalize():
        raise ValueError("cutoff must be a timezone-naive Sunday date.")

    # Define the training and forecast periods
    train_dates = pd.date_range(end=cutoff, periods=training_weeks, freq="W-SUN")
    future_dates = pd.date_range(start=cutoff + pd.Timedelta(weeks=1), periods=horizon, freq="W-SUN")

    # Retrieve past observations for the selected exogenous variables
    def lagged_inputs(dates):
        features = pd.DataFrame(index=dates)
        for col in selected:
            features[f"{col}_lag_{lag}"] = data[col].reindex(dates - pd.Timedelta(weeks=lag)).to_numpy()
        return features

    train_x = lagged_inputs(train_dates)
    future_x = lagged_inputs(future_dates)
    train = pd.concat([data[target].reindex(train_dates), train_x], axis=1)

    if train.isna().any().any():
        missing = train.columns[train.isna().any()].tolist()
        raise ValueError(f"Incomplete {training_weeks}-week training period ending {cutoff.date()}. Missing data in: {missing}.")
    if not np.isfinite(train.to_numpy(dtype=float)).all():
        raise ValueError("Training data contain non-finite values.")
    if (train[target] < 0).any():
        raise ValueError("Reservoir filling cannot be negative.")
    if future_x.isna().any().any() or not np.isfinite(future_x.to_numpy(dtype=float)).all():
        raise ValueError("Missing or non-finite lagged exogenous values for the forecast period.")

    # Check that enough observations remain after differencing
    model = time_series.SNARIMAX(**params)
    
    if training_weeks <= model.differencer.n_required_past_values:
        raise ValueError("The training period is too short for the selected differencing orders.")

    # Train the model one week at a time
    for date, row in train.iterrows():
        x = calendar_features(date) if use_calendar else {}
        x.update({col: float(row[col]) for col in train_x.columns})
        model.learn_one(float(row[target]), x=x or None)

    # Forecast future weeks using the selected features
    if selected or use_calendar:
        xs = []
        for date, row in future_x.iterrows():
            x = calendar_features(date) if use_calendar else {}
            x.update({col: float(row[col]) for col in future_x.columns})
            xs.append(x)
        predictions = model.forecast(horizon=horizon, xs=xs)
    else:
        predictions = model.forecast(horizon=horizon)

    predictions = np.asarray(predictions, dtype=float)
    if predictions.shape != (horizon,) or not np.isfinite(predictions).all():
        raise ValueError("River returned invalid or non-finite predictions.")

    result = pd.DataFrame({"forecast_fill_ratio": predictions}, index=future_dates)
    result.index.name = "date_id"
    return result


def evaluate_forecast(actual, predicted):
    """Calculate MAE, RMSE and R^2 for reservoir filling forecasts."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if actual.ndim != 1 or predicted.ndim != 1 or len(actual) != len(predicted) or len(actual) == 0:
        raise ValueError("Actual and predicted values must be non-empty, equally sized 1D arrays.")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Actual and predicted values must be finite.")

    # Express forecast errors in percentage points
    mae = mean_absolute_error(actual, predicted) * 100
    rmse = np.sqrt(mean_squared_error(actual, predicted)) * 100

    # R^2 is undefined for a single observation or constant actual values
    r2 = r2_score(actual, predicted) if len(actual) > 1 and np.ptp(actual) > 0 else np.nan

    return {"MAE (pp)": mae, "RMSE (pp)": rmse, "R²": r2}