import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.fft import dct, idct
from scipy.signal import spectrogram
from scipy.stats import median_abs_deviation
from sklearn.neighbors import LocalOutlierFactor
from statsmodels.tsa.seasonal import STL


def precipitation_spc(data, cutoff_days=30, n_std=3):
    """Find unusual hourly precipitation using a DCT high-pass filter and robust SPC."""

    dates = pd.DatetimeIndex(pd.to_datetime(data["date"]))
    values = data["precipitation"].to_numpy(dtype=float)

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

    # DCT-I bin k corresponds to k / (2*(N-1)) cycles/hour. Zero out periods longer than cutoff_days and use what remains to flag unusual rainfall
    frequencies = np.arange(len(values)) / (2 * (len(values) - 1))
    coefficients = dct(values, type=1, norm="forward")

    high_coefficients = coefficients.copy()
    high_coefficients[frequencies < 1 / (24 * cutoff_days)] = 0

    residual = idct(high_coefficients, type=1, norm="forward")
    baseline = values - residual

    # Rainfall peaks can pull the mean and SD upwards, so use median and MAD. The MAD scaling makes it comparable to an SD, but rainfall is not normally distributed
    centre = np.median(residual)
    sigma = median_abs_deviation(residual, scale="normal")

    tolerance = 1e-12 * max(1, np.max(np.abs(values)))
    degenerate = sigma <= tolerance

    if degenerate:
        sigma = 0.0

    # Put the limits back on the original rainfall scale (only the limits use the filter)
    lower = baseline + centre - n_std * sigma
    upper = baseline + centre + n_std * sigma

    below = values < lower - tolerance
    above = values > upper + tolerance
    outliers = below | above

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

    fig, ax = plt.subplots(figsize=(12, 4.8))

    ax.plot(dates, values, linewidth=0.7, label="Average precipitation")
    ax.plot(dates, lower, color="#E69F00", linewidth=0.8, label="Lower SPC limit")
    ax.plot(dates, upper, color="#618E07", linewidth=0.8, label="Upper SPC limit")

    ax.scatter(dates[outliers], values[outliers], facecolors="none", edgecolors="#D50000", s=10, linewidths=0.55, alpha=0.85, label="Flagged hour", zorder=3)

    ax.set(xlabel="Time", ylabel="Hourly precipitation (mm)", title=f"Regional precipitation: {cutoff_days:g}-day DCT cut-off, {n_std:g} × SD")

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4, frameon=False)
    fig.tight_layout()

    return fig, result, summary


def temperature_lof(data, contamination=0.01, n_neighbors=50, time_scale=0.02):
    """Find unusual hourly temperatures using LOF with temperature and scaled time."""

    dates = pd.DatetimeIndex(pd.to_datetime(data["date"]))
    values = data["temperature_2m"].to_numpy(dtype=float)

    if len(values) < 3 or dates.hasnans or not np.isfinite(values).all():
        raise ValueError("At least three valid temperature observations are required.")

    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Dates must be unique and in chronological order.")

    if not ((dates[1:] - dates[:-1]) == pd.Timedelta(hours=1)).all():
        raise ValueError("Temperature data must have hourly intervals without gaps.")

    if not np.isfinite(contamination) or not 0 < contamination <= 0.5:
        raise ValueError("contamination must be between 0 and 0.5.")

    if not isinstance(n_neighbors, (int, np.integer)) or not 1 < n_neighbors < len(values):
        raise ValueError("n_neighbors must be between 2 and the number of observations minus 1.")

    if not np.isfinite(time_scale) or time_scale < 0:
        raise ValueError("time_scale must be non-negative.")

    # LOF uses distances between points. At time_scale=0.02, 50 hours apart contributes as much to the distance as a 1°C difference
    time = np.arange(len(values)) * time_scale
    features = np.column_stack((values, time))

    model = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    anomalies = model.fit_predict(features) == -1

    # scikit-learn stores negative LOF values, so reverse the sign for easier reading
    scores = -model.negative_outlier_factor_

    result = pd.DataFrame({"date": dates,
                           "temperature_2m": values,
                           "lof_score": scores,
                           "anomaly": anomalies})

    summary = {"hours": len(values),
               "anomalies": int(anomalies.sum()),
               "anomaly_percent": 100 * anomalies.mean(),
               "contamination": contamination,
               "n_neighbors": n_neighbors,
               "time_scale": time_scale}

    fig, ax = plt.subplots(figsize=(12, 4.8))

    ax.plot(dates, values, linewidth=0.8, label="Average temperature")
    ax.scatter(dates[anomalies], values[anomalies], color="#D50000", s=18, label="LOF anomalies", zorder=3)

    ax.set(xlabel="Time", ylabel="Temperature (°C)", title="Hourly temperature and LOF anomalies")

    ax.legend()
    fig.tight_layout()

    return fig, result, summary


def reservoir_stl(series, seasonal=13, trend=89, robust=True):
    """Plot STL decomposition of weekly reservoir filling degree."""

    # Two yearly cycles give STL more than one repetition to estimate seasonality
    if len(series) < 104 or not np.isfinite(series.to_numpy(dtype=float)).all():
        raise ValueError("At least 104 valid weekly observations are required.")

    dates = series.index

    if (not isinstance(dates, pd.DatetimeIndex) or dates.hasnans or not dates.is_unique or not dates.is_monotonic_increasing):
        raise ValueError("Dates must be valid, unique and chronological.")

    if not ((dates[1:] - dates[:-1]) == pd.Timedelta(weeks=1)).all():
        raise ValueError("Reservoir data must have weekly intervals without gaps.")

    # 52 weeks approximates a year
    result = STL(series, period=52, seasonal=seasonal, trend=trend, robust=robust).fit()

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.06)
    components = [("Observed", series, "#8FD3C1"),
                  ("Trend", result.trend, "#5FA8D3"),
                  ("Seasonal", result.seasonal, "#E4C1F9"),
                  ("Residual", result.resid, "#E07A5F")]

    for row, (name, component, colour) in enumerate(components, start=1):
        unit = "%" if row <= 2 else " pp"
        fig.add_trace(go.Scatter(x=dates, y=component * 100, mode="lines", name=name, line=dict(color=colour, width=1.5),
                                 hovertemplate=f"%{{y:.2f}}{unit}<extra></extra>"), row=row, col=1)
        fig.update_yaxes(title_text=name, ticksuffix=unit, row=row, col=1)
        
    fig.update_layout(title="STL decomposition of reservoir filling degree", height=750, showlegend=False, hovermode="x unified")
    fig.update_xaxes(hoverformat="%d %b %Y")
    fig.update_xaxes(title_text="Date", row=4, col=1)

    return fig


def reservoir_spectrogram(series, window_length=104, overlap=52):
    """Plot a spectrogram of weekly reservoir filling degree."""

    dates = series.index
    values = series.to_numpy(dtype=float)

    if (not isinstance(dates, pd.DatetimeIndex) or dates.hasnans or not dates.is_unique or not dates.is_monotonic_increasing or not ((dates[1:] - dates[:-1]) == pd.Timedelta(weeks=1)).all()):
        raise ValueError("Reservoir data must have uninterrupted weekly dates.")

    if not np.isfinite(values).all():
        raise ValueError("Reservoir filling degree must contain finite values.")

    # The Hann window used by specgram has zero weights at both ends. Four is the smallest window with two interior values. Windows shorter than a year are allowed, but cannot resolve the annual cycle
    if not isinstance(window_length, (int, np.integer)) or window_length < 4:
        raise ValueError("Window length must be a whole number of at least 4 weeks.")

    if window_length > len(values):
        raise ValueError(f"The selected period has {len(values)} weekly observations, but the window length is {window_length}. Choose a shorter window or a longer period.")

    # Each new window moves forward by window_length - overlap weeks
    if not isinstance(overlap, (int, np.integer)) or not 0 <= overlap < window_length:
        raise ValueError(f"Overlap must be a whole number between 0 and {window_length - 1} weeks.")

    # Calculate the spectrogram
    frequencies, times, power = spectrogram(values, fs=52, window=np.hanning(window_length), nperseg=window_length, 
                                            noverlap=overlap, detrend="constant", scaling="density")

    # Convert spectral power to decibels
    power_db = np.full_like(power, np.nan)
    np.log10(power, out=power_db, where=power > 0)
    power_db *= 10

    # Convert window centres to calendar dates
    window_dates = dates[0] + pd.to_timedelta(times * 52 * 7, unit="D")

    fig = go.Figure(go.Heatmap(x=window_dates, y=frequencies, z=power_db, colorscale="Viridis", colorbar=dict(title="Power (dB)"),
                               hovertemplate=("Date: %{x|%d %b %Y}<br>Frequency: %{y:.2f} cycles/year<br>Power: %{z:.2f} dB<extra></extra>")))
    fig.update_layout(title="Spectrogram of reservoir filling degree", xaxis_title="Date", yaxis_title="Frequency (cycles per year)", height=500)

    # Small windows have coarser frequency bins
    if window_length >= 52:
        fig.update_yaxes(range=[0, 5])

    return fig
