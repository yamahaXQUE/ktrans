BEGIN;

ALTER TABLE calls
    ADD COLUMN analysis_requested_at timestamptz,
    ADD COLUMN analysis_requested_by_operator_id uuid
        REFERENCES operators (id) ON DELETE SET NULL;

CREATE INDEX calls_manual_analysis_queue_idx
    ON calls (analysis_requested_at, started_at)
    WHERE analysis_requested_at IS NOT NULL
      AND transcription_status IN ('pending', 'failed');

ALTER TABLE task_candidates
    ADD COLUMN task_type varchar(64) NOT NULL DEFAULT 'legacy',
    ADD COLUMN quality_criterion smallint;

UPDATE task_candidates
SET task_type = 'none'
WHERE NOT should_create;

ALTER TABLE task_candidates
    ADD CONSTRAINT task_candidates_task_type_check CHECK (
        task_type IN (
            'legacy',
            'service_fm',
            'bar_food',
            'product_quality_food_safety',
            'semi_finished_products',
            'ice_cream',
            'camera_recording',
            'receipt_search',
            'mobile_app_error',
            'mobile_app_wrong_information',
            'payment_check',
            'operator_quality_violation',
            'none'
        )
    ),
    ADD CONSTRAINT task_candidates_type_decision_check CHECK (
        (task_type = 'none' AND NOT should_create)
        OR (task_type <> 'none' AND should_create)
    ),
    ADD CONSTRAINT task_candidates_quality_criterion_check CHECK (
        (
            task_type = 'operator_quality_violation'
            AND quality_criterion BETWEEN 1 AND 20
        )
        OR (
            task_type <> 'operator_quality_violation'
            AND quality_criterion IS NULL
        )
    );

CREATE OR REPLACE VIEW candidate_feed AS
SELECT
    candidate.id,
    candidate.call_id,
    candidate.operator_id,
    candidate.should_create,
    COALESCE(task.title, candidate.task_name) AS task_name,
    COALESCE(task.description, candidate.task_description) AS task_description,
    COALESCE(
        task.department_label,
        task_department.name,
        candidate.predicted_department,
        predicted_department.name
    ) AS department,
    COALESCE(task.priority, candidate.priority) AS priority,
    CASE
        WHEN review.decision = 'rejected' THEN 'rejected'
        WHEN task.delivery_status = 'created' THEN 'confirmed'
        WHEN task.delivery_status = 'failed' THEN 'failed'
        ELSE 'pending'
    END AS status,
    task.bitrix_item_id,
    task.failure_reason,
    review.rejection_reason,
    candidate.created_at,
    GREATEST(
        candidate.created_at,
        COALESCE(review.decided_at, candidate.created_at),
        COALESCE(task.updated_at, candidate.created_at)
    ) AS updated_at,
    candidate.task_type,
    candidate.quality_criterion
FROM task_candidates AS candidate
LEFT JOIN candidate_reviews AS review
    ON review.candidate_id = candidate.id
LEFT JOIN confirmed_tasks AS task
    ON task.candidate_id = candidate.id
LEFT JOIN departments AS task_department
    ON task_department.bitrix_department_id = task.department_id
LEFT JOIN departments AS predicted_department
    ON predicted_department.bitrix_department_id =
       candidate.predicted_department_id;

COMMIT;
