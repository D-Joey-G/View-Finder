"""
Configuration constants and environment variables for the Entity Views app.
"""
import streamlit as st

# --- Configuration & Constants ---
ANTHROPIC_API_KEY = st.secrets.get("anthropic", {}).get("api_key")
SPACY_MODEL = "en_core_web_lg"
DEFAULT_VIEWS_DAYS = 365
ENTITY_TYPES_TO_KEEP = {
    "PERSON",
    "ORG",
    "LOC",
    "GPE",
    "FAC",
    "PRODUCT",
    "EVENT",
    "WORK_OF_ART",
    "NORP",
    "LAW",
}