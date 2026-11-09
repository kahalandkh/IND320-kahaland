import streamlit as st

from modules.magasinstatistikk_data import load_magasinstatistikk_data


# Configure the application layout and browser tab
st.set_page_config(page_title="IND320 Energy Project", layout="wide")


def main():
    """Render the home page."""
    st.title("IND320 Energy Project")

    st.write("")
    st.write("This application was developed as part of the IND320 project work and provides an interactive overview of reservoir, historical weather and cross-border electricity transfer data.")

    st.write("")
    st.subheader("What you can explore")

    st.markdown(
        "- **Reservoir Data:** Browse weekly reservoir measurements and trends.\n"
        "- **Reservoir Plots:** Plot reservoir measurements over time and compare regions.\n"
        "- **Reservoir Analysis:** Explore seasonal patterns in reservoir filling degree using STL and Spectrogram.\n"
        "- **Weather Analysis:** Download hourly ERA5 weather data and analyse unusual precipitation (SPC) and temperature (LOF).\n"
        "- **Cross-border Transfers:** Explore annual electricity transfers and monthly flows between Norway and neighbouring bidding zones.")

    st.write("")
    st.subheader("Getting started")

    st.write(
        "Choose a region in the sidebar to explore reservoir and weather data. "
        "Each page has its own date and analysis settings. On the Weather Analysis page, "
        "select a period and click 'Load weather data' before running the analyses.")

    st.caption(
        "Cross-border Transfers uses a separate connection selector "
        "and is not affected by the global region selection.")

# Register the application pages and define their sidebar labels
pages = [st.Page(main, title="Home", icon="🏠", default=True),
         st.Page("pages/2_Reservoir_Data.py", title="Reservoir Data", icon="📋"),
         st.Page("pages/3_Reservoir_Plots.py", title="Reservoir Plots", icon="📈"),
         st.Page("pages/4_Reservoir_Analysis.py", title="Reservoir Analysis", icon="📊"),
         st.Page("pages/5_Weather_Analysis.py", title="Weather Analysis", icon="🌦️"),
         st.Page("pages/6_Cross_Border_Transfers.py", title="Cross-border Transfers", icon="⚡")]

page = st.navigation(pages)


# Get the available reservoir regions
df = load_magasinstatistikk_data()
area_types = sorted(df["area_type"].dropna().unique())

# Default to electricity area EL on a new session
if st.session_state.get("selected_area_type") not in area_types:
    st.session_state["selected_area_type"] = ("EL" if "EL" in area_types else area_types[0])

# Keep the region selector visible across all pages
with st.sidebar:
    st.divider()
    st.subheader("Selected region")

    selected_area_type = st.selectbox("Area type", area_types, key="selected_area_type")

    # Area numbers depend on the selected area type
    area_numbers = sorted(df.loc[df["area_type"] == selected_area_type, "area_number"].dropna().unique())

    # Use EL1 by default, or the first valid area
    if st.session_state.get("selected_area_number") not in area_numbers:
        st.session_state["selected_area_number"] = (1 if selected_area_type == "EL" and 1 in area_numbers else area_numbers[0])

    selected_area_number = st.selectbox("Area number", area_numbers, key="selected_area_number")

    st.caption(f"Current selection: {selected_area_type}{selected_area_number}")
    
    # Explain the area types used in the app
    with st.expander("About the regions"):
        st.markdown("""
        - **EL1–EL5:** Norwegian electricity bidding zones (NO1–NO5).
        - **VASS1–VASS3:** Groups of NVE hydrological regions.
        - **NO0:** Norway as a whole.
        """)

# Run the selected page
page.run()
