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
│   ├── search.py
│   └── generation.py
├── sql/
│   └── 001_schema.sql
├── tests/
│   └── test_chunking.py
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

If you are using an existing database volume, the initialization script will not run again automatically. In that case, initialize or update the schema manually if necessary.

Ingest the Wikipedia articles:

python -m src.ingest

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

The ingestion pipeline currently uses these ten Wikipedia articles:

1. Computer science
2. Database
3. Information retrieval
4. Machine learning
5. Neural network
6. Database management system
7. Computer data storage
8. Supervised learning
9. Gradient descent
10. Backpropagation

## Current Limitations and Future Work

- Citation validation checks source-number references, not the factual support of every claim.
- Retrieval quality needs systematic evaluation against a prepared question set.
- HNSW index usage and query performance should be verified with query plans and benchmarks.
- Hybrid lexical and vector retrieval can be explored.
- GPU acceleration and embedding optimization are future improvements.
- The corpus can be expanded with additional relevant Wikipedia articles.

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
1. Ensure data has been ingested into the database (e.g., `python3 -m src.ingest`).
2. Run the benchmark script:
   ```bash
   python3 benchmark.py

## Team Contributions

The project is divided into four areas:

- Database and infrastructure.
- Corpus collection and ingestion.
- Embeddings and semantic retrieval.
- Application, answer generation, and evaluation.

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.


