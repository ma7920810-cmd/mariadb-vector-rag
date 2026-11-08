"""Generate grounded answers using a local Ollama model."""

import os
import re
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def generate_answer(question, passages):

    # search() may return (passages, elapsed_time).
    if isinstance(passages, tuple):
        passages, _ = passages

    if not passages:
        return "I couldn't find relevant passages to answer this question."

    passages = passages[:5]

    context = "\n\n".join(
        f"[Source {i}]\n"
        f"Title: {item['title']}\n"
        f"URL: {item['wiki_url']}\n"
        f"Passage: {item['content'][:1800]}"
        for i, item in enumerate(passages, 1)
    )

    prompt = f"""You are a factual question-answering assistant.

Answer the question using ONLY the supplied source passages.

STRICT INSTRUCTIONS:
1. Answer the exact question directly.
2. Write 2-3 short paragraphs, approximately 80-110 words total.
3. Include only information relevant to the question.
4. Do not introduce facts from your own knowledge.
5. Explain processes only when the sources describe them.
6. Every paragraph containing factual information MUST include citations.
7. Use citations in the format [Source 1] or [Source 2].
8. Cite only passages that support the statements.
9. Never repeat the same information.
10. Do not include historical background unless explicitly requested.
11. Finish with a complete sentence.

If the sources do not contain enough information, clearly state what is missing.

QUESTION:
{question}

SOURCE PASSAGES:
{context}

Write the answer now:
"""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 350,
                    "repeat_penalty": 1.15,
                    "repeat_last_n": 64,
                },
            },
            timeout=180,
        )

        response.raise_for_status()
        answer = response.json()["response"].strip()

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "Ollama took too long to generate an answer."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Could not connect to Ollama. Make sure Ollama is running."
        ) from exc

    except (requests.exceptions.RequestException, KeyError, ValueError) as exc:
        raise RuntimeError(f"Answer generation failed: {exc}") from exc

    valid_sources = set(range(1, len(passages) + 1))

    def validate_citation(match):
        source_number = int(match.group(1))
        return match.group(0) if source_number in valid_sources else ""

    answer = re.sub(r"\[Source (\d+)\]", validate_citation, answer)

    return answer
