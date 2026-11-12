import time
from src.db import connect
from sentence_transformers import SentenceTransformer
from src.config import EMBEDDING_MODEL

def run_benchmark():
    print("Loading embedding model for benchmark...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    query = "What is vector search?"
    
    # Generate actual embedding vector for the query
    query_embedding = model.encode(query).tolist()
    vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
    
    iterations = 20
    
    with connect() as conn:
        cursor = conn.cursor()
        
        # --- Test 1: With HNSW Index Enabled ---
        start_time = time.time()
        for _ in range(iterations):
            cursor.execute(
                """
                SELECT c.id, a.title, VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(%s)) AS distance
                FROM chunks AS c
                JOIN articles AS a ON a.id = c.article_id
                ORDER BY distance ASC
                LIMIT 5
                """,
                (vector_str,)
            )
            cursor.fetchall()
        indexed_time = time.time() - start_time
        
        # --- Test 2: Bypassing HNSW Index (Full Table Scan) ---
        start_time = time.time()
        for _ in range(iterations):
            cursor.execute(
                """
                SELECT chunks.id, a.title, VEC_DISTANCE_COSINE(chunks.embedding, VEC_FromText(%s)) AS distance
                FROM chunks IGNORE INDEX (embedding)
                JOIN articles AS a ON a.id = chunks.article_id
                ORDER BY distance ASC
                LIMIT 5
                """,
                (vector_str,)
            )
            cursor.fetchall()
        non_indexed_time = time.time() - start_time

    print("\n--- Benchmark Results (20 Iterations) ---")
    print(f"With HNSW Index:     {indexed_time:.4f} sec (Avg: {(indexed_time/iterations)*1000:.2f} ms)")
    print(f"Without HNSW Index:  {non_indexed_time:.4f} sec (Avg: {(non_indexed_time/iterations)*1000:.2f} ms)")
    speedup = non_indexed_time / indexed_time if indexed_time > 0 else 0
    print(f"Index Speedup:       {speedup:.2f}x faster")

if __name__ == "__main__":
    run_benchmark()