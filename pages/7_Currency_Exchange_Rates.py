import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from modules.nb_exchange_rates import get_nb_exchange_rates


st.title("Currency exchange rates")
st.write("Explore historical EUR and USD exchange rates against the Norwegian krone.")

today = pd.Timestamp.now(tz="Europe/Oslo").date()

# Reserve space for the latest exchange rates above the period selector
metrics_container = st.container()

periods = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "5Y": 60, "All": None}

period = st.segmented_control("Period",
                              options=list(periods),
                              default="3M",
                              key="currency_period",
                              persist_state="session") or "3M"

# Request only the selected period, or the full history from 1995
start_date = ("1995-01-01" if periods[period] is None else (pd.Timestamp(today) - pd.DateOffset(months=periods[period])).date())

try:
    with st.spinner("Loading exchange rates..."):
        rates = get_nb_exchange_rates(start_date=start_date, end_date=today, currencies=("EUR", "USD"), frequency="B")

    # Keep the relevant columns and remove invalid observations
    rates = rates[["TIME_PERIOD", "BASE_CUR", "OBS_VALUE"]].copy()
    rates["OBS_VALUE"] = pd.to_numeric(rates["OBS_VALUE"], errors="coerce")
    rates = rates.dropna().sort_values("TIME_PERIOD")

    if rates.empty:
        raise ValueError("No valid exchange rate observations found.")

except (requests.RequestException, ValueError, KeyError) as exc:
    st.error(f"Could not load exchange rates from Norges Bank: {exc}")

else:
    # Show the latest available observation for each currency
    for column, currency in zip(metrics_container.columns(2), ["EUR", "USD"]):
        currency_data = rates.loc[rates["BASE_CUR"] == currency]

        with column:
            with st.container(border=True):
                if currency_data.empty:
                    st.metric(f"{currency}/NOK", "Unavailable")
                else:
                    latest = currency_data.iloc[-1]

                    st.metric(f"{currency}/NOK", f"{latest['OBS_VALUE']:.4f} NOK")
                    st.caption(f"Latest observation: {latest['TIME_PERIOD']:%d %b %Y}")

    rates["Currency"] = rates["BASE_CUR"] + "/NOK"

    fig = px.line(rates, x="TIME_PERIOD", y="OBS_VALUE", color="Currency",
                  color_discrete_map={"EUR/NOK": "#64B5F6", "USD/NOK": "#EF553B"},
                  category_orders={"Currency": ["EUR/NOK", "USD/NOK"]},
                  labels={"TIME_PERIOD": "Date", "OBS_VALUE": "Exchange rate (NOK)"},
                  title="Historical exchange rates")
    fig.update_layout(hovermode="x unified", legend_title_text="")
    st.plotly_chart(fig, width="stretch")
    
    st.caption("Business-day observations. No exchange rates are published on weekends or bank holidays.")


with st.expander("Data source"):
    st.markdown("The exchange rates come from the [**Norges Bank API**](https://www.norges-bank.no/tema/statistikk/apne-data/). "
                "The rates represent the value of one euro or US dollar in Norwegian kroner.\n\n"
                "The **All** option includes available observations from 1995 for USD and from the introduction of the euro in 1999 for EUR.")
