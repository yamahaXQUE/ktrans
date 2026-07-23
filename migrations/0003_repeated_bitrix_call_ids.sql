BEGIN;

-- One telephony conversation may have several statistic rows (call legs,
-- transfers, or different portal users) sharing the same Bitrix CALL_ID.
-- ID from voximplant.statistic.get remains the source row identity.
ALTER TABLE calls
    DROP CONSTRAINT calls_bitrix_call_id_key;

CREATE INDEX calls_bitrix_call_id_idx
    ON calls (bitrix_call_id);

COMMIT;
