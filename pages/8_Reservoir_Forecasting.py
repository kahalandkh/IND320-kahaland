import pandas as pd
import streamlit as st

from modules.entsoe_mongodb import load_weekly_cross_border
from modules.forecasting import forecast_reservoir, evaluate_forecast, plot_reservoir_forecast
from modules.magasinstatistikk_data import load_magasinstatistikk_data
from modules.nb_exchange_rates import load_weekly_exchange_rates
from modules.weather import load_weekly_weather_with_progress

@st.cache_data(ttl="24h", max_entries=32)
def run_forecast(data, params, training_weeks, horizon, cutoff, use_calendar, columns, exog_lag):
    return forecast_reservoir(data, params=params, training_weeks=training_weeks, horizon=horizon, cutoff=cutoff, columns=columns, exog_lag=exog_lag, use_calendar=use_calendar)


def update_forecast_cutoff():
    st.session_state["reference_week"] = st.session_state["forecast_reference_week"]

st.title("Reservoir Forecasting")
st.write("Forecast weekly reservoir filling using River's SNARIMAX model.")

# Use the region selected in the global sidebar
selected_area_type = st.session_state["selected_area_type"]
selected_area_number = st.session_state["selected_area_number"]
region = f"{selected_area_type}{selected_area_number}"

st.caption(f"Selected region: **{region}** · Change in the sidebar")

df = load_magasinstatistikk_data()

reservoir = df.loc[(df["area_type"] == selected_area_type) & (df["area_number"] == selected_area_number),
                   ["date_id", "reservoir_fill_ratio"]].dropna(subset=["date_id"]).set_index("date_id").sort_index()

if reservoir.empty:
    st.info("No reservoir observations are available for this region.")
    st.stop()

if not reservoir.index.is_unique:
    st.warning("The reservoir data contain duplicate dates.")
    st.stop()

# Synchronise the forecast cutoff with the Home map
observation_dates = sorted(df["date_id"].dropna().dt.date.unique(), reverse=True)
st.session_state["forecast_reference_week"] = st.session_state["reference_week"]

cutoff = st.selectbox("Forecast cutoff", observation_dates, format_func=lambda date: date.strftime("%d %b %Y"),
                      key="forecast_reference_week", on_change=update_forecast_cutoff,
                      help="Last reservoir observation used for training. Shared with the reference week on the Home page.")

cutoff = pd.Timestamp(cutoff)

c1, c2 = st.columns(2)

with c1:
    training_weeks = st.number_input("Training length (weeks)", min_value=4, value=780, step=1,
                                     key="forecast_training_weeks", persist_state="session")
with c2:
    horizon = st.number_input("Forecast horizon (weeks)", min_value=1, max_value=52, value=4, step=1,
                               key="forecast_horizon", persist_state="session")

train_start = cutoff - pd.Timedelta(weeks=training_weeks - 1)
forecast_end = cutoff + pd.Timedelta(weeks=horizon)

st.caption(f"Training period: {train_start:%d %b %Y} – {cutoff:%d %b %Y}")
st.caption(f"Forecast period: {cutoff + pd.Timedelta(weeks=1):%d %b %Y} – {forecast_end:%d %b %Y}")

# Default parameters selected in the Part 4 forecasting experiments
with st.expander("SNARIMAX model parameters"):
    defaults = [("p", "AR order", 0, 0, 12), ("d", "Differencing order", 1, 0, 2),
                ("q", "MA order", 0, 0, 12), ("sp", "Seasonal AR order", 1, 0, 12),
                ("sd", "Seasonal differencing", 1, 0, 2), ("sq", "Seasonal MA order", 1, 0, 12),
                ("m", "Seasonal period", 52, 1, 104)]

    parameter_columns = st.columns(3)
    params = {}

    for i, (name, label, default, minimum, maximum) in enumerate(defaults):
        with parameter_columns[i % 3]:
            params[name] = st.number_input(f"{label} ({name})", min_value=minimum, max_value=maximum,
                                          value=default, step=1, key=f"forecast_{name}", persist_state="session")

use_calendar = st.checkbox("Include annual calendar features", value=True, key="forecast_calendar", persist_state="session",
                           help="Represent the annual cycle using sine and cosine features.")

EXTERNAL_VARIABLES = {"eur_nok": "EUR/NOK", "usd_nok": "USD/NOK",
                      "temperature_mean_c": "Mean weekly temperature", "precipitation_total_mm": "Total weekly precipitation",
                      "imports_mwh": "Weekly electricity imports", "exports_mwh": "Weekly electricity exports", "net_imports_mwh": "Weekly net electricity imports"}

columns = st.multiselect("External variables", options=list(EXTERNAL_VARIABLES), format_func=lambda name: EXTERNAL_VARIABLES[name],
                         key="forecast_external_variables", persist_state="session")

currency_columns = [col for col in columns if col in ["eur_nok", "usd_nok"]]
weather_columns = [col for col in columns if col in ["temperature_mean_c", "precipitation_total_mm"]]
electricity_columns = [col for col in columns if col in ["imports_mwh", "exports_mwh", "net_imports_mwh"]]

exog_lag = None

if columns:
    extra_lag = st.number_input("Additional external-variable lag (weeks)", min_value=0, max_value=52, value=0, step=1, key="forecast_extra_lag", persist_state="session",
                                help="Additional lag beyond the forecast horizon. The same total lag is applied to all selected external variables.")

    exog_lag = horizon + extra_lag

    external_start = train_start - pd.Timedelta(weeks=exog_lag)
    external_end = forecast_end - pd.Timedelta(weeks=exog_lag)
    
    st.caption(f"External-variable lag: {exog_lag} weeks")
    st.caption(f"Required external data: {external_start:%d %b %Y} – {external_end:%d %b %Y}")
    
    if weather_columns:
        st.caption("Regional weather estimates are based on 100 sampled locations.")
        if extra_lag == 0:
            st.info("Consider adding one extra week of lag to account for the ERA5 publication delay.")
        if training_weeks + horizon > 52:
            st.warning("Large weather requests may take longer or reach Open-Meteo's API limits.")
    
    if electricity_columns:
        electricity_start = pd.Timestamp("2024-01-07")
        electricity_end = pd.Timestamp("2025-12-28")

        st.caption("International electricity transfer data are available for EL1–EL4 for weeks ending 7 Jan 2024 to 28 Dec 2025.")

        if region not in ["EL1", "EL2", "EL3", "EL4"]:
            st.warning("Electricity transfer data are not available for the selected region.")
            st.stop()

        if external_start < electricity_start or external_end > electricity_end:
            st.warning("The required external-data period exceeds the available electricity data. Adjust the cutoff, training length or lag.")
            st.stop()

# Check the requested training period
if training_weeks > len(reservoir.loc[:cutoff]):
    st.warning("Not enough reservoir observations for the selected training length. Choose a shorter period or a later cutoff.")
    st.stop()

train_dates = pd.date_range(end=cutoff, periods=training_weeks, freq="W-SUN")
training_data = reservoir.reindex(train_dates)
if training_data["reservoir_fill_ratio"].isna().any():
    st.warning("The selected training period contains missing reservoir observations. Choose a different cutoff or training length.")
    st.stop()

# Associate each forecast with the settings used to generate it
settings = (region, cutoff, training_weeks, horizon, tuple(params.items()), use_calendar, tuple(columns), exog_lag)

if st.button("Run forecast", key="run_reservoir_forecast"):
    st.session_state.pop("forecast_run", None)

    try:
        model_data = training_data.copy()

        if columns:
            # Retain the weeks required for lagged external inputs
            model_dates = pd.date_range(external_start, cutoff, freq="W-SUN")
            model_data = reservoir.reindex(model_dates)

        # Check weather availability before requesting external data
        if weather_columns:
            latest_weather_date = pd.Timestamp.now(tz="Europe/Oslo").date() - pd.Timedelta(days=7)

            if external_end.date() > latest_weather_date:
                raise ValueError("The required weather data may not be available yet. Increase the additional lag or select an earlier cutoff.")

        # Load currency exchange rates
        if currency_columns:
            with st.spinner("Loading weekly exchange rates..."):
                currencies = tuple(col.split("_")[0].upper() for col in currency_columns)

                rates = load_weekly_exchange_rates(
                    start_date=(external_start - pd.Timedelta(days=6)).date(),
                    end_date=external_end.date(), currencies=currencies)

                model_data = model_data.join(rates[currency_columns])

        # Load regional weather
        if weather_columns:
            weather = load_weekly_weather_with_progress(region, external_start, external_end, n_points=100)
            model_data = model_data.join(weather[weather_columns])
        
        # Load international electricity transfers
        if electricity_columns:
            with st.spinner("Loading weekly electricity transfers..."):
                electricity = load_weekly_cross_border(
                    norway_area=f"BZN|NO{selected_area_number}",
                    first_sunday=external_start.strftime("%Y-%m-%d"),
                    last_sunday=external_end.strftime("%Y-%m-%d"))
                model_data = model_data.join(electricity[electricity_columns])

        with st.spinner("Training the model and forecasting reservoir filling..."):
            forecast = run_forecast(model_data, params, training_weeks, horizon, cutoff,
                                    use_calendar, columns, exog_lag)

        st.session_state["forecast_run"] = (settings, forecast)

    except Exception as exc:
        st.error(f"Forecast could not run: {exc}")
        st.stop()

saved_forecast = st.session_state.get("forecast_run")
if saved_forecast is None or saved_forecast[0] != settings:
    st.info("Click 'Run forecast' to forecast reservoir filling using the selected settings.")
    st.stop()
forecast = saved_forecast[1]

# Actual observations are used for evaluation only, not training
actual = reservoir["reservoir_fill_ratio"].reindex(forecast.index)

fig = plot_reservoir_forecast(training_data["reservoir_fill_ratio"], forecast, actual)
st.plotly_chart(fig, width="stretch")

st.caption("The plot shows up to 52 weeks of training observations and the selected forecast horizon.")

if not forecast["forecast_fill_ratio"].between(0, 1).all():
    st.warning("Some predictions are outside the physical filling range of 0–100%. Consider adjusting the model settings.")

# Evaluate historical forecasts where actual observations are available
available = actual.notna()

if available.any():
    metrics = evaluate_forecast(actual[available], forecast.loc[available, "forecast_fill_ratio"])
    st.caption(f"Evaluation based on {available.sum()} of {horizon} forecast weeks.")
    c1, c2 = st.columns(2)
    c1.metric("MAE", f"{metrics['MAE (pp)']:.2f} pp")
    c2.metric("RMSE", f"{metrics['RMSE (pp)']:.2f} pp")

with st.expander("Forecast results"):
    display_results = pd.DataFrame({"Forecast filling (%)": forecast["forecast_fill_ratio"] * 100, "Observed filling (%)": actual * 100})
    st.dataframe(display_results.round(2), width="stretch")
    
with st.expander("Data sources"):
    st.markdown("- [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/): Weekly reservoir filling.\n"
                "- [Norges Bank API](https://www.norges-bank.no/tema/statistikk/apne-data/): Weekly mean EUR/NOK and USD/NOK exchange rates.\n"
                "- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api): ERA5 temperature and precipitation data.\n"
                "- [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/): International electricity transfers for 2024–2025, stored in MongoDB.")
