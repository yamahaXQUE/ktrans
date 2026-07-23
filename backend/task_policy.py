"""Closed task taxonomy derived from the approved task and QA documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal


POLICY_PATH = Path(__file__).parent / "prompt" / "task_policy.json"

ComplaintBasis = Literal[
    "explicit_complaint",
    "explicit_negative_feedback",
    "none",
]

TaskType = Literal[
    "service_fm",
    "bar_food",
    "product_quality_food_safety",
    "semi_finished_products",
    "ice_cream",
    "camera_recording",
    "receipt_search",
    "mobile_app_error",
    "mobile_app_wrong_information",
    "payment_check",
    "operator_quality_violation",
    "none",
]

ALLOWED_TASK_TYPES = frozenset(
    {
        "service_fm",
        "bar_food",
        "product_quality_food_safety",
        "semi_finished_products",
        "ice_cream",
        "camera_recording",
        "receipt_search",
        "mobile_app_error",
        "mobile_app_wrong_information",
        "payment_check",
        "operator_quality_violation",
        "none",
        "legacy",
    }
)


def load_task_policy() -> dict:
    with POLICY_PATH.open(encoding="utf-8") as policy_file:
        return json.load(policy_file)


def render_task_policy() -> str:
    return json.dumps(load_task_policy(), ensure_ascii=False, indent=2)


__all__ = [
    "ALLOWED_TASK_TYPES",
    "ComplaintBasis",
    "POLICY_PATH",
    "TaskType",
    "load_task_policy",
    "render_task_policy",
]
