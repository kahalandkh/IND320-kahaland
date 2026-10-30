import numpy as np
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry


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