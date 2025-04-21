"""
Natural Language Processing utilities for the Entity Views app.
"""
import streamlit as st
import spacy
from .config import SPACY_MODEL, ENTITY_TYPES_TO_KEEP

@st.cache_resource
def load_spacy_model(model_name=SPACY_MODEL):
    """Loads and caches the Spacy model."""
    try:
        return spacy.load(model_name)
    except OSError:
        st.error(
            f"Spacy model '{model_name}' not found. "
            f"Please run: python -m spacy download {model_name}"
        )
        st.stop()

@st.cache_data(show_spinner=False)  # Called within the main loop spinner
def extract_entities(_nlp, text):
    """Extracts named entities from text using Spacy."""
    if not text:  # Handle empty input
        return []
    doc = _nlp(text)
    entities = set()  # Use a set for uniqueness
    for ent in doc.ents:
        if ent.label_ in ENTITY_TYPES_TO_KEEP:
            # Basic cleaning: strip leading/trailing whitespace
            cleaned_entity = ent.text.strip()
            if cleaned_entity:
                entities.add(cleaned_entity)
    return list(entities)