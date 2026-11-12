# Native Vector Search and RAG with MariaDB

**Constructor University — Database Systems Project, Area 4**

A retrieval-augmented question-answering system built around MariaDB 11.8 native vector search. It retrieves relevant Wikipedia passages using sentence embeddings and MariaDB cosine-distance queries, then uses a locally hosted Ollama language model to generate answers grounded in the retrieved passages.

## Features

- MariaDB 11.8 with native `VECTOR(384)` storage.
- HNSW vector index configured for cosine distance.
- Sentence embeddings using `sentence-transformers/all-MiniLM-L6-v2`.
- Semantic retrieval using `VEC_DISTANCE_COSINE`.
- SQL joins between article metadata and text chunks.
- Category filtering and configurable retrieval count.
- Multiple-chunk-per-article limit to improve source diversity.
- Local answer generation using Ollama and `llama3.2:3b`.
- Streamlit interface displaying answers and expandable source passages.
- Wikipedia article URLs retained for source attribution.
- Curated, categorised Wikipedia corpus (~70 articles) with incremental, idempotent ingestion.
- Section- and sentence-aware chunking sized to the embedding model's 256-token input.

## Architecture

```text
                  User question
                        |
                        v
              Sentence Transformer
                (384-d embedding)
                        |
                        v
                MariaDB 11.8
             Native vector retrieval
             VEC_DISTANCE_COSINE
                        |
                        v
               Ranked text chunks
                        |
                        v
                Context preparation
                        |
                        v
                 Ollama LLM
                  llama3.2:3b
                        |
                        v
                Generated answer
                        |
                        v
                 Streamlit UI
             Answer + source passages
```

## Project Structure

```text
mariadb-vector-rag/
├── app.py
├── src/
│   ├── config.py
│   ├── db.py
│   ├── embeddings.py
│   ├── chunking.py
│   ├── ingest.py
│   ├── wikipedia.py
│   ├── search.py
│   └── generation.py
├── data/
│   └── corpus.json
├── docs/
│   └── DATASET.md
├── sql/
│   ├── 001_schema.sql
│   └── 002_ingestion_metadata.sql
├── tests/
│   ├── fixtures.py
│   ├── test_chunking.py
│   ├── test_ingest.py
│   └── test_wikipedia.py
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Requirements

- Python 3.11 or newer (use a version supported by the installed dependencies).
- Docker and Docker Compose.
- MariaDB 11.8.
- Ollama.
- Git.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/ma7920810-cmd/mariadb-vector-rag.git
cd mariadb-vector-rag
```

### 2. Start MariaDB

```bash
docker compose up -d
```

Wait until the database container is healthy.

### 3. Configure Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your MariaDB connection settings and other configuration values.

### 5. Start Ollama

Install Ollama from https://ollama.com and download the model:

```bash
ollama pull llama3.2:3b
```

Make sure the Ollama service is running.

### 6. Initialize and populate the database
Start MariaDB using Docker Compose. The schema in sql/001_schema.sql is automatically executed when the database volume is initialized for the first time.

docker compose up -d
docker compose ps

Wait until the MariaDB container reports that it is healthy.

If you are using an existing database volume, the initialization scripts will not run again automatically. `python -m src.ingest` detects a database created before `sql/002_ingestion_metadata.sql` existed and applies that (additive) migration itself.

If your `.env` was copied from an older `.env.example`, update `CHUNK_WORDS=160` and `CHUNK_OVERLAP=30` (see [Ingestion](#ingestion)).

Ingest the Wikipedia articles:

```bash
python -m src.ingest
```

## Ingestion

`python -m src.ingest` ingests the curated corpus in `data/corpus.json`. Each key in that file is stored in `articles.category`, so it can be used in the category filter (`databases`, `information-retrieval`, `machine-learning`, `natural-language-processing`, `computer-science`).

```bash
python -m src.ingest --only-category databases                 # one corpus category
python -m src.ingest --titles "Vector database" --category databases
python -m src.ingest --from-category "Information retrieval" --limit 25 \
                     --category information-retrieval          # expand from a Wikipedia category
python -m src.ingest --dry-run --export chunks.jsonl           # inspect chunks; no DB, no embeddings
python -m src.ingest --force                                   # re-embed everything
python -m src.ingest --prune                                   # remove articles no longer in corpus.json
```

How it works:

1. **Resolve** all titles in batches of 50 (`action=query`), following redirects. Missing pages, disambiguation pages and stubs are skipped, and titles that resolve to the same page id are ingested once.
2. **Skip unchanged** articles: the stored `rev_id` and `ingest_signature` (chunker version + chunk settings + embedding model) are compared first, so a re-run only downloads pages that changed on Wikipedia or need re-chunking.
3. **Fetch and clean** the article HTML (`action=parse`). Section headings are kept. References, "See also", infoboxes, navboxes, hatnotes and citation markers are removed, and math is replaced with its TeX alt text.
4. **Chunk** within sections at sentence boundaries (default 160 words, ~30 words of whole-sentence overlap). Each chunk is embedded as `"Title — Section: text"` so short passages keep their context. `chunks.content` stores the plain text.
5. **Deduplicate**: repeated chunks inside an article and chunks whose text already exists under another article are dropped (`chunks.content_hash`).
6. **Write** the article upsert and the chunk replacement in one transaction (keyed on the unique `wiki_page_id`), so a failure never leaves an article half-ingested. One failing page does not stop the run, and the run ends with a summary.

Requests to Wikipedia follow the API etiquette: a User-Agent with contact details (`WIKI_CONTACT`), serial requests, `maxlag=5`, and back-off with `Retry-After` on HTTP 429/5xx. See `docs/DATASET.md` for the dataset options that were considered.

### 7. Launch the application

```bash
streamlit run app.py
```

Open the local Streamlit URL shown in the terminal.

## Testing

Run the available unit tests:

```bash
python -m unittest discover -s tests -v
```

Check Python syntax:

```bash
python -m compileall -q app.py src tests
```

## Current Corpus

`data/corpus.json` lists about 70 English Wikipedia articles in five categories chosen to match the project topic: databases (including MariaDB, indexing and transactions), information retrieval and vector search (BM25, nearest-neighbour search, HNSW, RAG), machine learning, natural language processing and embeddings, and computer-science fundamentals. The original ten articles are all included. To grow the corpus, add titles to the file and re-run `python -m src.ingest`.

## Current Limitations and Future Work

- Citation validation checks source-number references, not the factual support of every claim.
- Retrieval quality needs systematic evaluation against a prepared question set.
- HNSW index usage and query performance should be verified with query plans and benchmarks.
- Hybrid lexical and vector retrieval can be explored.
- GPU acceleration and embedding optimization are future improvements.
- Article quality classes (WikiProject assessments) could be stored and used to weight retrieval.

## Team Contributions

The project is divided into four areas:

- Database and infrastructure.
- Corpus collection and ingestion.
- Embeddings and semantic retrieval.
- Application, answer generation, and evaluation.

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.


