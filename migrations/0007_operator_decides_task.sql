BEGIN;

ALTER TABLE task_candidates
    DROP CONSTRAINT task_candidates_complaint_gate_check;

ALTER TABLE task_candidates
    ADD CONSTRAINT task_candidates_complaint_evidence_check CHECK (
        (
            complaint_basis = 'none'
            AND btrim(complaint_evidence) = ''
        )
        OR (
            complaint_basis = 'legacy'
        )
        OR (
            complaint_basis IN (
                'explicit_complaint',
                'explicit_negative_feedback'
            )
            AND btrim(complaint_evidence) <> ''
            AND char_length(complaint_evidence) <= 500
        )
    );

COMMIT;
