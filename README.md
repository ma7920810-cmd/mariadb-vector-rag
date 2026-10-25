# Area 4 — Native Vector Search and RAG with MariaDB

A four-person database project using **MariaDB 11.8**, native `VECTOR` storage, an HNSW vector index, semantic retrieval, and a small Wikipedia-backed search interface.

## What works in this starter

- MariaDB service and persistent local volume via Docker Compose.
- Relational schema for Wikipedia articles and text chunks, including a native vector column and cosine-distance vector index.
- Wikipedia ingestion pipeline: fetch pages, clean text, split into overlapping chunks, create 384-dimensional embeddings, and store them.
- Semantic top-k search using MariaDB's `VEC_DISTANCE_COSINE` and SQL joins; optional category filter.
- Minimal Streamlit interface that displays retrieved passages and their source links.
- Unit tests for chunking.

The first ingestion run uses five seed pages. Expand the corpus only after verifying the complete pipeline.

## Architecture

```text
Wikipedia API
    |
    v
fetch + clean --> overlapping chunks --> sentence-transformer embeddings
                                            |
                                            v
                              MariaDB 11.8 (articles + VECTOR chunks)
                                            |
User question --> query embedding ----------+
                                            |
                                            v
                            cosine-distance top-k retrieval
                                            |
                                            v
                           Streamlit UI + source passages
```

## Requirements

- Docker Desktop (or Docker Engine) with Compose
- Python 3.11 or 3.12 recommended
- Internet access for the first model download and Wikipedia ingestion

## Run locally

1. Clone the repository and enter the directory:

   ```bash
   git clone https://github.com/ma7920810-cmd/mariadb-vector-rag.git
   cd mariadb-vector-rag
   ```

2. Create your local environment file. Change the example passwords for your own machine:

   ```bash
   cp .env.example .env
   ```

   On Windows PowerShell, use `Copy-Item .env.example .env`.

3. Start MariaDB:

   ```bash
   docker compose up -d
   docker compose ps
   docker compose logs -f mariadb
   ```

   The schema is mounted as an initialization script. Docker runs it only when the database volume is first initialized. If you change the initial schema during development, apply the SQL manually or reset the local volume (resetting it deletes local database data).

4. Create and activate a Python environment:

   **Windows PowerShell**
   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   **Linux / WSL / macOS**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Ingest the initial Wikipedia pages (downloads the embedding model on first run):

   ```bash
   python -m src.ingest
   ```

6. Start the interface:

   ```bash
   streamlit run app.py
   ```

7. Run the unit tests:

   ```bash
   python -m unittest discover -s tests -v
   ```

## Database design

- `articles`: article title, canonical Wikipedia URL, page ID, category, fetch timestamp.
- `chunks`: article reference, chunk order, text, word count, and `VECTOR(384)` embedding.
- `VECTOR INDEX`: HNSW index configured for cosine distance.
- Query retrieval uses a normal SQL join so relational filters can be combined with semantic ranking.

Confirm the exact vector-index and vector-function syntax against the MariaDB 11.8 server image used by your team before the demonstration; native vector features are version-specific.

## Four-person work split

1. **Database / infrastructure:** MariaDB setup, schema, index configuration, SQL correctness, performance measurements.
2. **Corpus / ingestion:** Wikipedia data acquisition, cleaning, chunking, deduplication, and corpus expansion.
3. **Embeddings / retrieval:** embedding model evaluation, semantic top-k retrieval, metadata filters, and hybrid-search experiments.
4. **Application / evaluation:** Streamlit UX, source excerpts, test queries, retrieval evaluation, and demo/report integration.

Everyone should review and understand the SQL and contribute to evaluation. Pick a focused Wikipedia topic after the initial end-to-end pipeline runs.

## Important notes

- Do not commit `.env`, passwords, model files, or a large Wikipedia dump.
- The supplied credentials are local development defaults only; do not expose this database to a public network.
- This first version performs retrieval and shows source passages; it does **not** yet generate an LLM answer. The RAG generation stage and hybrid lexical/vector ranking are follow-up tasks.
- Wikipedia text is available under its applicable license; preserve attribution and source URLs in any report or demo.
