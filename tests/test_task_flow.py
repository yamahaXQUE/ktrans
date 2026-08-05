from types import SimpleNamespace
from datetime import datetime, timezone
import unittest

from backend.analysis_daemon import _enhance_with_fallback
from backend.analyzer import AnalyzeText, EnhanceTranscript
from backend.task_create import (
    ConfirmedTask,
    RejectedTaskCandidate,
    TaskCandidate,
    task_cand,
)
from bitrix.bit import BitrixAPIError, BitrixClient
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
                            "Клиент явно пожаловался на обслуживание в магазине."
                        ),
                        "is_concrete_complaint": True,
                        "complaint_subject": "обслуживание в магазине",
                        "complaint_issue": "меня обслужили ненадлежащим образом",
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
            (
                "Клиент явно пожаловался на обслуживание в магазине. "
                "Меня обслужили ненадлежащим образом."
            ),
            client=client,
            call_id=55,
            initiator=9,
            model="test-model",
        ).analyze()

        self.assertEqual(candidate.call_id, 55)
        self.assertEqual(candidate.conversation_title, "Жалоба на обслуживание")
        self.assertEqual(candidate.task_name, "Подготовить смету")
        self.assertTrue(candidate.should_create)
        self.assertTrue(candidate.is_concrete_complaint)
        self.assertEqual(candidate.complaint_subject, "обслуживание в магазине")
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

    def test_transcript_enhancer_uses_structured_private_response(self):
        calls = []

        class FakeResponses:
            def parse(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    output_parsed={
                        "transcript": (
                            "Оператор: Добрый день.\n\n"
                            "Клиент: Заказ 123 всё ещё не доставили."
                        )
                    }
                )

        readable = EnhanceTranscript(
            "добрый день заказ 123 всё ещё не доставили",
            client=SimpleNamespace(responses=FakeResponses()),
            model="test-enhancer",
        ).enhance()

        self.assertIn("Оператор:", readable)
        self.assertIn("123", readable)
        self.assertEqual(calls[0]["model"], "test-enhancer")
        self.assertEqual(calls[0]["reasoning"], {"effort": "none"})
        self.assertFalse(calls[0]["store"])
        self.assertEqual(calls[0]["text_format"].__name__, "_ReadableTranscript")
        self.assertIn("не добавляй", calls[0]["input"][0]["content"])

    def test_transcript_enhancement_failure_falls_back_to_raw_text(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                raise RuntimeError("temporary model failure")

        raw = "клиент назвал заказ 456"
        readable, error = _enhance_with_fallback(
            raw,
            client=SimpleNamespace(responses=FakeResponses()),
            model="test-enhancer",
        )

        self.assertEqual(readable, raw)
        self.assertIn("RuntimeError", error)

    def test_transcript_enhancer_prioritizes_readability_over_exact_numbers(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={"transcript": "Клиент назвал заказ 457."}
                )

        readable = EnhanceTranscript(
            "клиент назвал заказ 456",
            client=SimpleNamespace(responses=FakeResponses()),
        ).enhance()

        self.assertEqual(readable, "Клиент назвал заказ 457.")

    def test_analyzer_requires_none_for_calls_outside_closed_policy(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Уточнение часов работы",
                        "should_create": False,
                        "decision_basis": "none",
                        "complaint_evidence": "",
                        "is_concrete_complaint": False,
                        "complaint_subject": "",
                        "complaint_issue": "",
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

    def test_vague_negative_feedback_does_not_create_task(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Жалоба без готовой задачи",
                        "should_create": False,
                        "decision_basis": "explicit_negative_feedback",
                        "complaint_evidence": "Клиент выразил недовольство.",
                        "is_concrete_complaint": False,
                        "complaint_subject": "",
                        "complaint_issue": "",
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
        self.assertEqual(candidate.complaint_basis, "explicit_negative_feedback")
        self.assertFalse(candidate.is_concrete_complaint)
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
                            "оператор постоянно говорит мне «минуточку»"
                        ),
                        "is_concrete_complaint": True,
                        "complaint_subject": "оператор",
                        "complaint_issue": "постоянно говорит мне «минуточку»",
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

    def test_ungrounded_complaint_is_downgraded_to_no_task(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Жалоба на продукт",
                        "should_create": True,
                        "decision_basis": "explicit_complaint",
                        "complaint_evidence": "Клиент пожаловался на эклер.",
                        "is_concrete_complaint": True,
                        "complaint_subject": "заказ 123",
                        "complaint_issue": "привезли другой торт",
                        "requires_unstated_exact_data": False,
                        "task_type": "product_quality_food_safety",
                        "quality_criterion": None,
                        "task_name": "Проверить продукт",
                        "task_description": "Разобрать жалобу клиента.",
                        "department": None,
                        "priority": 3,
                    }
                )

        candidate = AnalyzeText(
            "Клиент пожаловался на эклер. Внутри была плесень.",
            client=SimpleNamespace(responses=FakeResponses()),
            call_id=61,
        ).analyze()

        self.assertFalse(candidate.should_create)
        self.assertEqual(candidate.task_type, "none")
        self.assertFalse(candidate.is_concrete_complaint)

    def test_plain_delivery_request_cannot_be_promoted_to_task(self):
        class FakeResponses:
            def parse(self, **_kwargs):
                return SimpleNamespace(
                    output_parsed={
                        "conversation_title": "Обычная доставка мороженого",
                        "should_create": True,
                        "decision_basis": "none",
                        "complaint_evidence": "",
                        "is_concrete_complaint": False,
                        "complaint_subject": "",
                        "complaint_issue": "",
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
            "explicit concrete complaint",
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
                        "is_concrete_complaint": True,
                        "complaint_subject": "платёж",
                        "complaint_issue": "неизвестный платёж требует проверки",
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
    def test_create_task_calls_native_tasks_method(self):
        calls = []

        def transport(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {"result": {"task": {"id": "321", **payload["fields"]}}}

        client = BitrixClient(
            "https://portal.example/rest/1/secret/",
            timeout=8,
            transport=transport,
        )
        result = client.tasks_task_add(
            fields={
                "TITLE": "Подготовить смету",
                "DESCRIPTION": "Отправить клиенту",
                "RESPONSIBLE_ID": 9,
                "PRIORITY": "2",
            }
        )

        self.assertEqual(result.task_id, "321")
        self.assertEqual(
            calls[0][0],
            "https://portal.example/rest/1/secret/tasks.task.add",
        )
        self.assertEqual(
            calls[0][1]["fields"]["TITLE"],
            "Подготовить смету",
        )
        self.assertEqual(calls[0][1]["fields"]["RESPONSIBLE_ID"], 9)
        self.assertEqual(calls[0][2], 8)

    def test_onpremise_task_method_returns_scalar_id(self):
        calls = []

        def transport(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {"result": 654}

        client = BitrixClient(
            "https://portal.example/rest/1/secret/",
            transport=transport,
        )
        result = client.task_add(
            fields={"TITLE": "Проверка", "RESPONSIBLE_ID": 9},
            method="task.item.add",
        )

        self.assertEqual(result.task_id, 654)
        self.assertEqual(
            calls[0][0],
            "https://portal.example/rest/1/secret/task.item.add",
        )
        self.assertEqual(calls[0][1]["fields"]["RESPONSIBLE_ID"], 9)

    def test_api_error_is_not_treated_as_success(self):
        client = BitrixClient(
            "https://portal.example/rest/1/secret",
            transport=lambda *_: {
                "error": "ERROR_CORE",
                "error_description": "Bad fields",
            },
        )

        with self.assertRaisesRegex(BitrixAPIError, "Bad fields"):
            client.tasks_task_add(fields={"TITLE": "x"})

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
