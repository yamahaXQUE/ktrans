BEGIN;

ALTER TABLE calls
    ADD COLUMN raw_transcript text NOT NULL DEFAULT '',
    ADD COLUMN transcript_enhancement_model text,
    ADD COLUMN transcript_enhanced_at timestamptz,
    ADD COLUMN transcript_enhancement_error text;

-- Existing transcripts predate the readability pass. Preserve their current
-- value as the raw source so a later backfill remains reversible and auditable.
UPDATE calls
SET raw_transcript = transcript
WHERE btrim(transcript) <> '';

COMMIT;
