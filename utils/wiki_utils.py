"""
Wikipedia API and page view utilities for the Entity Views app.
"""
import streamlit as st
import wikipediaapi
import pageviewapi
from datetime import datetime, timedelta

from .config import DEFAULT_VIEWS_DAYS
from .text_utils import to_title_case
from .llm_utils import resolve_disambiguation

@st.cache_resource
def get_wikipedia_api():
    """Initializes and caches the Wikipedia API client."""
    wiki_user_agent = st.secrets.get("wikipedia", {}).get("WIKI_USER_AGENT")
    if not wiki_user_agent:
        st.error("Wikipedia User-Agent not found in secrets.toml. Please check your configuration.")
        raise ValueError("Wikipedia User-Agent not configured in st.secrets")
    return wikipediaapi.Wikipedia(
        language="en",
        user_agent=wiki_user_agent
    )

# Cache Wikipedia data fetch per entity + context
@st.cache_data(show_spinner=False, hash_funcs={"anthropic.Anthropic": lambda _: None})
def get_wikipedia_data(
    _wiki_api,
    entity_name,
    *, # Force keyword arguments for clarity
    question="",
    answer="",
    days=DEFAULT_VIEWS_DAYS,
    client=None,
):
    """Fetch Wikipedia stats, handling disambiguation via Claude."""
    entity_name_title_case = to_title_case(entity_name)
    page_info = {
        "title": entity_name_title_case, # Start with the processed name
        "length": None,
        "views": None,
        "url": None,
        "found": False,
        "error": None,
    }

    def _fetch_page_views(page_title, days_to_fetch):
        """Helper to fetch page views, handling common errors."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_to_fetch)
        try:
            views_data = pageviewapi.per_article(
                "en.wikipedia",
                page_title,
                start=start_date.strftime("%Y%m%d"),
                end=end_date.strftime("%Y%m%d"),
                access="all-access",
                agent="user",
            )
            return sum(item["views"] for item in views_data["items"])
        except pageviewapi.client.ZeroViewsError:
            return 0
        except Exception as pv_err:
            return f"Pageview fetch error: {pv_err}" # Return error string

    def _populate_from_page(page):
        """Populates page_info dictionary from a WikipediaPage object."""
        page_info["found"] = True
        page_info["title"] = page.title # Use canonical title
        page_info["length"] = len(page.text)
        page_info["url"] = page.fullurl
        views_result = _fetch_page_views(page.title, days)
        if isinstance(views_result, int):
            page_info["views"] = views_result
        else:
            page_info["views"] = None
            page_info["error"] = page_info.get("error") or views_result # Append view error if no other error

    try:
        page = _wiki_api.page(entity_name_title_case)
        if page.exists():
            # Check if it's a disambiguation page *after* confirming existence
            # Using category check as getattr might not always work reliably depending on lib version/page structure
            is_disambiguation = any(
                cat.title == "Category:All disambiguation pages"
                for cat in page.categories.values()
            )
            
            if is_disambiguation:
                # Handle disambiguation directly - no exception needed
                # Extract options directly from the page if possible
                options = [link.title for link in page.links.values()]
                if not options: # Fallback if links aren't parsed as expected
                    options = [entity_name_title_case + " (disambiguation)"]
                
                # Try to resolve via Claude
                selected_title = resolve_disambiguation(
                    client, entity_name_title_case, options, question, answer
                )
                
                if selected_title:
                    # Fetch the page Claude selected
                    try:
                        resolved_page = _wiki_api.page(selected_title)
                        if resolved_page.exists():
                            # Ensure the resolved page isn't *also* a disambiguation page (rare case)
                            is_resolved_disambiguation = any(
                                cat.title == "Category:All disambiguation pages"
                                for cat in resolved_page.categories.values()
                            )
                            if not is_resolved_disambiguation:
                                _populate_from_page(resolved_page)
                                return page_info
                    except Exception as resolve_err:
                        # Log error if fetching resolved page fails
                        page_info["error"] = f"Error fetching resolved page '{selected_title}': {resolve_err}"
                        return page_info
                
                # If resolution failed or Claude returned None
                page_info["error"] = (
                    f"Disambiguation: {entity_name_title_case}. "
                    f"Options: {', '.join(options[:5])}..."
                )
                return page_info
            else:
                # Normal page - not disambiguation
                _populate_from_page(page)
                return page_info
        else:
            page_info["error"] = "Page not found on Wikipedia."
            return page_info
            
    except Exception as gen_err:
        # Catch other potential errors (network, etc.)
        st.error(f"Unexpected error fetching Wikipedia data for '{entity_name_title_case}': {gen_err}") # Log unexpected
        page_info["error"] = f"Unexpected error: {gen_err}"
        return page_info