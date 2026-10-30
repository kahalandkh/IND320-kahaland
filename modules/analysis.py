import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.fft import dct, idct
from scipy.stats import median_abs_deviation



def precipitation_spc(data, cutoff_days=30, n_std=3):
    """Detect precipitation outliers using DCT high-pass filtering and robust SPC."""

    # Get precipitation values and timestamps
    dates = pd.DatetimeIndex(pd.to_datetime(data["date"]))
    values = data["precipitation"].to_numpy(dtype=float)

    # Check the input data
    if len(values) < 3 or dates.hasnans or not np.isfinite(values).all():
        raise ValueError("At least three valid precipitation observations are required.")

    if (values < 0).any():
        raise ValueError("Precipitation cannot be negative.")

    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Dates must be unique and in chronological order.")

    if not ((dates[1:] - dates[:-1]) == pd.Timedelta(hours=1)).all():
        raise ValueError("Precipitation data must have hourly intervals without gaps.")

    if not np.isfinite(cutoff_days) or cutoff_days < 2 / 24:
        raise ValueError("The cut-off period must be at least 2 hours for hourly data.")

    if not np.isfinite(n_std) or n_std <= 0:
        raise ValueError("n_std must be positive.")

    # DCT high-pass filtering
    frequencies = np.arange(len(values)) / (2 * (len(values) - 1))
    coefficients = dct(values, type=1, norm="forward")

    high_coefficients = coefficients.copy()
    high_coefficients[frequencies < 1 / (24 * cutoff_days)] = 0

    residual = idct(high_coefficients, type=1, norm="forward")
    baseline = values - residual

    # Robust SPC limits based on the filtered precipitation
    centre = np.median(residual)
    sigma = median_abs_deviation(residual, scale="normal")

    tolerance = 1e-12 * max(1, np.max(np.abs(values)))
    degenerate = sigma <= tolerance

    if degenerate:
        sigma = 0.0

    # Add the removed low-frequency component back to the limits
    lower = baseline + centre - n_std * sigma
    upper = baseline + centre + n_std * sigma

    below = values < lower - tolerance
    above = values > upper + tolerance
    outliers = below | above

    # Store the results
    result = pd.DataFrame({"date": dates,
                           "precipitation": values,
                           "baseline": baseline,
                           "residual": residual,
                           "lower": lower,
                           "upper": upper,
                           "outlier": outliers,
                           "side": np.where(above, "upper", np.where(below, "lower", "inlier"))})

    variance = np.var(values)

    summary = {"cutoff_days": cutoff_days,
               "n_std": n_std,
               "hours": len(values),
               "median_residual": centre,
               "robust_sigma": sigma,
               "degenerate_mad": degenerate,
               "upper_outliers": int(above.sum()),
               "lower_outliers": int(below.sum()),
               "outliers": int(outliers.sum()),
               "outlier_percent": 100 * outliers.mean(),
               "residual_variance_ratio": np.var(residual) / variance if variance else 0.0,
               "baseline_variance_ratio": np.var(baseline) / variance if variance else 0.0,
               "negative_baseline_hours": int((baseline < -tolerance).sum())}

    # Plot original precipitation with SPC boundaries and outliers
    fig, ax = plt.subplots(figsize=(12, 4.8))

    ax.plot(dates, values, linewidth=0.7, label="Average precipitation")
    ax.plot(dates, lower, color="#E69F00", linewidth=0.8, label="Lower SPC limit")
    ax.plot(dates, upper, color="#618E07", linewidth=0.8, label="Upper SPC limit")

    ax.scatter(dates[outliers], values[outliers], facecolors="none", edgecolors="#D50000", s=10,
               linewidths=0.55, alpha=0.85, label="Flagged hour", zorder=3)

    ax.set(xlabel="Time", ylabel="Hourly precipitation (mm)",
           title=f"Regional precipitation: {cutoff_days:g}-day DCT cut-off, {n_std:g} × SD")

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4, frameon=False)

    fig.tight_layout()

    return fig, result, summary