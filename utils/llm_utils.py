"""
LLM (Claude) utilities for the Entity Views app.
"""
import streamlit as st
import anthropic
import json
import re
from .config import ANTHROPIC_API_KEY

@st.cache_resource
def get_anthropic_client():
    """Initializes and caches the Anthropic client, stopping if key is missing."""
    if not ANTHROPIC_API_KEY:
        st.error(
            "Anthropic API key not found. "
            "Please configure it in Streamlit secrets (secrets.toml)."
        )
        st.stop()
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

@st.cache_data(show_spinner="Structuring Q&A pairs...", hash_funcs={"anthropic.Anthropic": lambda _: None})
def structure_qa_pairs(_client, text_input):
    """Uses Claude to structure unstructured Q&A text into JSON."""
    if not text_input.strip():
        return []

    prompt = f"""
    {anthropic.HUMAN_PROMPT} Here is a block of text containing one or more trivia question-answer pairs. Please parse it and identify each distinct question and its corresponding answer. Structure the output as a JSON list of objects, where each object has a "question" key and an "answer" key. Handle various delimiters (newlines, specific markers like Q:, A:, Answer:, etc.) intelligently.

    Input Text:
    ```
    {text_input}
    ```

    Output the JSON list directly, without any introductory text. Example format:
    [
      {{"question": "Question text 1?", "answer": "Answer 1"}},
      {{"question": "Question text 2?", "answer": "Answer 2"}}
    ]
    {anthropic.AI_PROMPT}
    """
    try:
        response = _client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        # Robust JSON extraction (handles potential leading/trailing text)
        json_match = re.search(r"^\s*(\[.*?\])\s*$", response.content[0].text, re.DOTALL)
        if json_match:
            json_string = json_match.group(1)
            try:
                structured_data = json.loads(json_string)
                # Basic validation
                if (
                    isinstance(structured_data, list)
                    and all(
                        isinstance(item, dict) and "question" in item and "answer" in item
                        for item in structured_data
                    )
                ):
                    return structured_data
                else:
                    st.warning(
                        "LLM response JSON was not a list of {question, answer} objects."
                    )
                    return None  # Or potentially attempt fallback parsing
            except json.JSONDecodeError as e:
                st.error(
                    f"Failed to parse JSON from Claude's response: {e}\n"
                    f"Response: {response.content[0].text}"
                )
                return None
        else:
            st.error(
                "Could not extract JSON list from Claude's response:\n"
                f"{response.content[0].text}"
            )
            return None

    except anthropic.APIError as e:
        st.error(f"Anthropic API error during structuring: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during structuring: {e}")
        return None

@st.cache_data(show_spinner="Identifying main topic...", hash_funcs={"anthropic.Anthropic": lambda _: None})
def identify_main_topic(_client, question, answer):
    """Uses Claude 3.7 Sonnet to identify the primary subject/topic of a Q&A pair."""
    prompt = f"""
    {anthropic.HUMAN_PROMPT} Consider the following trivia question and its answer:
    Question: "{question}"
    Answer: "{answer}"
    Your task is to analyze question-answer pairs and identify the implicit "key entity" that connects them. The key entity is critical knowledge required to answer the question correctly, but is not explicitly stated in the question itself. Respond with ONLY the name of the most specific subject/topic. If the answer itself is the clear topic, just repeat the answer, but think carefully before answering.

    Examples:

    Question: The body of which US President, who died in 1885, lies in Riverside Park in Manhattan, in the largest mausoleum in North America?
    Answer: Ulysses S Grant
    Key Entity: Grant's Tomb

    Question: What name precedes "en-Y" in the surgical procedure often used as part of a gastric bypass?
    Answer: Roux
    Key Entity: Roux-en-Y

    Question: What King was victorious at a battle fought on Saint Crispin's Day in 1415?
    Answer: Henry V
    Key Entity: Battle of Agincourt

    Question: A term from what game titles the 2024 Sally Rooney novel about Ivan and Paul Koubek?
    Answer: Chess
    Key Entity: Intermezzo (novel)

    Question: Who invented the martial art whose name translates as 'the way of the intercepting fist'?
    Answer: Bruce Lee
    Key Entity: Jeet Kune Do

    For the following question-answer pair, identify the implicit key entity:
    Question: {question}
    Answer:{answer}

    {anthropic.AI_PROMPT}
    """
    try:
        response = _client.messages.create(
            model="claude-3-7-sonnet-20250219", # Use advanced model for subtle task of key entity detection
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )
        topic = response.content[0].text.strip()
        # Clean up potential LLM artifacts like surrounding quotes
        topic = topic.strip('"\'')
        return topic if topic else None
    except anthropic.APIError as e:
        st.warning(f"Anthropic API error identifying topic: {e}")
        return None
    except Exception as e:
        st.warning(f"An unexpected error occurred during topic identification: {e}")
        return None

@st.cache_data(show_spinner="Resolving disambiguation...", hash_funcs={"anthropic.Anthropic": lambda _: None})
def resolve_disambiguation(client, entity_name, options, question, answer):
    """Ask Claude to pick the best Wikipedia title from a list of disambiguation options."""
    if not client or not options:
        return None

    prompt = f"""
    {anthropic.HUMAN_PROMPT} We encountered multiple possible Wikipedia pages for the entity \"{entity_name}\".
    Trivia Question: {question}
    Answer: {answer}
    Possible Wikipedia pages:
    {chr(10).join('- ' + o for o in options[:15])} # Limit options sent

    Please choose the single option that best matches the context of the question and answer. If none are clearly relevant, respond with "NONE".
    Respond ONLY with the exact page title (case sensitive) or "NONE".
    {anthropic.AI_PROMPT}
    """

    try:
        resp = client.messages.create(
            model="claude-3-haiku-20240307", # Use Haiku for faster/cheaper resolution
            max_tokens=50, 
            messages=[{"role": "user", "content": prompt}],
        )
        title = resp.content[0].text.strip().strip('"\'')
        # Validate that the returned title was one of the options
        if title and title != "NONE" and title in options:
            return title
        else:
            return None # Claude responded NONE or an invalid title
    except anthropic.APIError as e:
        st.warning(f"Anthropic API error during disambiguation: {e}")
        return None
    except Exception as e:
        st.warning(f"An unexpected error occurred during disambiguation: {e}")
        return None