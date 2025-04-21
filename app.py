"""
Trivia Question Analyzer - A Streamlit app for analyzing trivia questions
and extracting Wikipedia viewership stats for relevant entities.
"""
import streamlit as st
import pandas as pd

# Import utility modules
from utils.config import DEFAULT_VIEWS_DAYS
from utils.text_utils import in_list_case_insensitive, normalize_text
from utils.nlp_utils import load_spacy_model, extract_entities
from utils.wiki_utils import get_wikipedia_api, get_wikipedia_data
from utils.llm_utils import get_anthropic_client, structure_qa_pairs, identify_main_topic

# --- Streamlit App UI ---
st.set_page_config(layout="wide", page_title="Question Analysis")
st.title("🧠 Question-Answer View Finder")
st.markdown(
    "Paste unstructured question-answer pairs below. The app will structure them, "
    "identify key entities, and fetch Wikipedia stats (page length & recent views)."
    "\n\n\nThe app can identify key entities implicit in a question. For example, given the "
    "question 'What country is home to the largest lake in the EU? Sweden', it should "
    "fetch views for Lake Vänern."
    "\n\n\nBy default, the app only fetches views for the answer and the key entity."
)

# --- Resource Loading ---
with st.spinner("Loading resources..."):
    nlp = load_spacy_model()
    wiki_api = get_wikipedia_api()
    client = get_anthropic_client() # Checks for API key via secrets & stops if missing

# --- User Input Area ---
col1, col2 = st.columns([3, 1]) # Ratio for text area and controls
with col1:
    raw_text = st.text_area(
        "Enter Question(s) and Answer(s) Here:",
        height=175,
        placeholder=(
            "Example:\n"
            "Q: The body of which US President, who died in 1885, lies in Riverside Park "
            "in Manhattan, in the largest mausoleum in North America?\n"
            "A: Ulysses S Grant\n\n"
            "What is the capital of France? Paris"
        ),
        label_visibility="collapsed", # Hide label, placeholder is sufficient
    )

with col2:
    include_q_entities_toggle = st.checkbox(
        "Include entities from question text",
        value=False,
        key="include_q_entities",
        help="Check this to also fetch stats for entities found in the question text.",
    )
    analyze_button = st.button("🔍 Analyse Quiz", use_container_width=True)

# --- Analysis Logic ---
if analyze_button and raw_text and client:
    # 1. Structure Q&A pairs
    structured_pairs = structure_qa_pairs(client, raw_text)

    if structured_pairs is None:
        st.error("Failed to structure the input text. Please check the format or try again.")
    elif not structured_pairs:
        st.warning("No valid Q-A pairs were identified in the input.")
    else:
        st.subheader(f"Analysis Results ({len(structured_pairs)} Q-A pairs found):", divider="rainbow")

        # Process each pair
        with st.spinner("Analysing pairs and fetching Wikipedia data..."):
            all_results_data = []
            for i, pair in enumerate(structured_pairs):
                question = pair.get("question", "N/A")
                answer = pair.get("answer", "N/A")

                with st.expander(f"Pair {i+1}: Q: {question[:80]}... A: {answer}", expanded=True):
                    st.markdown(f"**Question:** {question}")
                    st.markdown(f"**Answer:** {answer}")

                    # Determine which entities to check based on toggle
                    include_q_entities = st.session_state.get("include_q_entities", False)

                    # Extract entities from answer (always)
                    answer_entities = extract_entities(nlp, answer)
                    if answer and not in_list_case_insensitive(answer, answer_entities):
                        answer_entities.append(answer) # Ensure literal answer is included

                    # Extract entities from question (optional)
                    question_entities = (
                        extract_entities(nlp, question) if include_q_entities else []
                    )

                    # Identify main topic via LLM
                    main_topic = identify_main_topic(client, question, answer)

                    # Combine entities, ensuring uniqueness via normalization
                    combined_entities = {}
                    for entity_list in [answer_entities, question_entities, [main_topic]]:
                        for entity in entity_list:
                            if entity: # Skip None or empty strings
                                combined_entities[normalize_text(entity)] = entity # Store original form

                    unique_entities_to_fetch = sorted(list(combined_entities.values()), key=str.lower)

                    if not unique_entities_to_fetch:
                        st.write("No relevant entities were identified.")
                        continue

                    st.markdown("**Wikipedia Stats:**")
                    # Fetch data for unique entities
                    entity_data_list = []
                    for entity in unique_entities_to_fetch:
                        wiki_data = get_wikipedia_data(
                            wiki_api, entity, question=question, answer=answer, client=client
                        )
                        entity_data_list.append(wiki_data)

                    # Prepare data for DataFrame display
                    df_data = []
                    for data in entity_data_list:
                        views = data["views"]
                        length = data["length"]
                        status = (
                            "✓ Found"
                            if data["found"]
                            else f"✗ {data['error']}"
                            if data["error"]
                            else "✗ Not Found"
                        )
                        url = data.get("url", "")
                        df_data.append({
                            "Entity": data['title'],
                            "URL": url,  # Store URL separately
                            # Use None for sorting if views/length aren't numbers
                            "Views (365d)": views if isinstance(views, int) else None,
                            "Page Length": length if isinstance(length, int) else None,
                            "Status": status,
                            # Formatted display strings (handle None)
                            "Views Display": f"{views:,}" if isinstance(views, int) else "N/A",
                            "Length Display": f"{length:,}" if isinstance(length, int) else "N/A",
                        })

                    if df_data:
                        df = pd.DataFrame(df_data)
                        column_config = {
                            "Entity": st.column_config.Column(
                                "Entity",
                                help="Wikipedia page title"
                            ),
                            "URL": st.column_config.LinkColumn(
                                "Link",
                                display_text="View on Wikipedia",
                                help="Link to Wikipedia page"
                            ),
                            "Views (365d)": st.column_config.NumberColumn(
                                "Views (365d)",
                                format="%d",
                                help=f"Number of page views in the last {DEFAULT_VIEWS_DAYS} days. Sorting uses raw number.",
                            ),
                            "Page Length": st.column_config.NumberColumn(
                                "Page Length",
                                format="%d",
                                help="Number of characters in the Wikipedia page source. Sorting uses raw number.",
                            ),
                            "Status": st.column_config.TextColumn(
                                "Status",
                                help="Indicates if the page was found and fetched successfully."
                            ),
                            "Views Display": None, # Hide for display, use formatted column
                            "Length Display": None, # Hide for display, use formatted column
                        }
                        # Display DataFrame with specific columns
                        st.dataframe(
                            df[["Entity", "URL", "Views (365d)", "Page Length", "Status"]], # Include URL column
                            use_container_width=True,
                            hide_index=True,
                            column_config=column_config,
                        )
                    else:
                        st.write("No Wikipedia data could be fetched for identified entities.")

elif analyze_button and not raw_text:
    st.warning("Please enter some text to analyze.")