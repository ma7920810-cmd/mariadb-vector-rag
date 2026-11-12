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
# Must match VECTOR(384) in sql/001_schema.sql.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

# all-MiniLM-L6-v2 truncates input after 256 word pieces (~190 English words),
# so chunks larger than this are only partially embedded. 160 words plus the
# "Title — Section:" prefix stays under the limit for typical Wikipedia prose.
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "160"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "30"))
MIN_CHUNK_WORDS = int(os.getenv("MIN_CHUNK_WORDS", "30"))
TOP_K = int(os.getenv("TOP_K", "5"))

# Wikimedia's User-Agent policy asks for contact information so operators can
# reach you instead of blocking you. Set WIKI_CONTACT to an email or URL.
WIKI_CONTACT = os.getenv(
    "WIKI_CONTACT", "https://github.com/ma7920810-cmd/mariadb-vector-rag"
)
WIKI_API_URL = os.getenv("WIKI_API_URL", "https://en.wikipedia.org/w/api.php")
WIKI_REQUEST_DELAY = float(os.getenv("WIKI_REQUEST_DELAY", "0.5"))
