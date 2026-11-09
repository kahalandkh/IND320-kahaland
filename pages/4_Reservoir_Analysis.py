import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from modules.analysis import reservoir_stl, reservoir_spectrogram
from modules.magasinstatistikk_data import load_magasinstatistikk_data


st.title("Reservoir Analysis")
st.write("Explore seasonal patterns in weekly reservoir filling degree using STL and Spectrogram.")

# Use the region selected in the global sidebar
df = load_magasinstatistikk_data()
selected_area_type = st.session_state["selected_area_type"]
selected_area_number = st.session_state["selected_area_number"]
region = f"{selected_area_type}{selected_area_number}"
st.caption(f"Selected region: **{region}** · Change in the sidebar")

# Prepare the same weekly filling degree series used in the notebook
selected_data = df.loc[(df["area_type"] == selected_area_type) & (df["area_number"] == selected_area_number),
                       ["date_id", "reservoir_fill_ratio"]].dropna(subset=["date_id"]).sort_values("date_id")

if selected_data.empty:
    st.info("No reservoir observations are available for this region.")
    st.stop()

# Use the full available history by default; remember later changes to the range
months = sorted(selected_data["date_id"].dt.to_period("M").unique())
min_date = months[0].start_time.date()
max_date = months[-1].end_time.date()

if min_date == max_date:
    st.info("Not enough historical data are available for these analyses.")
    st.stop()

saved_range = st.session_state.get("reservoir_analysis_date_range")
if (not isinstance(saved_range, (tuple, list)) or len(saved_range) != 2
    or not (min_date <= saved_range[0] <= saved_range[1] <= max_date)):
    st.session_state["reservoir_analysis_date_range"] = (min_date, max_date)

selected_dates = st.slider("Analysis period", min_value=min_date, max_value=max_date, format="MMM YYYY",
                           key="reservoir_analysis_date_range", persist_state="session")
start_month = pd.Period(selected_dates[0], freq="M")
end_month = pd.Period(selected_dates[1], freq="M")

# Include all weekly observations in the selected calendar months
period_data = selected_data.loc[selected_data["date_id"].dt.to_period("M").between(start_month, end_month)]
series = period_data.set_index("date_id")["reservoir_fill_ratio"]

st.caption(f"{len(series):,} weekly observations for {region} ({start_month.strftime('%b %Y')} – {end_month.strftime('%b %Y')})")

# Both methods require weekly observations without missing values or gaps
has_missing = series.isna().any()
has_gaps = len(series) > 1 and not series.index.to_series().diff().iloc[1:].eq(pd.Timedelta(weeks=1)).all()
has_duplicates = not series.index.is_unique
valid_series = not series.empty and not (has_missing or has_gaps or has_duplicates)

if series.empty:
    st.info("No weekly observations are available for the selected months.")
elif not valid_series:
    st.warning("The selected period contains missing values, duplicate dates or gaps between weekly observations. "
               "Choose another period to run the analyses. The data have not been filled or changed.")

# Remember the active tab when navigating between pages
def save_reservoir_tab():
    st.session_state["reservoir_analysis_last_tab"] = st.session_state["reservoir_analysis_tabs"]


stl_tab, spectrogram_tab = st.tabs(
    ["STL", "Spectrogram"], default=st.session_state.get("reservoir_analysis_last_tab", "STL"),
    key="reservoir_analysis_tabs", on_change=save_reservoir_tab,
)

with stl_tab:
    st.write("Separate the weekly filling degree into trend, seasonal pattern and residuals.")

    if not valid_series:
        st.caption("Select a period with uninterrupted weekly observations to run STL.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            seasonal = st.number_input("Seasonal smoother", min_value=7, value=13, step=2,
                                       key="stl_seasonal", persist_state="session",
                                       help="Controls how the seasonal pattern changes over time. Must be an odd number of at least 7.")
        with c2:
            trend = st.number_input("Trend smoother", min_value=53, value=89, step=2,
                                    key="stl_trend", persist_state="session",
                                    help="Controls the smoothness of the long-term trend. Must be odd and greater than 52 weeks.")
        with c3:
            robust = st.checkbox("Robust fitting", value=True, key="stl_robust", persist_state="session",
                                 help="Reduces the influence of unusually large residuals when fitting STL.")

        if len(series) < 104:
            st.info("STL requires at least 104 consecutive weekly observations (about two years). Choose a longer period.")
        elif seasonal % 2 == 0 or trend % 2 == 0:
            st.warning("The seasonal and trend smoothers must both be odd numbers.")
        else:
            try:
                fig = reservoir_stl(series, seasonal=seasonal, trend=trend, robust=robust)
                st.pyplot(fig, width="stretch")
                plt.close(fig)
                st.caption("The filling degree is shown as a fraction (0–1), as in the original reservoir data.")
            except ValueError as exc:
                st.warning(f"STL analysis could not run: {exc}")

with spectrogram_tab:
    st.write("See how the frequency of reservoir filling patterns changes over time.")

    if not valid_series:
        st.caption("Select a period with uninterrupted weekly observations to create the spectrogram.")
    elif len(series) < 4:
        st.info("The spectrogram needs at least four weekly observations. Choose a longer period.")
    else:
        # Keep the controls valid if the user shortens the period or window
        max_window = len(series)
        if not 4 <= st.session_state.get("spectrogram_window", 104) <= max_window:
            st.session_state["spectrogram_window"] = min(104, max_window)

        c1, c2 = st.columns(2)
        with c1:
            window_length = st.number_input("Window length (weeks)", min_value=4, max_value=max_window,
                                            value=min(104, max_window), step=1, key="spectrogram_window",
                                            persist_state="session",
                                            help="Number of weeks analysed in each segment. Longer windows distinguish frequencies better, but show less detail about when patterns change.")

        if not 0 <= st.session_state.get("spectrogram_overlap", 52) < window_length:
            st.session_state["spectrogram_overlap"] = min(52, window_length - 1)

        with c2:
            overlap = st.number_input("Overlap (weeks)", min_value=0, max_value=window_length - 1,
                                      value=min(52, window_length - 1), step=1, key="spectrogram_overlap",
                                      persist_state="session",
                                      help="Number of weeks shared between neighbouring segments. More overlap gives more time positions, but not better frequency resolution. Must be less than the window length.")
        
        # Short windows have limited frequency resolution
        if window_length < 52:
            st.caption("Windows shorter than one year may not resolve the annual reservoir cycle clearly.")
                
        try:
            fig = reservoir_spectrogram(series, window_length=window_length, overlap=overlap)
            st.pyplot(fig, width="stretch")
            plt.close(fig)
            st.caption("Frequency is measured in cycles per year; around 1 cycle/year represents an annual pattern.")
        except ValueError as exc:
            st.warning(f"Spectrogram could not run: {exc}")

with st.expander("Data source"):
    st.markdown("The reservoir filling degree data come from [**NVE Magasinstatistikk**](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/).")
