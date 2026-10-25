"""Shared configuration for the Wikipedia vector-search project."""
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("MARIADB_HOST", "127.0.0.1"),
    "port": int(os.getenv("MARIADB_PORT", "3306")),
    "user": os.getenv("MARIADB_USER", "rag_user"),
    "password": os.getenv("MARIADB_PASSWORD", "rag-dev-password"),
    "database": os.getenv("MARIADB_DATABASE", "vector_rag"),
}
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
TOP_K = int(os.getenv("TOP_K", "5"))
