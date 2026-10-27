import pandas as pd
import requests
import streamlit as st


@st.cache_data
def load_magasinstatistikk_data():
    """Retrieve, prepare and cache the NVE Magasinstatistikk reservoir dataset."""
    url = ("https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData")
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    df = pd.DataFrame(response.json())

    # Rename the original column headers to English names
    df = df.rename(columns={
        "dato_Id": "date_id",
        "omrType": "area_type",
        "omrnr": "area_number",
        "iso_aar": "iso_year",
        "iso_uke": "iso_week",
        "fyllingsgrad": "reservoir_fill_ratio",
        "kapasitet_TWh": "reservoir_capacity_twh",
        "fylling_TWh": "stored_energy_twh",
        "neste_Publiseringsdato": "next_publication_date",
        "fyllingsgrad_forrige_uke": "previous_week_reservoir_fill_ratio",
        "endring_fyllingsgrad": "reservoir_fill_ratio_change"
    })

    df["date_id"] = pd.to_datetime(df["date_id"])

    return df