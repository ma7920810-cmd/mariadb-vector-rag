CREATE DATABASE IF NOT EXISTS vector_rag;
USE vector_rag;

CREATE TABLE IF NOT EXISTS articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(500) NOT NULL,
    wiki_url VARCHAR(1000) NOT NULL,
    wiki_page_id BIGINT UNSIGNED NULL,
    category VARCHAR(120) NOT NULL DEFAULT 'general',
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_articles_wiki_url (wiki_url(255)),
    KEY idx_articles_category (category),
    KEY idx_articles_title (title(191))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS chunks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    article_id BIGINT UNSIGNED NOT NULL,
    chunk_index INT UNSIGNED NOT NULL,
    content MEDIUMTEXT NOT NULL,
    word_count INT UNSIGNED NOT NULL,
    embedding VECTOR(384) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_article_chunk (article_id, chunk_index),
    KEY idx_chunks_article_id (article_id),
    VECTOR INDEX (embedding) M=6 DISTANCE=cosine,
    CONSTRAINT fk_chunks_article
      FOREIGN KEY (article_id) REFERENCES articles(id)
      ON DELETE CASCADE
) ENGINE=InnoDB;
