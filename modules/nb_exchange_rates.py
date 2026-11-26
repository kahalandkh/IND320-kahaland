from io import StringIO

import pandas as pd
import requests
import streamlit as st


@st.cache_data(ttl="24h")
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

    # Read the semicolon-separated CSV response directly into memory and preserve the API metadata
    df = pd.read_csv(StringIO(response.text), sep=";")

    if df.empty:
        raise ValueError("No exchange rates found for the selected period.")

    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])

    return df


def load_weekly_exchange_rates(start_date, end_date, currencies=("EUR", "USD")):
    """Return weekly average exchange rates against NOK, indexed by Sunday."""

    if isinstance(currencies, str):
        currencies = (currencies,)

    currencies = tuple(currency.upper() for currency in currencies)

    # Reuse the existing Norges Bank API function
    rates = get_nb_exchange_rates(start_date, end_date, currencies=currencies, frequency="B")

    rates = rates[["TIME_PERIOD", "BASE_CUR", "OBS_VALUE"]].copy()
    rates["OBS_VALUE"] = pd.to_numeric(rates["OBS_VALUE"], errors="raise")

    # One column per currency
    daily = rates.pivot_table(index="TIME_PERIOD", columns="BASE_CUR", values="OBS_VALUE").sort_index()

    # Average available business-day rates within each Monday-Sunday week
    weekly = daily.resample("W-SUN").mean()

    missing = set(currencies) - set(weekly.columns)
    if missing:
        raise ValueError(f"Missing exchange rates: {sorted(missing)}")

    weekly = weekly[list(currencies)]
    weekly = weekly.rename(columns={currency: f"{currency.lower()}_nok" for currency in currencies})
    weekly.index.name = "date_id"

    return weekly
