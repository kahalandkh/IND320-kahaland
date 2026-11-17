from io import StringIO

import pandas as pd
import requests


def get_nb_exchange_rates(start_date, end_date, currencies=("EUR", "USD"), frequency="B"):
    """Download exchange rates against NOK from the Norges Bank API."""

    # Accept both a single currency ("EUR") and multiple currencies ("EUR", "USD")
    if isinstance(currencies, str):
        currencies = (currencies,)

    # Norges Bank uses '+' to separate currencies in the API URL
    currency_codes = "+".join(currencies)
    url = f"https://data.norges-bank.no/api/data/EXR/{frequency}.{currency_codes}.NOK.SP"

    params = {"startPeriod": str(start_date),
              "endPeriod": str(end_date),
              "format": "csv",
              "locale": "en"}

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    
    # Read the semicolon separated CSV response directly into memory and preserve the API metadata for later analysis
    df = pd.read_csv(StringIO(response.text), sep=";")

    if df.empty:
        raise ValueError("No exchange rates found for the selected period.")

    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])

    return df