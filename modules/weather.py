import geopandas as gpd
import numpy as np
import openmeteo_requests
from pathlib import Path
import pandas as pd
import requests_cache
from retry_requests import retry
import streamlit as st


@st.cache_data
def sample_weather_locations(region, n_points=1000, seed=26102025):
    """Generate random locations within a selected geographical area.
    Supports electricity areas (EL1–EL5 / NO1–NO5), hydrological areas (VASS1–VASS3) and Norway (NO0 / NO).
    Returns a DataFrame with region, latitude and longitude."""
    region = region.upper().replace(" ", "")

    # Keep region names consistent with the weather download function
    if region == "NO0":
        region = "NO"
    elif region in [f"EL{i}" for i in range(1, 6)]:
        region = f"NO{region[2:]}"
    if not isinstance(n_points, int) or n_points < 1:
        raise ValueError("n_points must be a positive integer")

    # Match weather region names to Magasinstatistikk identifiers
    area_id = region

    if region == "NO":
        area_id = "NO0"
    elif region in [f"NO{i}" for i in range(1, 6)]:
        area_id = f"EL{region[2:]}"

    data_path = Path(__file__).resolve().parents[1] / "data" / "geographical"
    areas = gpd.read_file(data_path / "reservoir_areas.geojson")

    selected = areas.loc[areas["area_id"] == area_id]

    if selected.empty:
        raise ValueError(f"No geographical boundary found for {region}")

    # Sample in the original projected coordinate system
    boundary = selected.geometry.to_crs(epsg=25833)
    points = boundary.sample_points(size=n_points, rng=seed)

    # Convert sampled locations to WGS84 for Open-Meteo
    points = points.explode(ignore_index=True).to_crs(epsg=4326)

    return pd.DataFrame({"region": region, "latitude": points.y.to_numpy(), "longitude": points.x.to_numpy()})


# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession(".cache", expire_after=-1)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)


def download_weather(region, start_date, end_date, locations, batch_size=100, verbose=False):
    """
    Download hourly ERA5 weather data for a selected region and time interval.

    The sampled locations are downloaded in batches. Returns the Open-Meteo API responses.
    """
    region = region.upper().replace(" ", "")
    
    # Match reservoir area identifiers to geographical regions
    if region == "NO0":
        region = "NO"
    elif region in [f"EL{i}" for i in range(1, 6)]:
        region = f"NO{region[2:]}"

    if not isinstance(batch_size, (int, np.integer)) or batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    if pd.Timestamp(start_date) > pd.Timestamp(end_date):
        raise ValueError("start_date must not be after end_date")

    # Select the sampled coordinates for the requested region
    points = locations[locations["region"] == region]

    if points.empty:
        raise ValueError(f"No sampled locations found for {region}")

    # Create a list of (longitude, latitude) pairs
    coordinates = list(zip(points["longitude"], points["latitude"]))

    url = "https://archive-api.open-meteo.com/v1/archive"
    all_responses = []

    # Download the coordinates in batches
    for start in range(0, len(coordinates), batch_size):
        batch = coordinates[start:start + batch_size]
        longitudes, latitudes = zip(*batch)

        # The order of hourly variables is important when processing the responses
        params = {"latitude": list(latitudes),
                  "longitude": list(longitudes),
                  "start_date": start_date,
                  "end_date": end_date,
                  "hourly": ["temperature_2m", "precipitation"],
                  "models": "era5",
                  "timezone": "Europe/Berlin",
                  "timeformat": "unixtime"}

        responses = openmeteo.weather_api(url, params=params, timeout=120)

        # One response is expected for each requested location
        if len(responses) != len(batch):
            raise ValueError("Unexpected number of API responses")

        all_responses.extend(responses)
        
        if verbose:
            print(f"Downloaded {min(start + batch_size, len(coordinates))}/{len(coordinates)} locations")

    return all_responses


def regional_hourly_averages(responses):
    """
    Calculate hourly average temperature and precipitation across locations.

    Missing values are excluded from the averages.
    """
    if not responses:
        raise ValueError("No weather responses provided")

    # Use the first response to create the hourly timestamps
    first_hourly = responses[0].Hourly()
    start = first_hourly.Time()
    end = first_hourly.TimeEnd()
    interval = first_hourly.Interval()

    dates = pd.date_range(start=pd.to_datetime(start, unit="s", utc=True),
                          end=pd.to_datetime(end, unit="s", utc=True),
                          freq=pd.Timedelta(seconds=interval),
                          inclusive="left").tz_convert(responses[0].Timezone().decode())

    n_hours = len(dates)

    # Store sums and counts for temperature (0) and precipitation (1)
    sums = np.zeros((2, n_hours))
    counts = np.zeros((2, n_hours), dtype=int)

    for response in responses:
        hourly = response.Hourly()

        # All locations must have the same hourly timestamps
        if (hourly.Time(), hourly.TimeEnd(), hourly.Interval()) != (start, end, interval):
            raise ValueError("Hourly timestamps do not match across locations")

        for i in range(2):
            values = hourly.Variables(i).ValuesAsNumpy()

            if len(values) != n_hours:
                raise ValueError("Unexpected number of hourly observations")

            valid = np.isfinite(values)

            sums[i, valid] += values[valid]
            counts[i, valid] += 1

    # Divide by the number of valid observations for each hour
    averages = np.divide(sums, counts, out=np.full_like(sums, np.nan), where=counts > 0)

    return pd.DataFrame({"date": dates, "temperature_2m": averages[0], "precipitation": averages[1]})


@st.cache_data(ttl="7d")
def load_regional_hourly_weather(region, start_date, end_date, n_points=100, batch_size=100, seed=26102025):
    """Load and cache regional hourly averages for a selected period."""
    locations = sample_weather_locations(region, n_points=n_points, seed=seed)
    responses = download_weather(region, start_date, end_date, locations, batch_size=batch_size)
    return regional_hourly_averages(responses)


def hourly_weather_to_weekly(hourly):
    """Convert regional hourly weather data into complete Norwegian Monday-Sunday weeks."""
    df = hourly[["date", "temperature_2m", "precipitation"]].copy()
    df["date"] = pd.to_datetime(df["date"])

    if df["date"].dt.tz is None:
        raise ValueError("Weather timestamps must be timezone-aware.")

    df = df.set_index("date").tz_convert("Europe/Oslo").sort_index()

    if df.index.has_duplicates:
        raise ValueError("Duplicate hourly weather timestamps.")

    # Temperature is measured at the given hour
    temperature = df["temperature_2m"].resample("W-MON", closed="left", label="left")

    # Precipitation represents the preceding hour
    precipitation = df["precipitation"].copy()
    precipitation.index = precipitation.index - pd.Timedelta(hours=1)
    precipitation = precipitation.resample("W-MON", closed="left", label="left")

    weekly = pd.DataFrame({"temperature_mean_c": temperature.mean(),
                           "precipitation_total_mm": precipitation.sum(),
                           "temperature_hours": temperature.count(),
                           "precipitation_hours": precipitation.count()})

    # Check complete weeks, accounting for daylight saving time
    expected_hours = ((weekly.index + pd.DateOffset(weeks=1) - weekly.index) / pd.Timedelta(hours=1))

    weekly = weekly.loc[(weekly["temperature_hours"] == expected_hours) & (weekly["precipitation_hours"] == expected_hours),
                        ["temperature_mean_c", "precipitation_total_mm"]]

    # Label each Monday-Sunday week by Sunday, as in the NVE dataset
    weekly.index = pd.DatetimeIndex([pd.Timestamp(monday.date()) + pd.Timedelta(days=6) for monday in weekly.index], name="date_id")

    return weekly


@st.cache_data()
def load_weather_week(region, reference_week, n_points=100):
    """Return mean temperature and total precipitation for a selected week."""
    sunday = pd.Timestamp(reference_week).normalize()

    if sunday.dayofweek != 6:
        raise ValueError("The reference week must be a Sunday.")

    monday = sunday - pd.Timedelta(days=6)

    # Include an extra day before the week to account for UTC offset differences
    start_date = monday - pd.Timedelta(days=1)

    # Include the following Monday to capture Sunday's final precipitation hour
    end_date = sunday + pd.Timedelta(days=1)

    hourly = load_regional_hourly_weather(region, start_date=start_date.strftime("%Y-%m-%d"),
                                          end_date=end_date.strftime("%Y-%m-%d"), n_points=n_points)

    weekly = hourly_weather_to_weekly(hourly)

    if sunday not in weekly.index:
        raise ValueError(f"No complete weather observations for {region} on {sunday:%d %b %Y}.")

    return weekly.loc[sunday]

@st.cache_data()
def load_weekly_weather(region, first_week, last_week, n_points=100):
    """Load regional weather for a range of complete Monday-Sunday weeks."""

    first_week = pd.Timestamp(first_week).normalize()
    last_week = pd.Timestamp(last_week).normalize()

    if (first_week.dayofweek != 6 or last_week.dayofweek != 6
        or first_week > last_week):
        raise ValueError("Select a valid range of Sunday week labels.")

    weeks = pd.date_range(first_week, last_week, freq="W-SUN", name="date_id")
    blocks = []

    # Download weather in blocks of up to 52 weeks
    for i in range(0, len(weeks), 52):
        block = weeks[i:i + 52]

        # Include additional days for timezone and precipitation boundaries
        start = block[0] - pd.Timedelta(days=7)
        end = block[-1] + pd.Timedelta(days=1)

        hourly = load_regional_hourly_weather(region, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), n_points=n_points)

        weekly = hourly_weather_to_weekly(hourly)

        # Retain missing weeks rather than silently removing them
        blocks.append(weekly.reindex(block))

    return pd.concat(blocks)
