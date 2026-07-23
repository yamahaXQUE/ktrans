BEGIN;

CREATE TYPE operator_role AS ENUM ('operator', 'supervisor');
CREATE TYPE transcription_status AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed'
);
CREATE TYPE candidate_decision AS ENUM ('confirmed', 'rejected');
CREATE TYPE task_delivery_status AS ENUM ('pending', 'created', 'failed');

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    checksum char(64) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Contact Centre is the canonical operator scope discovered in Bitrix.
-- Runtime configuration can override this value without changing the schema.
INSERT INTO app_settings (key, value)
VALUES ('operator_department_bitrix_id', '82'::jsonb);

CREATE TABLE departments (
    bitrix_department_id bigint PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    parent_bitrix_department_id bigint
        REFERENCES departments (bitrix_department_id)
        DEFERRABLE INITIALLY DEFERRED,
    head_bitrix_user_id bigint,
    active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX departments_parent_idx
    ON departments (parent_bitrix_department_id);

CREATE TABLE operators (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bitrix_user_id bigint NOT NULL UNIQUE,
    display_name text NOT NULL CHECK (btrim(display_name) <> ''),
    work_position text NOT NULL DEFAULT '',
    email text,
    internal_phone text,
    active boolean NOT NULL DEFAULT true,
    role operator_role NOT NULL DEFAULT 'operator',
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX operators_active_name_idx
    ON operators (active, lower(display_name));

CREATE TABLE operator_departments (
    operator_id uuid NOT NULL
        REFERENCES operators (id) ON DELETE CASCADE,
    department_id bigint NOT NULL
        REFERENCES departments (bitrix_department_id) ON DELETE CASCADE,
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (operator_id, department_id)
);

CREATE UNIQUE INDEX operator_one_primary_department_idx
    ON operator_departments (operator_id)
    WHERE is_primary;

CREATE TABLE calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bitrix_statistic_id bigint NOT NULL UNIQUE,
    bitrix_call_id text NOT NULL UNIQUE CHECK (btrim(bitrix_call_id) <> ''),
    operator_id uuid NOT NULL
        REFERENCES operators (id) ON DELETE RESTRICT,
    call_type smallint NOT NULL CHECK (call_type BETWEEN 1 AND 5),
    duration_seconds integer NOT NULL DEFAULT 0 CHECK (duration_seconds >= 0),
    started_at timestamptz NOT NULL,
    phone_number text,
    phone_masked text NOT NULL DEFAULT '',
    failed_code text,
    crm_entity_type text,
    crm_entity_id bigint,
    crm_activity_id bigint,
    record_file_id bigint,
    recording_storage_key text,
    transcription_status transcription_status NOT NULL DEFAULT 'pending',
    transcript text NOT NULL DEFAULT '',
    transcription_error text,
    transcribed_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        transcription_status <> 'completed'
        OR btrim(transcript) <> ''
    )
);

CREATE INDEX calls_operator_started_idx
    ON calls (operator_id, started_at DESC);
CREATE INDEX calls_transcription_queue_idx
    ON calls (transcription_status, started_at)
    WHERE transcription_status IN ('pending', 'failed');

-- Immutable model prediction. Operator edits never overwrite these fields.
CREATE TABLE task_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id uuid NOT NULL UNIQUE
        REFERENCES calls (id) ON DELETE CASCADE,
    operator_id uuid NOT NULL
        REFERENCES operators (id) ON DELETE RESTRICT,
    should_create boolean NOT NULL,
    task_name varchar(160) NOT NULL DEFAULT '',
    task_description varchar(2000) NOT NULL DEFAULT '',
    predicted_department_id bigint
        REFERENCES departments (bitrix_department_id) ON DELETE SET NULL,
    predicted_department text,
    priority smallint NOT NULL CHECK (priority BETWEEN 1 AND 5),
    prediction_model text NOT NULL,
    raw_prediction jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        NOT should_create
        OR btrim(task_name) <> ''
    )
);

CREATE INDEX task_candidates_operator_created_idx
    ON task_candidates (operator_id, created_at DESC);

-- One explicit human decision per candidate.
CREATE TABLE candidate_reviews (
    candidate_id uuid PRIMARY KEY
        REFERENCES task_candidates (id) ON DELETE CASCADE,
    decision candidate_decision NOT NULL,
    decided_by_operator_id uuid NOT NULL
        REFERENCES operators (id) ON DELETE RESTRICT,
    rejection_reason varchar(400),
    decided_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (decision = 'rejected' AND rejection_reason IS NOT NULL)
        OR (decision = 'confirmed' AND rejection_reason IS NULL)
    )
);

-- The edited entity sent to Bitrix. It is deliberately separate from prediction.
CREATE TABLE confirmed_tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL UNIQUE
        REFERENCES task_candidates (id) ON DELETE RESTRICT,
    initiator_operator_id uuid NOT NULL
        REFERENCES operators (id) ON DELETE RESTRICT,
    title varchar(160) NOT NULL CHECK (btrim(title) <> ''),
    description varchar(2000) NOT NULL DEFAULT '',
    department_id bigint
        REFERENCES departments (bitrix_department_id) ON DELETE SET NULL,
    department_label text,
    priority smallint NOT NULL CHECK (priority BETWEEN 1 AND 5),
    delivery_status task_delivery_status NOT NULL DEFAULT 'pending',
    bitrix_entity_type_id integer NOT NULL CHECK (bitrix_entity_type_id > 0),
    bitrix_item_id text,
    failure_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (delivery_status = 'created' AND bitrix_item_id IS NOT NULL AND failure_reason IS NULL)
        OR (delivery_status = 'failed' AND bitrix_item_id IS NULL AND failure_reason IS NOT NULL)
        OR (delivery_status = 'pending' AND bitrix_item_id IS NULL)
    )
);

CREATE INDEX confirmed_tasks_delivery_idx
    ON confirmed_tasks (delivery_status, updated_at);

CREATE TABLE bitrix_task_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    confirmed_task_id uuid NOT NULL
        REFERENCES confirmed_tasks (id) ON DELETE CASCADE,
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    request_payload jsonb NOT NULL,
    response_payload jsonb,
    succeeded boolean NOT NULL,
    error_code text,
    error_message text,
    attempted_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (confirmed_task_id, attempt_no),
    CHECK (
        (succeeded AND error_code IS NULL AND error_message IS NULL)
        OR NOT succeeded
    )
);

CREATE TABLE user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL
        REFERENCES operators (id) ON DELETE CASCADE,
    bitrix_member_id text,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_sessions_expiry_idx ON user_sessions (expires_at);

CREATE FUNCTION touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER departments_touch_updated_at
BEFORE UPDATE ON departments
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER operators_touch_updated_at
BEFORE UPDATE ON operators
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER calls_touch_updated_at
BEFORE UPDATE ON calls
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER confirmed_tasks_touch_updated_at
BEFORE UPDATE ON confirmed_tasks
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

COMMIT;
