import os
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
from uuid import UUID

from backend.bitrix_auth import validate_current_user
from backend.analytics_export import build_complaints_workbook
from backend.main import app
from backend.schemas import (
    ComplaintAnalyticsDto,
    ComplaintDepartmentStatDto,
    SessionUserDto,
    SourceCallDto,
)
from backend.sync_bitrix import mask_phone
from backend.task_delivery import TaskDeliveryConfig
from bitrix import BitrixResponse


class FrontendContractTests(unittest.TestCase):
    def test_dtos_serialize_with_frontend_camel_case(self):
        operator_id = UUID("00000000-0000-0000-0000-000000000001")
        call = SourceCallDto(
            id=UUID("00000000-0000-0000-0000-000000000002"),
            statistic_id=99,
            operator_id=operator_id,
            operator_name="Иван Петров",
            direction="inbound",
            duration_seconds=30,
            started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            phone_masked="+996 XX 1234",
            failed_code=None,
            transcript="Текст",
            conversation_title="Уточнение заказа",
            analysis_status="completed",
            analysis_requested=False,
            analysis_error=None,
        )

        payload = call.model_dump(mode="json")

        self.assertEqual(payload["statisticId"], 99)
        self.assertEqual(payload["operatorId"], str(operator_id))
        self.assertEqual(payload["conversationTitle"], "Уточнение заказа")
        self.assertNotIn("statistic_id", payload)

    def test_openapi_contains_frontend_routes(self):
        paths = app.openapi()["paths"]

        self.assertIn("/api/candidates", paths)
        self.assertIn("/api/candidates/{candidate_id}/confirm", paths)
        self.assertIn("/api/emulation/users", paths)
        self.assertIn("/api/emulation/session", paths)
        self.assertIn("/api/calls/{call_id}/analysis", paths)
        self.assertIn("/api/calls/{call_id}", paths)
        self.assertIn("/api/operators/{operator_id}/calls", paths)
        self.assertIn("/api/analytics/complaints", paths)
        self.assertIn("/api/analytics/complaints.xlsx", paths)
        query_names = {
            parameter["name"]
            for parameter in paths["/api/candidates"]["get"]["parameters"]
            if parameter["in"] == "query"
        }
        self.assertIn("operatorId", query_names)

    def test_session_role_contract(self):
        user = SessionUserDto(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            display_name="Регина Лазаревич",
            work_position="Супервайзер",
            initials="РЛ",
            role="supervisor",
            department_ids=[82],
            source="bitrix",
        )

        self.assertEqual(user.model_dump(mode="json")["departmentIds"], [82])

    def test_excel_export_contains_complaints_and_analytics(self):
        from openpyxl import load_workbook

        analytics = ComplaintAnalyticsDto(
            total_complaints=1,
            generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            departments=[
                ComplaintDepartmentStatDto(
                    department="Поддержка",
                    count=1,
                    share_percent=100,
                )
            ],
        )
        content = build_complaints_workbook(
            [
                {
                    "sent_at": datetime(2026, 7, 23, tzinfo=timezone.utc),
                    "bitrix_item_id": "321",
                    "operator_name": "Иван Петров",
                    "department": "Поддержка",
                    "task_type": "service_fm",
                    "complaint_basis": "explicit_complaint",
                    "complaint_evidence": "Клиент явно пожаловался.",
                    "title": "Разобрать жалобу",
                    "description": "Проверить обслуживание.",
                    "priority": 3,
                    "call_id": UUID("00000000-0000-0000-0000-000000000003"),
                }
            ],
            analytics,
        )

        self.assertTrue(content.startswith(b"PK"))
        workbook = load_workbook(BytesIO(content))
        self.assertEqual(workbook.sheetnames, ["Жалобы", "Аналитика"])
        self.assertEqual(workbook["Жалобы"]["C2"].value, "Иван Петров")
        self.assertEqual(workbook["Аналитика"]["A2"].value, "Поддержка")


class ConfigurationTests(unittest.TestCase):
    def test_task_mapping_is_configuration_driven(self):
        environment = {
            "BITRIX_TASK_ENTITY_TYPE_ID": "1034",
            "BITRIX_TASK_FIELD_MAPPING": (
                '{"title":"title","description":"ufCrmDescription"}'
            ),
            "BITRIX_TASK_CONSTANT_FIELDS": '{"opened":true}',
        }
        with patch.dict(os.environ, environment, clear=False):
            config = TaskDeliveryConfig.from_env()

        self.assertEqual(config.entity_type_id, 1034)
        self.assertEqual(config.mapper.field_mapping["description"], "ufCrmDescription")
        self.assertTrue(config.mapper.constant_fields["opened"])

    def test_phone_is_masked_before_frontend(self):
        masked = mask_phone("+996 555 12 34 56")

        self.assertNotIn("555123456", masked.replace(" ", ""))
        self.assertTrue(masked.endswith("3456"))

    def test_iframe_user_is_verified_server_side(self):
        class FakeClient:
            def __init__(self, base_url, **kwargs):
                self.base_url = base_url
                self.kwargs = kwargs

            def call(self, method, params):
                self.method = method
                self.params = params
                return BitrixResponse(
                    result={"ID": "10"},
                    total=None,
                    next=None,
                    raw_response={"result": {"ID": "10"}},
                )

        with (
            patch("backend.bitrix_auth.BitrixClient", FakeClient),
            patch.dict(
                os.environ,
                {
                    "BITRIX_ALLOWED_PORTALS": "bitrix.kulikov.com",
                    "BITRIX_TLS_COMPATIBILITY": "true",
                },
                clear=False,
            ),
        ):
            user_id = validate_current_user(
                domain="bitrix.kulikov.com",
                access_token="temporary-token",
            )

        self.assertEqual(user_id, 10)

    def test_iframe_domain_allowlist_blocks_ssrf(self):
        with patch.dict(
            os.environ,
            {"BITRIX_ALLOWED_PORTALS": "bitrix.kulikov.com"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "not allowed"):
                validate_current_user(
                    domain="localhost",
                    access_token="temporary-token",
                )


if __name__ == "__main__":
    unittest.main()
