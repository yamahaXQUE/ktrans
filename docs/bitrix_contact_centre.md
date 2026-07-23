# Bitrix operator scope snapshot

Snapshot taken from the portal on 2026-07-23.

The canonical scope is Bitrix department **82 — `Contact Centre`**:

- department head: **Ирина Гришкова** (`user ID 9`),
  `Руководитель Контакт Центра`;
- supervisor: **Регина Лазаревич** (`user ID 10`),
  `Супервайзер контакт - центра`;
- acting head: **Айбарша Оралбай** (`user ID 54103`),
  `И. О. Руководитель контакт-центра`.

Active directory membership:

| Bitrix user ID | Name | Position / resolved role |
| ---: | --- | --- |
| 9 | Ирина Гришкова | Руководитель Контакт Центра / supervisor |
| 10 | Регина Лазаревич | Супервайзер контакт - центра / supervisor |
| 13 | Светлана Невечеря | operator |
| 43654 | Анастасия Захарова | operator |
| 54103 | Айбарша Оралбай | И. О. Руководитель контакт-центра / supervisor |
| 55520 | Ранохан Рустамова | operator |
| 74428 | Элина Кулубекова | operator |
| 175658 | Максат Жамалбек уулу | operator |
| 248352 | Бекболат Утемуратов | senior operator |
| 248359 | Али Дахан | operator |
| 248362 | Шокан Дарбай | operator |
| 252068 | Тамерлан Ерболатулы | operator |
| 253831 | Перизат Дарменалы | operator |
| 256470 | Динара Жусубакунова | operator |
| 256479 | Эльмира Шакирова | operator |
| 260169 | Курманжан Альберт | operator |
| 260833 | Сайдана Шайлозова | operator |

This file is only an audit snapshot. Migrations do not seed employee rows.
`python -m backend.sync_bitrix directory` refreshes departments, membership,
names, positions, and active flags from Bitrix. The role resolver treats the
department head and positions containing supervisor/head wording as
`supervisor`; everyone else in department 82 is an `operator`.

Department `1253 — Контакт центр` is a duplicate-looking directory branch
whose only active member was Ирина Гришкова. It is not used as the operator
scope.
