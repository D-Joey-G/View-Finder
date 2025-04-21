"""
Text processing utilities for the Entity Views app.
"""
import unicodedata
from string import capwords

def normalize_text(txt: str) -> str:
    """Lower-case text and strip accents for loose equality comparisons."""
    if not txt:
        return ""
    # Strip accents, convert to ASCII, lowercase, and strip surrounding whitespace
    return (
        unicodedata.normalize("NFKD", txt)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )

def in_list_case_insensitive(item, item_list):
    """Case- and accent-insensitive membership test."""
    norm_item = normalize_text(item)
    return any(normalize_text(x) == norm_item for x in item_list)

def to_title_case(text):
    """Convert text to title case, handling common exceptions."""
    if not text:
        return text
    text = capwords(text)
    # Lowercase common articles, prepositions, conjunctions (except first word)
    special_words = {
        "Of",
        "And",
        "The",
        "In",
        "On",
        "At",
        "To",
        "For",
        "With",
        "By",
    }
    words = text.split()
    for i in range(1, len(words)):
        if words[i] in special_words:
            words[i] = words[i].lower()
    return " ".join(words)