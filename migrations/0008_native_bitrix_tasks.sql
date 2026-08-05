BEGIN;

ALTER TABLE confirmed_tasks
    ADD COLUMN bitrix_method text;

UPDATE confirmed_tasks
SET bitrix_method = 'crm.item.add';

ALTER TABLE confirmed_tasks
    ALTER COLUMN bitrix_method SET NOT NULL,
    ALTER COLUMN bitrix_method SET DEFAULT 'tasks.task.add',
    ALTER COLUMN bitrix_entity_type_id DROP NOT NULL,
    ADD COLUMN responsible_bitrix_user_id bigint,
    ADD CONSTRAINT confirmed_tasks_bitrix_method_check CHECK (
        bitrix_method IN ('crm.item.add', 'tasks.task.add')
    ),
    ADD CONSTRAINT confirmed_tasks_responsible_check CHECK (
        responsible_bitrix_user_id IS NULL
        OR responsible_bitrix_user_id > 0
    );

COMMIT;
