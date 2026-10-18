# IND320-kahaland

Project work for the IND320 course at NMBU.

This repository contains the Streamlit application developed for the course project together with the documentation in Jupyter Notebooks.

## Part 1

Part 1 explores the reservoir dataset and includes:
- data inspection and visualisation in Jupyter
- a multipage Streamlit application
- a data table with first-month trends
- an interactive Plotly view of the reservoir data

## Part 2

Part 2 extends the project with:
- reservoir data retrieved directly from the NVE Magasinstatistikk API
- a separate reservoir fill ratio page
- ENTSO-E cross-border electricity flow data for 2024 and 2025
- Cassandra and Spark for storing and processing the ENTSO-E data
- MongoDB for the data used by the cross-border Streamlit page

## Streamlit app

[IND320 Energy Project](https://ind320-kahaland-vqqy43wgawwsxmytoyb9ah.streamlit.app)

## Run locally

```bash
uv sync
uv run streamlit run main.py
```