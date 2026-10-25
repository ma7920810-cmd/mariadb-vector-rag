"""Small UI for semantic retrieval with transparent Wikipedia sources."""
import streamlit as st
from src.search import search

st.set_page_config(page_title="Wikipedia Vector Search", page_icon="🔎", layout="wide")
st.title("Wikipedia Vector Search")
st.caption("Area 4 — Native vector search and retrieval with MariaDB 11.8")
st.write("Ask a question to retrieve relevant Wikipedia passages. This prototype shows source excerpts rather than generating unsupported answers.")

with st.form("search_form"):
    question = st.text_input("Your question", placeholder="How are databases used in information retrieval?")
    category = st.text_input("Optional category filter", placeholder="Leave empty for all categories")
    top_k = st.slider("Number of passages", min_value=1, max_value=10, value=5)
    submitted = st.form_submit_button("Search")

if submitted:
    if not question.strip():
        st.warning("Enter a question first.")
    else:
        try:
            results, elapsed = search(question.strip(), top_k, category.strip() or None)
            st.caption(f"{len(results)} passages · query and database time: {elapsed:.1f} ms")
            if not results:
                st.info("No chunks found. Run the ingestion command first.")
            for index, item in enumerate(results, 1):
                with st.container(border=True):
                    st.subheader(f"{index}. {item['title']}")
                    st.caption(f"Cosine similarity: {item['score']:.3f} · {item['word_count'] if 'word_count' in item else len(item['content'].split())} words")
                    st.write(item["content"])
                    st.markdown(f"[Open Wikipedia source]({item['wiki_url']})")
        except Exception as exc:
            st.error(f"Search failed: {exc}")
            st.info("Check that MariaDB is running, the schema exists, and the ingestion step completed.")
