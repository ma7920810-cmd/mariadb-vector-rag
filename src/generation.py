"""Generate grounded answers using a local Ollama model."""
import os
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def generate_answer(question, passages):
    if not passages:
        return "I couldn't find relevant passages to answer this question."

    context = "\n\n".join(
        f"[Source {i}] {item['title']}\n"
        f"URL: {item['wiki_url']}\n"
        f"Passage: {item['content']}"
        for i, item in enumerate(passages, 1)
    )

    prompt = f"""Answer the question using ONLY the source passages below.
Do not invent facts. If the sources lack enough information, say so.
Cite supporting passages using [Source 1], [Source 2], etc.

QUESTION:
{question}

SOURCE PASSAGES:
{context}

ANSWER:
"""

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["response"].strip()
