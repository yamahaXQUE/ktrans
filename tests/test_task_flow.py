from types import SimpleNamespace
from datetime import datetime, timezone
import unittest

from backend.analyzer import AnalyzeText
from backend.task_create import (
    ConfirmedTask,
    RejectedTaskCandidate,
    TaskCandidate,
    task_cand,
)
from bitrix.bit import BitrixAPIError, BitrixClient, BitrixTaskMapper
from bitrix.mirror import BitrixMirror


class TaskDomainTests(unittest.TestCase):
    def test_old_candidate_shape_remains_supported(self):
        candidate = task_cand(
            task_id=101,
            task_name="Перезвонить клиенту",
            department="Продажи",
            iniciator=7,
            task_text_body="Уточнить объём заказа",
        )

        self.assertIsInstance(candidate, TaskCandidate)
        self.assertEqual(candidate.call_id, 101)
        self.assertEqual(candidate.task_description, "Уточнить объём заказа")
        self.assertEqual(candidate.initiator, 7)

    def test_operator_edits_create_a_new_entity(self):
        candidate = TaskCandidate(
            call_id="call-1",
            task_name="Черновое название",
            task_description="Черновое описание",
            department="Продажи",
            initiator=7,
            priority=2,
            should_create=True,
        )

        task = ConfirmedTask.from_candidate(
            candidate,
            title="Согласовать договор",
            description="Отправить финальную версию до пятницы",
            department=None,
            priority=5,
        )

        self.assertEqual(task.source_call_id, "call-1")
        self.assertEqual(task.title, "Согласовать договор")
        self.assertIsNone(task.department)
        self.assertEqual(task.priority, 5)
        self.assertEqual(candidate.task_name, "Черновое название")

    def test_negative_prediction_can_be_recorded_as_rejected(self):
        candidate = TaskCandidate(
            call_id="call-2",
            task_name="",
            task_description="",
            should_create=False,
            priority=1,
        )

        rejected = RejectedTaskCandidate.from_candidate(candidate, "Нет поручения")

        self.assertEqual(rejected.source_call_id, "call-2")
        self.assertEqual(rejected.reason, "Нет поручения")


class AnalyzerTests(unittest.TestCase):
    def test_analyzer_returns_domain_candidate(self):
        parse_calls = []

        class FakeResponses:
            def parse(self, **kwargs):
                parse_calls.append(kwargs)
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Жалоба на обслуживание",
                        "should_create": True,
                        "decision_basis": "explicit_complaint",
                        "complaint_evidence": (
                            "Клиент явно пожаловался на обслуживание."
                        ),
                        "requires_unstated_exact_data": False,
                        "task_type": "service_fm",
                        "quality_criterion": None,
                        "task_name": "Подготовить смету",
                        "task_description": "Отправить смету клиенту",
                        "department": "Расчётный отдел",
                        "priority": 4,
                    }
                )

        client = SimpleNamespace(responses=FakeResponses())
        candidate = AnalyzeText(
            "Клиент явно пожаловался на обслуживание и попросил разобраться.",
            client=client,
            call_id=55,
            initiator=9,
            model="test-model",
        ).analyze()

        self.assertEqual(candidate.call_id, 55)
        self.assertEqual(candidate.conversation_title, "Жалоба на обслуживание")
        self.assertEqual(candidate.task_name, "Подготовить смету")
        self.assertTrue(candidate.should_create)
        self.assertEqual(candidate.task_type, "service_fm")
        self.assertEqual(parse_calls[0]["model"], "test-model")
        self.assertEqual(parse_calls[0]["reasoning"], {"effort": "none"})
        self.assertFalse(parse_calls[0]["store"])

    def test_transcriber_uses_configured_model_and_context_prompt(self):
        calls = []

        class FakeTranscriptions:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(text="Клиент попросил перезвонить.")

        client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=FakeTranscriptions())
        )
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "call.mp3"
            recording.write_bytes(b"audio")
            from backend.analyzer import AnalyzeCall

            text = AnalyzeCall(
                directory,
                recording.name,
                client=client,
                model="test-transcribe",
            ).extract_text()

        self.assertEqual(text, "Клиент попросил перезвонить.")
        self.assertEqual(calls[0]["model"], "test-transcribe")
        self.assertIn("KULIKOV", calls[0]["prompt"])

    def test_analyzer_requires_none_for_calls_outside_closed_policy(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Уточнение часов работы",
                        "should_create": False,
                        "decision_basis": "none",
                        "complaint_evidence": "",
                        "requires_unstated_exact_data": False,
                        "task_type": "none",
                        "quality_criterion": None,
                        "task_name": "",
                        "task_description": "",
                        "department": None,
                        "priority": 1,
                    }
                )

        client = SimpleNamespace(responses=FakeResponses())
        candidate = AnalyzeText(
            "Клиент уточнил часы работы и попрощался.",
            client=client,
            call_id=56,
        ).analyze()

        self.assertFalse(candidate.should_create)
        self.assertEqual(candidate.task_type, "none")
        self.assertEqual(candidate.task_name, "")

    def test_complaint_without_model_task_remains_available_to_operator(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Жалоба без готовой задачи",
                        "should_create": False,
                        "decision_basis": "explicit_complaint",
                        "complaint_evidence": "Клиент выразил недовольство.",
                        "requires_unstated_exact_data": False,
                        "task_type": "none",
                        "quality_criterion": None,
                        "task_name": "",
                        "task_description": "",
                        "department": None,
                        "priority": 1,
                    }
                )

        candidate = AnalyzeText(
            "Клиент выразил недовольство, но не сформулировал поручение.",
            client=SimpleNamespace(responses=FakeResponses()),
            call_id=60,
        ).analyze()

        self.assertFalse(candidate.should_create)
        self.assertEqual(candidate.complaint_basis, "explicit_complaint")
        self.assertEqual(candidate.conversation_title, "Жалоба без готовой задачи")

    def test_quality_task_requires_criterion_from_document(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Жалоба на речь оператора",
                        "should_create": True,
                        "decision_basis": "explicit_complaint",
                        "complaint_evidence": (
                            "Клиент пожаловался на обращение «минуточку»."
                        ),
                        "requires_unstated_exact_data": False,
                        "task_type": "operator_quality_violation",
                        "quality_criterion": 13,
                        "task_name": "Разобрать уменьшительно-ласкательные слова",
                        "task_description": "Оператор использовал слово «минуточку».",
                        "department": None,
                        "priority": 2,
                    }
                )

        client = SimpleNamespace(responses=FakeResponses())
        candidate = AnalyzeText(
            (
                "Клиент: Я жалуюсь: оператор постоянно говорит мне «минуточку», "
                "это непрофессионально."
            ),
            client=client,
            call_id=57,
        ).analyze()

        self.assertEqual(candidate.task_type, "operator_quality_violation")
        self.assertEqual(candidate.quality_criterion, 13)

    def test_plain_delivery_request_cannot_be_promoted_to_task(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Обычная доставка мороженого",
                        "should_create": True,
                        "decision_basis": "none",
                        "complaint_evidence": "",
                        "requires_unstated_exact_data": False,
                        "task_type": "ice_cream",
                        "quality_criterion": None,
                        "task_name": "Доставить мороженое",
                        "task_description": "Отправить обычный заказ.",
                        "department": None,
                        "priority": 2,
                    }
                )

        client = SimpleNamespace(responses=FakeResponses())
        with self.assertRaisesRegex(
            ValueError,
            "explicit complaint or negative feedback",
        ):
            AnalyzeText(
                "Клиент оформил обычную доставку мороженого.",
                client=client,
                call_id=58,
            ).analyze()

    def test_task_requiring_unstated_exact_data_is_rejected(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Вопрос по платежу",
                        "should_create": True,
                        "decision_basis": "explicit_complaint",
                        "complaint_evidence": "Клиент сказал, что недоволен.",
                        "requires_unstated_exact_data": True,
                        "task_type": "payment_check",
                        "quality_criterion": None,
                        "task_name": "Проверить платёж",
                        "task_description": "Проверить неизвестный платёж.",
                        "department": None,
                        "priority": 3,
                    }
                )

        client = SimpleNamespace(responses=FakeResponses())
        with self.assertRaisesRegex(ValueError, "cannot require exact data"):
            AnalyzeText(
                "Клиент недоволен, но не назвал никакие данные платежа.",
                client=client,
                call_id=59,
            ).analyze()


class BitrixTests(unittest.TestCase):
    def setUp(self):
        self.task = ConfirmedTask(
            source_call_id="call-9",
            title="Подготовить смету",
            description="Отправить клиенту",
            department="Расчётный отдел",
            initiator=9,
            priority=4,
        )
        self.mapper = BitrixTaskMapper(
            {
                "title": "title",
                "description": "ufCrm42Description",
                "department": "ufCrm42Department",
                "initiator": "assignedById",
                "priority": "ufCrm42Priority",
                "source_call_id": "ufCrm42CallId",
            },
            value_encoders={"priority": lambda value: f"P{value}"},
        )

    def test_mapping_is_portal_specific(self):
        fields = self.mapper.to_bitrix_fields(self.task)

        self.assertEqual(fields["title"], "Подготовить смету")
        self.assertEqual(fields["ufCrm42Priority"], "P4")
        self.assertEqual(fields["ufCrm42CallId"], "call-9")

    def test_create_task_calls_crm_item_add_with_mapped_fields(self):
        calls = []

        def transport(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {"result": {"item": {"id": 321, **payload["fields"]}}}

        client = BitrixClient(
            "https://portal.example/rest/1/secret/",
            timeout=8,
            transport=transport,
        )
        result = client.create_task(
            self.task, entity_type_id=142, mapper=self.mapper
        )

        self.assertEqual(result.item_id, 321)
        self.assertEqual(
            calls[0][0],
            "https://portal.example/rest/1/secret/crm.item.add",
        )
        self.assertEqual(calls[0][1]["entityTypeId"], 142)
        self.assertEqual(calls[0][1]["fields"]["title"], "Подготовить смету")
        self.assertEqual(calls[0][2], 8)

    def test_api_error_is_not_treated_as_success(self):
        client = BitrixClient(
            "https://portal.example/rest/1/secret",
            transport=lambda *_: {
                "error": "ERROR_CORE",
                "error_description": "Bad fields",
            },
        )

        with self.assertRaisesRegex(BitrixAPIError, "Bad fields"):
            client.crm_item_add(entity_type_id=142, fields={"title": "x"})

    def test_list_pagination_follows_next_offset(self):
        starts = []

        def transport(_url, payload, _timeout):
            starts.append(payload["start"])
            if payload["start"] == 0:
                return {"result": [{"ID": "1"}, {"ID": "2"}], "next": 2}
            return {"result": [{"ID": "3"}], "total": 3}

        client = BitrixClient("https://portal.example/rest/x", transport=transport)
        rows = list(client.iter_list("user.get"))

        self.assertEqual([row["ID"] for row in rows], ["1", "2", "3"])
        self.assertEqual(starts, [0, 2])

    def test_mirror_parses_directory_and_call_contracts(self):
        responses = {
            "user.get": {
                "result": [
                    {
                        "ID": "7",
                        "ACTIVE": True,
                        "NAME": "Иван",
                        "LAST_NAME": "Петров",
                        "WORK_POSITION": "Оператор",
                        "EMAIL": "operator@example.test",
                        "UF_DEPARTMENT": ["10", "11"],
                        "UF_PHONE_INNER": "123",
                    }
                ]
            },
            "department.get": {
                "result": [
                    {
                        "ID": "10",
                        "NAME": "Продажи",
                        "PARENT": "1",
                        "UF_HEAD": "7",
                    }
                ]
            },
            "voximplant.statistic.get": {
                "result": [
                    {
                        "ID": "99",
                        "CALL_ID": "call.99",
                        "PORTAL_USER_ID": "7",
                        "PHONE_NUMBER": "+000000000",
                        "CALL_TYPE": "2",
                        "CALL_DURATION": "45",
                        "CALL_START_DATE": "2026-07-23T10:00:00+06:00",
                        "CALL_FAILED_CODE": "200",
                        "CRM_ENTITY_TYPE": "CONTACT",
                        "CRM_ENTITY_ID": "5",
                        "CRM_ACTIVITY_ID": "6",
                        "RECORD_FILE_ID": "8",
                        "CALL_RECORD_URL": "https://record.example.test/8",
                    }
                ]
            },
        }

        def transport(url, _payload, _timeout):
            method = url.rsplit("/", 1)[-1]
            return responses[method]

        mirror = BitrixMirror(
            BitrixClient("https://portal.example/rest/x", transport=transport)
        )

        user = next(mirror.iter_users())
        department = next(mirror.iter_departments())
        call = next(
            mirror.iter_calls(
                since=datetime(2026, 7, 22, tzinfo=timezone.utc)
            )
        )

        self.assertEqual(user.display_name, "Иван Петров")
        self.assertEqual(user.work_position, "Оператор")
        self.assertEqual(user.department_ids, (10, 11))
        self.assertEqual(department.head_user_id, 7)
        self.assertEqual(call.portal_user_id, 7)
        self.assertEqual(call.record_file_id, 8)

    def test_call_reader_requires_bounded_timezone_aware_date(self):
        mirror = BitrixMirror(
            BitrixClient(
                "https://portal.example/rest/x",
                transport=lambda *_: {"result": []},
            )
        )

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            list(mirror.iter_calls(since=datetime(2026, 7, 23)))


if __name__ == "__main__":
    unittest.main()
