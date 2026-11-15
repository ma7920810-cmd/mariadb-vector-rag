A project for area 4, "Vector search and RAG, natively" for the [MariaDB student database projects, 2026-09](https://mariadb.org/bachelor_hackathon_2026-09/).

# Native Vector Search and RAG with MariaDB

**Constructor University — Database Systems Project, Area 4**

A retrieval-augmented question-answering system built around MariaDB 11.8 native vector search. It retrieves relevant Wikipedia passages using sentence embeddings and MariaDB cosine-distance queries, then uses a locally hosted Ollama language model to generate answers grounded in the retrieved passages.

## Features

- MariaDB 11.8 with native `VECTOR(384)` storage.
- HNSW vector index configured for cosine distance.
- Sentence embeddings using `sentence-transformers/all-MiniLM-L6-v2`.
- Semantic retrieval using `VEC_DISTANCE_COSINE`.
- SQL joins between article metadata and text chunks.
- Category, minimum article word count, and ingestion-date filters in the same vector SQL query.
- Multiple-chunk-per-article limit to improve source diversity.
- Local answer generation using Ollama and `llama3.2:3b`.
- Streamlit interface displaying answers and expandable source passages.
- Wikipedia article URLs retained for source attribution.
- Curated, categorised Wikipedia corpus (~70 articles) with incremental, idempotent ingestion.
- Section- and sentence-aware chunking sized to the embedding model's 256-token input.

## Why MariaDB Native Vectors

Article metadata and embeddings live in the same MariaDB database. Retrieval uses one SQL statement to calculate `VEC_DISTANCE_COSINE`, join chunks to article rows, and apply ordinary relational predicates such as category, minimum article word count, and ingestion date. Transactions and the foreign key keep article and chunk writes consistent, with no separate vector service to synchronize. The current project does not store Wikipedia link relationships, so it does not claim link-graph filtering. The date filter uses local `fetched_at` ingestion time, not Wikipedia's last-edited timestamp.

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

### 2. Configure environment and start MariaDB

Copy the example environment file **before** starting Docker and replace both password placeholders with strong, distinct local passwords:

```bash
cp .env.example .env
# Edit .env: set MARIADB_ROOT_PASSWORD and MARIADB_PASSWORD
# Then start the database:
docker compose up -d
docker compose ps
```

Wait until the database container reports healthy. MariaDB binds only to `127.0.0.1` by default, so it is not exposed to other devices on your network. This is a local development setup, not a production deployment. **Do not commit `.env`.**

### 3. Configure Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Check environment configuration

Ensure `.env` contains the same database username, database name and password used by Docker Compose. Do not change these values on an existing populated Docker volume without migrating the corresponding MariaDB accounts; Docker initialization variables are applied only when the data directory is first initialized.

### 5. Start Ollama

Install Ollama from https://ollama.com and download the model:

```bash
ollama pull llama3.2:3b
```

Make sure the Ollama service is running.

### 6. Initialize and populate the database

The SQL schema in `sql/001_schema.sql` and metadata migration in `sql/002_ingestion_metadata.sql` execute automatically **only on a fresh database volume**. Do not delete an existing volume to rerun initialization: that destroys stored data. For older volumes, `python -m src.ingest` detects and applies the additive metadata migration.

If upgrading an older installation, review `CHUNK_WORDS=160` and `CHUNK_OVERLAP=30` in `.env` before ingesting.

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

## RAG Evaluation

The evaluation set in `data/evaluation.json` contains 14 questions, expected relevant source articles selected from `data/corpus.json`, categories, and answer key points. Expected titles are article-level relevance labels; review them against the resolved Wikipedia titles in your database before reporting results. Add target-use-case questions and have another team member check the expected sources and key points to strengthen the ground truth.

With MariaDB running and articles ingested, run the end-to-end evaluation:

```bash
python evaluate.py
```

This calls the same `search()` and Ollama `generate_answer()` functions as the app. It writes `evaluation-results.json` (summary plus each answer/error) and `evaluation-results.csv` (one row per question), which can be opened in a spreadsheet for charts. The summary reports Precision@k, Recall@k, MRR@k, nDCG@k, key-point coverage, citation presence/validity, failure rate, and mean/median/p95 latency. CSV fields support charts of retrieval metrics and latency by question. Model generation can be skipped to isolate retrieval:

```bash
python evaluate.py --retrieval-only
python evaluate.py --k 10 --output reports/run-1
```

Run metric and SQL-filter unit tests with `python -m unittest tests.test_evaluation -v`. Retrieval relevance uses expected article titles at article level. Key-point coverage is a literal phrase-match proxy, not a semantic judge, and citation checks verify citation format/index range, not whether a cited passage supports each claim. Human review is needed for answer relevance and factual support. Latency depends on model warm-up, hardware, and database state; report those conditions with results. The first run can be slower while the embedding model initializes. Generation latency is primarily local Ollama/model performance.

## Current Corpus

`data/corpus.json` lists about 70 English Wikipedia articles in five categories chosen to match the project topic: databases (including MariaDB, indexing and transactions), information retrieval and vector search (BM25, nearest-neighbour search, HNSW, RAG), machine learning, natural language processing and embeddings, and computer-science fundamentals. The original ten articles are all included. To grow the corpus, add titles to the file and re-run `python -m src.ingest`.

## Current Limitations and Future Work

- Citation validation checks source-number references, not the factual support of every claim.
- Ground-truth title relevance should be independently reviewed and expanded as the corpus and use cases grow.
- Article link relationships are not ingested, so link-based filters are not available.
- Hybrid lexical and vector retrieval can be explored.
- GPU acceleration and embedding optimization are future improvements.
- Article quality classes (WikiProject assessments) could be stored and used to weight retrieval.

## Vector Search Performance & Benchmarking

### HNSW Index Architecture
Semantic search queries use MariaDB's native `VECTOR(384)` data type paired with an **HNSW (Hierarchical Navigable Small World)** vector index (`DISTANCE=cosine`) on `chunks.embedding`. 

- **Index Validation:** Verified using `EXPLAIN`, confirming that `ORDER BY VEC_DISTANCE_COSINE(...) LIMIT N` utilizes the `embedding` index (`type: index`) rather than falling back to a full table scan (`type: ALL`).
- **Tuning Parameters:** 
  - **`M` (Graph Connections):** Configured with MariaDB's default (`M=6`), balancing fast index build times and low memory overhead with strong recall. Higher values (e.g., `M=16` or `32`) can be used at index creation to improve recall on larger datasets.
  - **`mhnsw_ef_search` (Search Candidate Pool):** Defaults to `20`. Increasing this session variable (e.g., `SET SESSION mhnsw_ef_search = 100;`) expands the candidate search pool for higher precision at the cost of slightly higher query latency.

### Benchmark Results
Using `benchmark.py` across a dataset of ~102 ingested Wikipedia articles (20 query iterations per test), comparing HNSW-indexed search against a forced full table scan (`IGNORE INDEX (embedding)`):

| Search Method | Total Time (20 Queries) | Avg. Latency per Query | Speedup |
| :--- | :--- | :--- | :--- |
| **With HNSW Index** | `0.0279 s` | **`1.39 ms`** | **6.15x faster** |
| **Without Index (Full Scan)** | `0.1716 s` | `8.58 ms` | Baseline (1.0x) |

### Running the Benchmark

The previous single-question, 20-iteration figures above are historical measurements. The current benchmark script performs a stronger, reproducible comparison against the exact full scan:

```bash
python benchmark.py
# Optional: more repeats, first five evaluation questions, custom report
python benchmark.py --iterations 30 --warmup 3 --limit 5 --k 5 --output reports/hnsw-30.json
```

The benchmark uses unique questions from `data/evaluation.json`, precomputes embeddings (excluded from SQL timing), warms both methods, randomly interleaves indexed and full-scan queries with a fixed seed, and reports mean, median and p95 SQL latency. It compares HNSW top-k chunk IDs with exact-scan top-k IDs to measure **recall@k against exact neighbors**, and writes the two `EXPLAIN` plans, configuration, corpus size, MariaDB version, and per-question results to JSON. The index choice must be verified from `EXPLAIN` rather than assumed. Approximate-neighbor recall is distinct from answer relevance or RAG correctness.

**For a credible report:** run the benchmark on the same populated database used in your demo, include hardware specifications and the generated JSON, and distinguish the old illustrative timings from the new measurements. Do not claim a new speedup until the script has actually run.

## Team Contributions

The project is divided into four areas:

- Database and infrastructure.
- Corpus collection and ingestion.
- Embeddings and semantic retrieval.
- Application, answer generation, and evaluation.

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.



## Database Design and Trade-offs

The `articles` table holds source metadata (Wikipedia page ID, title, URL, category, word count and ingestion timestamp). The `chunks` table holds ordered text passages, section labels and 384-dimensional embeddings. A foreign key `chunks.article_id -> articles.id` with `ON DELETE CASCADE` prevents orphan passages; article upserts and chunk replacement commit in one transaction. The vector index uses HNSW with cosine distance and `M=6`; the sentence-transformers `all-MiniLM-L6-v2` model produces the matching 384 dimensions. Chunks default to 160 words with 30-word overlap to preserve context while limiting model input truncation.

**Why MariaDB rather than a separate vector service?** One SQL query combines semantic ranking, metadata predicates and a relational join. The metadata and vectors participate in the same transactional database, avoiding a separate synchronization pipeline. This does **not** mean every combination of filters automatically uses the HNSW index: inspect `EXPLAIN` for the query shape and data distribution.

## Reproducible SQL walkthrough

After ingestion, connect using your local credentials (do not paste passwords into shell history):

```bash
docker exec -it vector-rag-mariadb mariadb -u rag_user -p vector_rag
```

Inspect the corpus and index:

```sql
SELECT COUNT(*) AS articles FROM articles;
SELECT COUNT(*) AS chunks FROM chunks;
SHOW CREATE TABLE chunks;
SELECT category, COUNT(*) AS article_count FROM articles GROUP BY category;
```

For the combined semantic and relational query, see `src/search.py`: the application binds the 384-dimensional query vector and optional category, word-count and ingestion-date predicates as parameters, joins `chunks` to `articles`, orders by `VEC_DISTANCE_COSINE`, and limits results. To inspect its execution plan, use `EXPLAIN` with an actual query vector produced by `src.embeddings.embed_query`; do not substitute a made-up short vector for a 384-dimensional embedding. The ingestion-date filter refers to local fetch time, **not** the Wikipedia article's edit time.

## Evaluation and reproducibility notes

The evaluation dataset has 14 questions. Run `python evaluate.py --retrieval-only` and `python evaluate.py` after ingesting. Publish measured metrics with the database article/chunk counts, machine specifications, MariaDB version, embedding model, Ollama model, and warm/cold-run conditions. Do not treat literal key-point matches or valid citation numbers as proof of factual grounding. The benchmark figures above are historical reported results, not independently reproduced here.

## Security boundaries

This example is designed for trusted local use. Docker binds the database port to loopback, and passwords must be set in a private `.env` file. Do not expose the database or Ollama to the public internet. Retrieved Wikipedia text is third-party content and must not be treated as instructions to the language model; generated answers and their citations should be checked before being relied on. The application has not been security-audited for public multi-user deployment.
