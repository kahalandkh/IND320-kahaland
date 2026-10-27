import certifi
import streamlit as st
from pymongo import MongoClient


# Reuse the MongoDB connection between Streamlit reruns
@st.cache_resource
def get_cross_border_collection():
    """Connect to MongoDB and return the ENTSO-E cross-border data."""
    client = MongoClient(st.secrets["MONGODB_URI"], tlsCAFile=certifi.where())
    return client["ind320_project"]["cross_border_flows"]