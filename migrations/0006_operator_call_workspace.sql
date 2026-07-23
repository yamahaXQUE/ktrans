BEGIN;

ALTER TABLE task_candidates
    ADD COLUMN conversation_title varchar(160) NOT NULL DEFAULT '';

UPDATE task_candidates
SET conversation_title = COALESCE(
    NULLIF(btrim(task_name), ''),
    'Разговор с клиентом'
);

ALTER TABLE task_candidates
    ADD CONSTRAINT task_candidates_conversation_title_check CHECK (
        btrim(conversation_title) <> ''
    );

ALTER TABLE confirmed_tasks
    DROP CONSTRAINT confirmed_tasks_candidate_id_fkey,
    ADD CONSTRAINT confirmed_tasks_candidate_id_fkey
        FOREIGN KEY (candidate_id)
        REFERENCES task_candidates (id)
        ON DELETE CASCADE;

CREATE TABLE deleted_calls (
    bitrix_statistic_id bigint PRIMARY KEY,
    deleted_by_operator_id uuid
        REFERENCES operators (id) ON DELETE SET NULL,
    deleted_at timestamptz NOT NULL DEFAULT now()
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
    candidate.quality_criterion,
    candidate.complaint_basis,
    candidate.complaint_evidence,
    candidate.conversation_title
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

CREATE OR REPLACE VIEW operator_dashboard AS
WITH call_stats AS (
    SELECT
        operator_id,
        count(*) AS call_count,
        max(started_at) AS last_call_at
    FROM calls
    GROUP BY operator_id
),
candidate_stats AS (
    SELECT
        operator_id,
        count(*) FILTER (WHERE status = 'pending') AS pending_count,
        count(*) FILTER (WHERE status = 'confirmed') AS confirmed_count,
        count(*) FILTER (WHERE status = 'failed') AS failed_count,
        count(*) FILTER (WHERE status = 'rejected') AS rejected_count
    FROM candidate_feed
    GROUP BY operator_id
)
SELECT
    operator.id,
    operator.display_name,
    operator.work_position,
    COALESCE(call_stats.call_count, 0) AS call_count,
    COALESCE(candidate_stats.pending_count, 0) AS pending_count,
    COALESCE(candidate_stats.confirmed_count, 0) AS confirmed_count,
    COALESCE(candidate_stats.failed_count, 0) AS failed_count,
    COALESCE(candidate_stats.rejected_count, 0) AS rejected_count,
    call_stats.last_call_at
FROM operators AS operator
LEFT JOIN call_stats ON call_stats.operator_id = operator.id
LEFT JOIN candidate_stats ON candidate_stats.operator_id = operator.id
WHERE operator.active;

COMMIT;
