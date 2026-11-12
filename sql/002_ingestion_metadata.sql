-- Migration 002: ingestion metadata, change detection and duplicate prevention.
--
-- Additive only: no existing column, index or the VECTOR(384) embedding is
-- changed, so src/search.py and app.py keep working unchanged.
--
-- Applied automatically:
--   * on a fresh Docker volume (mounted into /docker-entrypoint-initdb.d), and
--   * by `python -m src.ingest` when it detects the columns are missing
--     (for databases created before this migration existed).
-- Every clause uses IF NOT EXISTS, so re-running it is harmless.

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS rev_id BIGINT UNSIGNED NULL
        COMMENT 'Wikipedia revision id that was ingested' AFTER wiki_page_id,
    ADD COLUMN IF NOT EXISTS description VARCHAR(500) NULL
        COMMENT 'Wikipedia short description',
    ADD COLUMN IF NOT EXISTS word_count INT UNSIGNED NULL
        COMMENT 'Words of cleaned article text that was chunked',
    ADD COLUMN IF NOT EXISTS content_hash CHAR(64) NULL
        COMMENT 'SHA-256 of the cleaned article text',
    ADD COLUMN IF NOT EXISTS ingest_signature CHAR(16) NULL
        COMMENT 'Hash of chunker version + chunk settings + embedding model',
    ADD COLUMN IF NOT EXISTS source VARCHAR(40) NOT NULL DEFAULT 'wikipedia_api',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- One row per Wikipedia page, even if it is reached via a redirect or renamed.
    ADD UNIQUE KEY IF NOT EXISTS uq_articles_page_id (wiki_page_id);

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS section VARCHAR(255) NULL
        COMMENT 'Article section heading the chunk came from' AFTER chunk_index,
    ADD COLUMN IF NOT EXISTS content_hash CHAR(64) NULL
        COMMENT 'SHA-256 of normalised chunk text, for duplicate detection',
    ADD KEY IF NOT EXISTS idx_chunks_content_hash (content_hash);
