-- ============================================================================
-- Twitch Analytics Platform - Categories Table
-- ============================================================================
-- Purpose: Normalized reference table for game/content categories
-- Dependencies: None (base table)
-- ============================================================================

CREATE TABLE IF NOT EXISTS categories (
    -- Primary identifier (Twitch's game/category ID)
    category_id BIGINT PRIMARY KEY,

    -- Category information
    category_name VARCHAR(255) NOT NULL,        -- Display name (e.g., "League of Legends")
    category_type VARCHAR(50),                  -- Type: 'game', 'creative', 'just_chatting', etc.
    box_art_url TEXT,                           -- Category thumbnail/box art

    -- External enrichment
    igdb_id BIGINT,                             -- Internet Games Database ID for metadata

    -- Trending analysis
    is_trending BOOLEAN DEFAULT false,          -- Flag for currently trending categories

    -- Temporal tracking
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- First time we saw this category
    last_seen_at TIMESTAMPTZ,                   -- Most recent broadcast using this category

    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes for Query Optimization
-- ============================================================================

-- Category name lookup
CREATE INDEX IF NOT EXISTS idx_categories_name
    ON categories(category_name);

-- Category type filtering
CREATE INDEX IF NOT EXISTS idx_categories_type
    ON categories(category_type)
    WHERE category_type IS NOT NULL;

-- Trending categories (sparse index for performance)
CREATE INDEX IF NOT EXISTS idx_categories_trending
    ON categories(is_trending)
    WHERE is_trending = true;

-- External ID lookup for enrichment
CREATE INDEX IF NOT EXISTS idx_categories_igdb
    ON categories(igdb_id)
    WHERE igdb_id IS NOT NULL;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE categories IS
    'Reference table for Twitch games and content categories. Enables category-level analytics and attribution.';

COMMENT ON COLUMN categories.category_id IS
    'Twitch category/game ID. Used for linking broadcasts to specific content types.';

COMMENT ON COLUMN categories.category_type IS
    'Broad category classification: game, creative, just_chatting, irl, music, etc.';

COMMENT ON COLUMN categories.is_trending IS
    'Flag for identifying trending games. Critical for distinguishing game-hype vs personality-driven growth.';

COMMENT ON COLUMN categories.igdb_id IS
    'Internet Games Database ID for potential enrichment with game metadata (release date, genre, etc).';

COMMENT ON COLUMN categories.last_seen_at IS
    'Most recent broadcast in this category. Helps identify dead/inactive games.';
