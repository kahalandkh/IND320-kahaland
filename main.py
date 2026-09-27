import streamlit as st

def main():
    """Render the home page."""
    st.title("Reservoir Data")

    st.write("This application was developed as part of the IND320 project work and provides an interactive view of the reservoir dataset.")


# Configure the application layout and browser tab
st.set_page_config(page_title="Reservoir Data", layout="wide")

# Register the four pages and define their sidebar labels
pages = [st.Page(main, title="Home", icon="🏠", default=True),
         st.Page("pages/2_Data_Table.py", title="Data Table", icon="📋"),
         st.Page("pages/3_Data_Plot.py", title="Data Plot", icon="📈"),
         st.Page("pages/4_Additional_Analysis.py", title="Additional Analysis", icon="🔎")]

page = st.navigation(pages)
page.run()