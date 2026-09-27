import pandas as pd
import streamlit as st


@st.cache_data
def load_data():
    """Load, rename and cache the reservoir dataset."""
    df = pd.read_csv("data/reservoirs.csv", parse_dates=["dato_Id"])

    # Rename the original column headers to match the notebook
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

    return df