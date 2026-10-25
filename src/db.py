"""MariaDB helpers. Vectors are stored in MariaDB's native VECTOR type."""
import json
import mariadb
from src.config import DB_CONFIG


def connect():
    """Open a connection using environment-configured credentials."""
    return mariadb.connect(**DB_CONFIG)


def vector_literal(values):
    """Serialize numeric embedding values as MariaDB vector JSON text."""
    return json.dumps([float(value) for value in values], separators=(",", ":"))
