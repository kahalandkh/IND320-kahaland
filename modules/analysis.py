import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.fft import dct, idct
from scipy.signal import spectrogram
from scipy.stats import median_abs_deviation
from sklearn.neighbors import LocalOutlierFactor
from statsmodels.tsa.seasonal import STL


WEATHER_PROPERTIES = {"temperature_2m": ("Temperature", "°C"), "precipitation": ("Precipitation", "mm")}
WEEKLY_WEATHER_PROPERTIES = {"temperature_mean_c": ("Mean weekly temperature", "°C"), "precipitation_total_mm": ("Total weekly precipitation", "mm")}

RESERVOIR_CORRELATION_PROPERTIES = {"reservoir_fill_ratio": ("Reservoir filling", "%"), "reservoir_fill_ratio_change": ("Weekly change in filling", "pp")}

def weather_spc(data, property_name="temperature_2m", cutoff_days=30, n_std=3):
    """Find unusual hourly weather observations using DCT high-pass filtering and robust SPC."""

    if property_name not in WEATHER_PROPERTIES:
        raise ValueError("Unsupported weather property.")

    label, unit = WEATHER_PROPERTIES[property_name]

    dates = pd.DatetimeIndex(pd.to_datetime(data["date"]))
    values = data[property_name].to_numpy(dtype=float)

    if len(values) < 3 or dates.hasnans or not np.isfinite(values).all():
        raise ValueError("At least three valid weather observations are required.")

    if property_name == "precipitation" and (values < 0).any():
        raise ValueError("Precipitation cannot be negative.")

    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Dates must be unique and in chronological order.")

    if not ((dates[1:] - dates[:-1]) == pd.Timedelta(hours=1)).all():
        raise ValueError("Weather data must have hourly intervals without gaps.")

    if not np.isfinite(cutoff_days) or cutoff_days < 2 / 24:
        raise ValueError("The cut-off period must be at least 2 hours for hourly data.")

    if not np.isfinite(n_std) or n_std <= 0:
        raise ValueError("n_std must be positive.")

    # DCT-I frequency bins in cycles per hour
    frequencies = np.arange(len(values)) / (2 * (len(values) - 1))
    coefficients = dct(values, type=1, norm="forward")

    # Remove variations with periods longer than cutoff_days
    high_coefficients = coefficients.copy()
    high_coefficients[frequencies < 1 / (24 * cutoff_days)] = 0

    residual = idct(high_coefficients, type=1, norm="forward")
    baseline = values - residual

    # Use median and MAD to reduce the influence of extreme observations
    centre = np.median(residual)
    sigma = median_abs_deviation(residual, scale="normal")

    tolerance = 1e-12 * max(1, np.max(np.abs(values)))
    degenerate = sigma <= tolerance

    if degenerate:
        sigma = 0.0

    # Put the limits back on the original measurement scale
    lower = baseline + centre - n_std * sigma
    upper = baseline + centre + n_std * sigma

    below = values < lower - tolerance
    above = values > upper + tolerance
    outliers = below | above

    result = pd.DataFrame({"date": dates, property_name: values, "baseline": baseline, "residual": residual, "lower": lower,
                           "upper": upper, "outlier": outliers, "side": np.where(above, "upper", np.where(below, "lower", "inlier"))})
    variance = np.var(values)
    summary = {"cutoff_days": cutoff_days, "n_std": n_std, "hours": len(values), "median_residual": centre, "robust_sigma": sigma, "degenerate_mad": degenerate,
               "upper_outliers": int(above.sum()), "lower_outliers": int(below.sum()), "outliers": int(outliers.sum()), "outlier_percent": 100 * outliers.mean(),
        "residual_variance_ratio": np.var(residual) / variance if variance else 0.0, "baseline_variance_ratio": np.var(baseline) / variance if variance else 0.0}

    if property_name == "precipitation":
        summary["negative_baseline_hours"] = int((baseline < -tolerance).sum())

    # Plot the original observations and SPC limits, not the filtered signal
    fig = go.Figure()
    for name, y, colour in [(f"Average {label.lower()}", values, "#8FD3C1"), ("Lower SPC limit", lower, "#F2C14E"), ("Upper SPC limit", upper, "#5FA8D3")]:
        fig.add_trace(go.Scatter(x=dates, y=y, mode="lines", name=name, line=dict(color=colour, width=1.2)))
    fig.add_trace(go.Scatter(x=dates[outliers], y=values[outliers], mode="markers", name="Flagged hour", marker=dict(color="#E07A5F", size=6, symbol="circle-open")))
    fig.update_layout(title=f"Regional {label.lower()}: {cutoff_days:g}-day DCT cut-off, {n_std:g} × SD", xaxis_title="Time", yaxis_title=f"{label} ({unit})",
                      height=500, hovermode="x unified", legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(hoverformat="%d %b %Y, %H:%M")
    fig.update_yaxes(hoverformat=".2f", ticksuffix=f" {unit}")

    return fig, result, summary


def weather_lof(data, property_name="temperature_2m", contamination=0.01, n_neighbors=50, time_scale=0.02):
    """Find unusual hourly weather observations using LOF with scaled time."""

    if property_name not in WEATHER_PROPERTIES:
        raise ValueError("Unsupported weather property.")

    label, unit = WEATHER_PROPERTIES[property_name]

    dates = pd.DatetimeIndex(pd.to_datetime(data["date"]))
    values = data[property_name].to_numpy(dtype=float)

    if len(values) < 3 or dates.hasnans or not np.isfinite(values).all():
        raise ValueError("At least three valid weather observations are required.")

    if property_name == "precipitation" and (values < 0).any():
        raise ValueError("Precipitation cannot be negative.")
    
    if np.ptp(values) == 0:
        raise ValueError("The selected weather property is constant throughout the period.")

    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Dates must be unique and in chronological order.")

    if not ((dates[1:] - dates[:-1]) == pd.Timedelta(hours=1)).all():
        raise ValueError("Weather data must have hourly intervals without gaps.")

    if not np.isfinite(contamination) or not 0 < contamination <= 0.5:
        raise ValueError("contamination must be between 0 and 0.5.")

    if not isinstance(n_neighbors, (int, np.integer)) or not 1 < n_neighbors < len(values):
        raise ValueError("n_neighbors must be between 2 and the number of observations minus 1.")

    if not np.isfinite(time_scale) or time_scale < 0:
        raise ValueError("time_scale must be non-negative.")

    # Weight hourly time differences relative to the selected weather property
    time = np.arange(len(values)) * time_scale
    features = np.column_stack((values, time))

    model = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    anomalies = model.fit_predict(features) == -1

    # Reverse the negative LOF scores for easier reading
    scores = -model.negative_outlier_factor_
    result = pd.DataFrame({"date": dates, property_name: values, "lof_score": scores, "anomaly": anomalies})
    summary = {"hours": len(values), "anomalies": int(anomalies.sum()), "anomaly_percent": 100 * anomalies.mean(),
               "contamination": contamination, "n_neighbors": n_neighbors, "time_scale": time_scale}
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=values, mode="lines", name=f"Average {label.lower()}", line=dict(color="#8FD3C1", width=1.2)))
    fig.add_trace(go.Scatter(x=dates[anomalies], y=values[anomalies], mode="markers", name="LOF anomalies", marker=dict(color="#E07A5F", size=6, symbol="circle-open"),
                             customdata=scores[anomalies], hovertemplate=f"%{{y:.2f}} {unit}<br>LOF score: %{{customdata:.2f}}<extra>LOF anomaly</extra>"))
    fig.update_layout(title=f"Hourly {label.lower()} and LOF anomalies", xaxis_title="Time", yaxis_title=f"{label} ({unit})",
                      height=500, hovermode="x unified", legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(hoverformat="%d %b %Y, %H:%M")
    fig.update_yaxes(hoverformat=".2f", ticksuffix=f" {unit}")

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


def sliding_window_correlation(data, weather_property="temperature_mean_c", reservoir_property="reservoir_fill_ratio", window=13, lag=0):
    """Calculate and plot sliding window correlation between weather and reservoir data."""

    if weather_property not in WEEKLY_WEATHER_PROPERTIES or reservoir_property not in RESERVOIR_CORRELATION_PROPERTIES:
        raise ValueError("Unsupported correlation property.")

    dates = data.index

    if (not isinstance(dates, pd.DatetimeIndex) or dates.hasnans or not dates.is_unique or dates.tz is not None
        or not (dates.dayofweek == 6).all() or not (dates == dates.normalize()).all()):
        raise ValueError("Data must have unique Sunday date labels without a timezone.")

    if not isinstance(window, (int, np.integer)) or window < 4:
        raise ValueError("Window length must be at least four weeks.")

    if not isinstance(lag, (int, np.integer)) or lag < 0:
        raise ValueError("Lag must be a non-negative number of weeks.")

    if data.empty:
        raise ValueError("No weekly observations are available.")

    # Retain missing weeks so that a lag always represents calendar weeks
    data = data.sort_index().asfreq("W-SUN")

    if window + lag > len(data):
        raise ValueError("The selected period is too short for this window and lag.")

    reservoir = data[reservoir_property].replace([np.inf, -np.inf], np.nan)
    weather = data[weather_property].replace([np.inf, -np.inf], np.nan).shift(lag)

    # Calculate centred sliding window correlation
    rolling_reservoir = reservoir.rolling(window, center=True, min_periods=window)
    rolling_weather = weather.rolling(window, center=True, min_periods=window)
    corr = rolling_reservoir.corr(weather)

    # Correlation is undefined when either variable is constant
    corr = corr.where((rolling_reservoir.max() != rolling_reservoir.min()) & (rolling_weather.max() != rolling_weather.min()))
    corr = corr.replace([np.inf, -np.inf], np.nan).clip(-1, 1)

    result = pd.DataFrame({"reservoir": reservoir, "lagged_weather": weather, "correlation": corr})

    if corr.notna().sum() == 0:
        raise ValueError("No complete windows with variation in both variables. Try a shorter window or a different period.")

    reservoir_label, reservoir_unit = RESERVOIR_CORRELATION_PROPERTIES[reservoir_property]
    weather_label, weather_unit = WEEKLY_WEATHER_PROPERTIES[weather_property]

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07)
    components = [(reservoir_label, reservoir * 100, "#8FD3C1", reservoir_unit),
                  (f"{weather_label} (lag {lag} weeks)", weather, "#5FA8D3", weather_unit),
                  ("Pearson correlation", corr, "#E4C1F9", "")]

    axis_labels = ["Filling change" if reservoir_property == "reservoir_fill_ratio_change" else "Reservoir filling",
                   "Temperature" if weather_property == "temperature_mean_c" else "Precipitation", "Correlation"]
    for row, (label, values, colour, unit) in enumerate(components, start=1):
        fig.add_trace(go.Scatter(x=result.index, y=values, name=label, mode="lines+markers" if row == 3 else "lines",
                                line=dict(color=colour, width=1.5), marker=dict(size=3), connectgaps=False,
                                hovertemplate=f"%{{y:.2f}} {unit}<extra>{label}</extra>"), row=row, col=1)
        fig.update_yaxes(title_text=axis_labels[row - 1], ticksuffix=f" {unit}" if unit else "", row=row, col=1)

    fig.add_hline(y=0, line_dash="dot", line_color="gray", row=3, col=1)
    fig.update_yaxes(range=[-1.05, 1.05], row=3, col=1)
    fig.update_layout(title=f"Sliding window correlation: {window} weeks, lag {lag} weeks", height=650, showlegend=False, hovermode="x unified")
    fig.update_xaxes(hoverformat="%d %b %Y")
    fig.update_xaxes(title_text="Week ending", row=3, col=1)

    return fig, result
