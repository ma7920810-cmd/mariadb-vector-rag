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

## Team Contributions

The project is divided into four areas:

- Database and infrastructure.
- Corpus collection and ingestion.
- Embeddings and semantic retrieval.
- Application, answer generation, and evaluation.


