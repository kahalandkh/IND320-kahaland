# IND320-kahaland

Project work for the IND320 course at NMBU.

This repository contains the Streamlit application and Jupyter notebooks developed during the course project.

## Part 1

Part 1 explores the reservoir dataset and includes:
- data inspection and visualisation in Jupyter
- a multipage Streamlit application
- a data table with first-month trends
- interactive Plotly visualisations of reservoir data

## Part 2

Part 2 extends the project with:
- reservoir data retrieved directly from the NVE Magasinstatistikk API
- additional reservoir visualisations
- ENTSO-E cross-border electricity flow data for 2024 and 2025
- Cassandra and Spark for storing and processing the ENTSO-E data
- MongoDB for the data used by the cross-border Streamlit page

## Part 3

Part 3 adds data analysis in Jupyter and Streamlit, including:
- STL decomposition and Spectrogram analysis of weekly reservoir filling degree
- hourly ERA5 weather data downloaded through Open-Meteo
- DCT filtering and SPC for identifying unusual precipitation hours
- Local Outlier Factor (LOF) for detecting temperature anomalies
- updated Streamlit pages with a shared region selector, adjustable parameters and interactive plots

## Streamlit app

[IND320 Energy Project](https://ind320-kahaland-vqqy43wgawwsxmytoyb9ah.streamlit.app)

The app includes reservoir data tables and plots, STL and Spectrogram analysis, weather analysis using SPC and LOF, and cross-border electricity transfer visualisations.

## Run locally

Install the project dependencies and start the app:

```bash
uv sync
uv run streamlit run main.py
```

The app retrieves reservoir data from NVE and weather data from Open-Meteo. The weather page also uses local geographical files for region sampling. Cross-border Transfers requires a configured MongoDB connection.