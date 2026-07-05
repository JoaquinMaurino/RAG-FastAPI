-- =============================================================================
-- Migration: Add tsvector column for Hybrid Search (Phase 2.2)
-- =============================================================================
-- Run this ONCE against your existing database to enable lexical full-text search.
--
-- What this does:
--   1. Adds a `content_tsv` column of type TSVECTOR to the chunks table.
--   2. Backfills it for all existing chunks using the 'simple' dictionary
--      (language-neutral, works for mixed ES/EN content).
--   3. Creates a GIN index on it (required for fast full-text search).
--   4. Creates a trigger that auto-updates content_tsv on every INSERT/UPDATE,
--      so the ingestion pipeline doesn't need to call to_tsvector() explicitly.
--
-- Why 'simple' and not 'spanish' or 'english'?
--   'simple' tokenizes without stemming. This means "running" won't match "run",
--   but exact terms like function names, error codes, and IDs always match.
--   For a mixed-language corpus, 'simple' is safer than picking one language.
-- =============================================================================

-- Step 1: Add the column (safe to run if already exists due to IF NOT EXISTS)
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS content_tsv TSVECTOR;

-- Step 2: Backfill existing rows
UPDATE chunks
    SET content_tsv = to_tsvector('simple', content)
    WHERE content_tsv IS NULL;

-- Step 3: GIN index for fast text search
CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv
    ON chunks USING GIN (content_tsv);

-- Step 4: Trigger function to auto-update tsvector on writes
CREATE OR REPLACE FUNCTION chunks_content_tsv_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.content_tsv := to_tsvector('simple', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger (drop and recreate to make script idempotent)
DROP TRIGGER IF EXISTS trg_chunks_content_tsv ON chunks;
CREATE TRIGGER trg_chunks_content_tsv
    BEFORE INSERT OR UPDATE OF content
    ON chunks
    FOR EACH ROW
    EXECUTE FUNCTION chunks_content_tsv_update();
