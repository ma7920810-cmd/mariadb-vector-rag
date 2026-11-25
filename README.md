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

For the evaluated configuration, set `CHUNK_WORDS=120` and `CHUNK_OVERLAP=20` in `.env` before ingestion. Changing either setting triggers re-chunking and re-embedding on the next ingestion run.

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
4. **Chunk** within sections at sentence boundaries (evaluated setting 120 words, 20 words of whole-sentence overlap). Each chunk is embedded as `"Title — Section: text"` so short passages keep their context. `chunks.content` stores the plain text.
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

### Staged evaluation history

The retrieval optimisation uses a fivefold candidate pool followed by a maximum of two passages per article to improve source diversity; the full optimisation adds local Ollama generation with a concise, source-grounded prompt and controlled generation settings. The final stage additionally tightened citation formatting and normalized explicit source references while rejecting out-of-range source numbers ([citation change](https://github.com/ma7920810-cmd/mariadb-vector-rag/commit/dcb6c295bcec32b7dd10ada0a0bb704a643cc681)).

| Report | Precision@5 | Recall@5 | MRR@5 | nDCG@5 | Citation validity | Median total latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Baseline](reports/evaluation-baseline.json) | .4988 | .8333 | .9643 | .8270 | 1.0000 | 3038.60 ms |
| [Retrieval optimised](reports/evaluation-optimized-retrieval.json) | .5702 | .9286 | .9286 | .8845 | N/A | 40.41 ms |
| [Full optimised](reports/evaluation-optimized-full.json) | .5702 | .9286 | .9286 | .8845 | .8571 | 2769.25 ms |
| [Final](reports/evaluation-final.json) | .5702 | .9286 | .9286 | .8845 | .9286 | 2563.56 ms |

All four reports contain 14 successful cases. Recall improved by 9.53 percentage points and precision by 7.14 points, while MRR decreased by 3.57 points. Final citation validity recovered relative to the full-optimised run but remained below baseline; key-point coverage stayed at .8095 across the three generation runs. The retrieval-only latency excludes generation and cannot be directly compared with end-to-end latency. Historical reports do not record every configuration or corpus snapshot, so these are observed stage differences, not a controlled causal ablation of each individual change.

After migrating the existing index to M=12, [the validation benchmark](reports/hnsw-benchmark-m12.json) measured 1.073 ms mean indexed SQL latency versus 217.651 ms exact scan (202.761x speedup), with 100% exact-neighbor recall. The [retrieval-only validation](reports/evaluation-m12-retrieval.json) retained .9286 semantic recall and .5702 precision with zero failures. These metrics measure different notions of recall.

### HNSW parameter selection

The [16-configuration sweep](reports/hnsw-sweep.json) on 2706 stored chunks compared M=6, 12, 24 and 48 at session search widths 20, 50, 100 and 200 against an exact scan of the same vectors. Each configuration used 14 questions and five timed repetitions per question.

| M | Recall@5 vs exact (width 20) | Mean SQL latency | Index build time |
| ---: | ---: | ---: | ---: |
| 6 | 97.14% | 0.882 ms | 0.316 s |
| 12 | 100% | 0.878 ms | 0.517 s |
| 24 | 100% | 0.876 ms | 1.607 s |
| 48 | 100% | 1.047 ms | 5.198 s |

Increasing search width did not recover the missing neighbors at M=6 in this run. M=12 recovered all exact neighbors at every tested width, with substantially lower construction cost than M=24 or M=48. We therefore select M=12 for new installations and recommend width 20 for this workload. This is nearest-neighbor overlap, not human-judged relevance; the small query set and single index build per M limit generalization. EXPLAIN selected the sweep vector index in every configuration.

Reproduce without modifying the application index (requires CREATE, ALTER and DROP privileges on a dedicated benchmark table):

```bash
python benchmark_sweep.py
```

Existing installations retain their original index until explicitly rebuilt. Inspect SHOW CREATE TABLE chunks before migrating; back up the database and schedule index rebuilding during downtime.

## Corpus

The curated dataset contains 71 English Wikipedia articles in five categories: databases, information retrieval, machine learning, natural-language processing, and computer science. See `data/corpus.json` and `docs/DATASET.md` for the article list and ingestion approach.

## Limitations

- The curated 14-question evaluation is small; expected article titles and answer key points need independent review.
- Citation checks validate formatting and source indices, not factual entailment; Ollama can still omit citations or produce incomplete explanations.
- Wikipedia link relationships are not stored, and date filters use ingestion time rather than Wikipedia edit time.
- Hybrid lexical-vector retrieval and larger-corpus benchmarks remain future work.

## Measured Results (November 2026)

The evaluated local corpus contained **71 Wikipedia articles**, **2,706 chunks**, and five categories. Ingestion used `CHUNK_WORDS=120` and `CHUNK_OVERLAP=20`; only three chunks exceeded the embedding model's 256-token input. All 37 automated tests passed.

### Retrieval and answer evaluation

The 14-question evaluation uses article-level relevance labels and literal answer key-point matching.

| Metric | Measured result |
| --- | ---: |
| Precision@5 | 0.5702 |
| Recall@5 | 0.9286 |
| MRR@5 | 0.9286 |
| nDCG@5 | 0.8845 |
| Answer key-point coverage | 0.8095 |
| Citation presence | 0.9286 |
| Citation validity | 0.9286 |
| Failed evaluation cases | 0 / 14 |
| Mean end-to-end latency | 3,061.03 ms |

Citation validity checks recognized source-number references against the retrieved passages, **not** whether each claim is factually supported. The 14 questions are a small curated test set; the measurements should not be generalized to other corpora.

### Native HNSW benchmark

`python benchmark.py --iterations 10 --warmup 2 --k 5` compared the native `embedding` vector index against exact SQL search with `IGNORE INDEX (embedding)`, using 14 unique questions.

| SQL latency | Indexed | Exact scan |
| --- | ---: | ---: |
| Mean | **1.101 ms** | 217.391 ms |
| Median | 1.069 ms | 217.440 ms |
| P95 | 1.409 ms | 221.450 ms |

**Measured mean speedup: 197.42×.** Indexed top-five results matched exact search for all 14 queries (**recall@5 versus exact: 1.0**). `EXPLAIN` selected the `embedding` index (`type=index`) for indexed SQL and a full scan (`type=ALL`, `Using filesort`) for exact SQL. These are SQL-only timings excluding embedding and LLM generation, on the tested local machine and dataset.

The benchmark's configuration, per-question results, and query plans are recorded in `reports/hnsw-benchmark.json`. Full evaluation records are in `reports/evaluation-final.json`; historical baseline and intermediate results are also in `reports/`.

To reproduce after ingestion:

```bash
python evaluate.py
python benchmark.py --iterations 10 --warmup 2 --k 5
python -m unittest discover -s tests -v
```

## Team Contributions

This four-person team divided work across database infrastructure, corpus ingestion, vector retrieval, and application/evaluation. The repository history documents the implementation.

## License

MIT — see [LICENSE](LICENSE).


## Database Design and Trade-offs

The `articles` table holds source metadata (Wikipedia page ID, title, URL, category, word count and ingestion timestamp). The `chunks` table holds ordered text passages, section labels and 384-dimensional embeddings. A foreign key `chunks.article_id -> articles.id` with `ON DELETE CASCADE` prevents orphan passages; article upserts and chunk replacement commit in one transaction. The vector index uses HNSW with cosine distance and `M=12` for new installations (historical benchmarks used M=6); the sentence-transformers `all-MiniLM-L6-v2` model produces the matching 384 dimensions. The evaluated corpus used `CHUNK_WORDS=120` and `CHUNK_OVERLAP=20` to reduce embedding-input truncation. The code defaults may differ unless overridden in `.env`.

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

For a runnable, parameterized native-vector SQL walkthrough, use:

```bash
python -m src.sql_demo
python -m src.sql_demo --question "What is vector search?" --category databases --min-words 500
```

The demonstration prints corpus counts, the `embedding` index metadata, the actual `EXPLAIN` plan, and ranked results from a `JOIN` with category and minimum-word-count predicates. A vector index exists in the schema, but the optimizer may choose a full scan for filtered queries; the displayed plan is the evidence. Query vectors are computed from the real embedding model, not fabricated examples.

For the combined semantic and relational query, see `src/search.py`: the application binds the 384-dimensional query vector and optional category, word-count and ingestion-date predicates as parameters, joins `chunks` to `articles`, orders by `VEC_DISTANCE_COSINE`, and limits results. To inspect its execution plan, use `EXPLAIN` with an actual query vector produced by `src.embeddings.embed_query`; do not substitute a made-up short vector for a 384-dimensional embedding. The ingestion-date filter refers to local fetch time, **not** the Wikipedia article's edit time.

## Security boundaries

This example is designed for trusted local use. Docker binds the database port to loopback, and passwords must be set in a private `.env` file. Do not expose the database or Ollama to the public internet. Retrieved Wikipedia text is third-party content and must not be treated as instructions to the language model; generated answers and their citations should be checked before being relied on. The application has not been security-audited for public multi-user deployment.

### Expanded retrieval evaluation

The 54-question dataset preserves the original 14 cases and adds 40 across five categories. On the 2,706-chunk corpus, the expanded HNSW benchmark measured 100% top-5 overlap with exact search and 194.33x mean SQL speedup (1.121 vs 217.772 ms). See `reports/hnsw-benchmark-expanded.json`.

After normalizing the confirmed Transformer title redirect, `python compare_retrieval.py` compared three configurations:

| Candidate pool / article cap | Precision@5 | Recall@5 | MRR@5 | nDCG@5 | Mean retrieval ms |
|---|---:|---:|---:|---:|---:|
| 25 / 2 (default) | .4287 | .9444 | .8457 | .8583 | 5.82 |
| 50 / 1 | .2812 | .9537 | .8457 | .8640 | 8.12 |
| 50 / 2 | .3994 | .9537 | .8457 | .8640 | 8.24 |

All 162 retrieval evaluations succeeded. For recall-oriented use, set `RAG_POOL_FACTOR=10 RAG_ARTICLE_CAP=2` in the process environment. The default remains unchanged pending generation validation. Precision is sensitive to incomplete relevance labels and the number of distinct articles returned; these labels are not independently adjudicated. Reports are in `reports/retrieval-comparison-*.json`. The alias correction means these scores are not directly comparable to earlier uncorrected reports.
