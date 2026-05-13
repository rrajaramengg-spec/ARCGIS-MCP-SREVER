"""Tests for plan validation — _sanitize_fields and validate_plan."""

import os
import sys

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.orchestrator.validation import _sanitize_fields, validate_plan


class TestSanitizeFields:
    """Tests for _sanitize_fields helper."""

    def test_strips_as_alias(self):
        assert _sanitize_fields(["NAME AS county_name", "POP"]) == ["NAME", "POP"]

    def test_case_insensitive_as(self):
        assert _sanitize_fields(["NAME as alias"]) == ["NAME"]
        assert _sanitize_fields(["NAME As alias"]) == ["NAME"]

    def test_clean_fields_unchanged(self):
        assert _sanitize_fields(["NAME", "POP", "OBJECTID"]) == ["NAME", "POP", "OBJECTID"]

    def test_empty_list(self):
        assert _sanitize_fields([]) == []

    def test_none_passthrough(self):
        assert _sanitize_fields(None) is None

    def test_whitespace_handling(self):
        assert _sanitize_fields(["  NAME  AS  alias  "]) == ["NAME"]

    def test_field_with_no_alias(self):
        assert _sanitize_fields(["OBJECTID"]) == ["OBJECTID"]


class TestValidatePlanSanitize:
    """Verify _sanitize_fields is wired into validate_plan."""

    def test_aliases_stripped_before_field_check(self):
        rag_layers = [
            {
                "layer_name": "COUNTY",
                "url": "https://example.com/county/0",
                "fields": [
                    {"field_name": "NAME"},
                    {"field_name": "POP"},
                ],
            },
        ]
        plan = {
            "action": "query",
            "query": [
                {
                    "layer": "COUNTY",
                    "layer_url": "https://example.com/county/0",
                    "fields": ["NAME AS county_name", "POP"],
                }
            ],
        }
        result = validate_plan(plan, rag_layers)
        node = result["query"][0]
        # Alias stripped, both fields match KB → both kept
        assert node["fields"] == ["NAME", "POP"]
