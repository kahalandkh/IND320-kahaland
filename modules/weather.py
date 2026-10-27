
import pandas as pd
import openmeteo_requests
import requests_cache
from retry_requests import retry


# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession(".cache", expire_after=-1)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)


def download_weather(region, start_date, end_date, locations, batch_size=100, verbose=False):
    """
    Download hourly ERA5 weather data for a selected region and time interval.

    The sampled locations are downloaded in batches. Returns the requested
    coordinates and their corresponding Open-Meteo API responses.
    """
    region = region.upper().replace(" ", "")

    if batch_size < 1:
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

        responses = openmeteo.weather_api(url, params=params)

        # One response is expected for each requested location
        if len(responses) != len(batch):
            raise ValueError("Unexpected number of API responses")

        all_responses.extend(responses)
        
        if verbose:
            print(f"Downloaded {min(start + batch_size, len(coordinates))}/{len(coordinates)} locations")

    return coordinates, all_responses
