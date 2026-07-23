# PostgreSQL migrations

Migrations are ordered plain SQL and are applied by:

```powershell
$env:DATABASE_URL = "postgresql://user:password@localhost:5432/call_tasks"
python -m backend.migrate
```

`0001_core.sql` stores the immutable prediction separately from the operator's
review, edited confirmed task, and every Bitrix delivery attempt.
`0002_frontend_views.sql` exposes stable read models used by the React DTOs.
`0003_repeated_bitrix_call_ids.sql` reflects live telephony semantics: several
statistic rows may share one `CALL_ID`, while `bitrix_statistic_id` stays
unique.

The migration seeds only the stable integration setting
`operator_department_bitrix_id = 82` (`Contact Centre`). Employee rows remain
Bitrix-owned data and are populated/upserted by the sync command, never frozen
inside a migration.

Core ownership:

| Table | Meaning |
| --- | --- |
| `departments`, `operators`, `operator_departments` | Bitrix directory mirror |
| `calls` | Bitrix telephony row plus backend transcription |
| `task_candidates` | immutable model prediction |
| `candidate_reviews` | current operator decision |
| `confirmed_tasks` | operator-edited entity sent to Bitrix |
| `bitrix_task_attempts` | every `crm.item.add` attempt |
| `user_sessions` | server-side iframe sessions |

The `candidate_feed` and `operator_dashboard` views are frontend read models;
the frontend never needs to reconstruct workflow state from write tables.

Migration `0004_analysis_policy_and_manual_queue.sql` adds the closed
`task_type` taxonomy, an optional quality criterion (1-20), and the audited
manual-analysis request fields used for calls outside the automatic employee
allowlist.

Migration `0005_explicit_complaint_gate.sql` records the model's explicit
complaint basis and evidence. Candidate lists and dashboard counters include
only a customer complaint or clearly negative customer feedback; prior
predictions remain stored as `legacy` for audit but are hidden from work queues.

Migration `0006_operator_call_workspace.sql` adds the always-present
conversation title, deletion tombstones, and cascading removal of local task
history. Migration `0007_operator_decides_task.sql` allows the model to report
a complaint without recommending a task; the operator remains the final
decision-maker.
