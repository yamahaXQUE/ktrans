BEGIN;

ALTER TABLE confirmed_tasks
    DROP CONSTRAINT confirmed_tasks_bitrix_method_check;

ALTER TABLE confirmed_tasks
    ALTER COLUMN bitrix_method SET DEFAULT 'task.item.add',
    ADD CONSTRAINT confirmed_tasks_bitrix_method_check CHECK (
        bitrix_method IN (
            'crm.item.add',
            'tasks.task.add',
            'task.item.add'
        )
    );

COMMIT;
