import streamlit as st
from src.search import search
from src.generation import generate_answer

st.set_page_config(
    page_title="MariaDB Vector Search & RAG",
    page_icon="🔎",
    layout="wide",
)

st.title("MariaDB Vector Search & RAG")
st.caption("Area 4 — MariaDB 11.8 + local Ollama LLM")
st.write("Ask a question. MariaDB retrieves relevant Wikipedia passages, and Ollama generates an answer grounded in those sources.")

with st.form("search_form"):
    question = st.text_input(
        "Your question",
        placeholder="How do computers learn from data?",
    )
    category = st.text_input(
        "Optional category filter",
        placeholder="Leave empty for all categories",
    )
    top_k = st.slider("Number of passages", 1, 10, 5)
    submitted = st.form_submit_button("Ask")

if submitted:
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        try:
            with st.spinner("Searching MariaDB..."):
                results, elapsed = search(
                    question.strip(),
                    top_k,
                    category.strip() or None,
                )

            st.caption(f"Retrieved {len(results)} passages in {elapsed:.1f} ms.")

            if not results:
                st.warning("No passages found. Check your indexed articles.")
            else:
                with st.spinner("Generating answer with Ollama..."):
                    answer = generate_answer(question.strip(), results)

                st.subheader("Answer")
                st.markdown(answer)

                st.subheader("Sources")
                for i, item in enumerate(results, 1):
                    with st.expander(
                        f"{i}. {item['title']} "
                        f"(similarity {item['score']:.3f})"
                    ):
                        st.write(item["content"])
                        st.markdown(f"[Open Wikipedia source]({item['wiki_url']})")

        except Exception as exc:
            st.error(f"Error: {exc}")
            st.info("Check that MariaDB and Ollama are running.")
