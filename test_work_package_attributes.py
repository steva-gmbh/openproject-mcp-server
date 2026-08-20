#!/usr/bin/env python3
"""Unit tests for work package attribute tools and utilities."""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

# Provide dummy OpenProject config before importing server-backed tool modules
os.environ.setdefault("OPENPROJECT_URL", "https://example.test")
os.environ.setdefault("OPENPROJECT_API_KEY", "test-api-key")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_attribute_utilities():
    """Test attribute normalization, extraction, and payload building."""
    print("\n" + "=" * 70)
    print("Test 1: Attribute Utilities")
    print("=" * 70)

    from src.utils.work_package_attributes import (
        build_update_payload,
        collect_readable_attributes,
        extract_attribute_value,
        format_attribute_value,
        normalize_attribute_name,
        parse_attribute_filter,
    )

    assert normalize_attribute_name("assignee_id") == "assignee"
    assert normalize_attribute_name("responsible_id") == "responsible"
    assert normalize_attribute_name("custom_field_12") == "customField12"
    assert normalize_attribute_name("start_date") == "startDate"
    print("✅ normalize_attribute_name")

    assert parse_attribute_filter("assignee, responsible") == {"assignee", "responsible"}
    print("✅ parse_attribute_filter")

    work_package = {
        "id": 123,
        "subject": "Test task",
        "customField1": "Approved",
        "percentageDone": 40,
        "_links": {
            "assignee": {"href": "/api/v3/users/7", "title": "Alice"},
            "responsible": {"href": "/api/v3/users/5", "title": "Bob"},
            "customField3": {"href": "/api/v3/users/14", "title": "Reviewer"},
        },
    }

    schema = {
        "assignee": {
            "name": "Assignee",
            "type": "User",
            "location": "_links",
            "writable": True,
            "required": False,
        },
        "responsible": {
            "name": "Accountable",
            "type": "User",
            "location": "_links",
            "writable": True,
            "required": False,
        },
        "customField1": {
            "name": "Approval status",
            "type": "String",
            "writable": True,
            "required": False,
        },
        "customField3": {
            "name": "Reviewer",
            "type": "User",
            "location": "_links",
            "writable": True,
            "required": False,
        },
        "percentageDone": {
            "name": "% Complete",
            "type": "Integer",
            "writable": True,
            "required": False,
        },
    }

    assignee = extract_attribute_value(work_package, "assignee_id", schema["assignee"])
    assert assignee["id"] == 7
    assert assignee["title"] == "Alice"
    print("✅ extract_attribute_value for link field")

    assert extract_attribute_value(work_package, "customField1") == "Approved"
    print("✅ extract_attribute_value for scalar custom field")

    readable = collect_readable_attributes(work_package, schema=schema)
    assert readable["assignee"]["value"]["id"] == 7
    assert readable["customField1"]["value"] == "Approved"
    print("✅ collect_readable_attributes with schema")

    payload = build_update_payload(
        {
            "assignee_id": 9,
            "responsible_id": None,
            "customField1": "Rejected",
            "percentage_done": 75,
        },
        schema,
    )
    assert payload["percentageDone"] == 75
    assert payload["customField1"] == "Rejected"
    assert payload["_links"]["assignee"]["href"] == "/api/v3/users/9"
    assert payload["_links"]["responsible"]["href"] is None
    print("✅ build_update_payload with schema-aware links")

    assert format_attribute_value(None) == "null"
    assert "Alice" in format_attribute_value({"id": 7, "title": "Alice"})
    print("✅ format_attribute_value")

    from src.utils.work_package_attributes import (
        extract_custom_field_options,
        format_custom_field_values,
    )

    form_schema = {
        "customField4": {
            "name": "dot-Komponenten",
            "type": "[]CustomOption",
            "location": "_links",
            "writable": True,
            "required": False,
            "_embedded": {
                "allowedValues": [
                    {"id": 62, "value": "Core"},
                    {"id": 8, "value": "DMS"},
                    {"id": 9, "value": "EMS"},
                    {"id": 10, "value": "Formumat"},
                    {"id": 61, "value": "KI"},
                    {"id": 11, "value": "Orga"},
                    {"id": 12, "value": "PMS"},
                    {"id": 13, "value": "Report"},
                    {"id": 16, "value": "Templating"},
                    {"id": 18, "value": "Webdesigner"},
                    {"id": 54, "value": "Webformumat"},
                    {"id": 60, "value": "Work"},
                ]
            },
        },
        "customField9": {
            "name": "Reporter",
            "type": "User",
            "location": "_links",
            "writable": True,
            "required": False,
            "_embedded": {
                "allowedValues": [{"id": 6, "value": "Dirk Grappendorf"}]
            },
        },
        "customField1": {
            "name": "Angebotsnummer",
            "type": "String",
            "writable": True,
            "required": False,
        },
    }

    all_fields = extract_custom_field_options(form_schema)
    assert len(all_fields) == 3
    dot_field = next(item for item in all_fields if item["api_name"] == "customField4")
    assert dot_field["label"] == "dot-Komponenten"
    assert len(dot_field["options"]) == 12
    reporter_field = next(item for item in all_fields if item["api_name"] == "customField9")
    assert "options" not in reporter_field
    print("✅ extract_custom_field_options")

    filtered = extract_custom_field_options(form_schema, field_filter="dot-Komponenten")
    assert len(filtered) == 1
    assert filtered[0]["api_name"] == "customField4"
    filtered_api = extract_custom_field_options(form_schema, field_filter="customField4")
    assert len(filtered_api) == 1
    print("✅ extract_custom_field_options filter")

    formatted = format_custom_field_values(filtered, context="project #12")
    assert "dot-Komponenten" in formatted
    assert "**Formumat** (ID: 10)" in formatted
    assert "set_work_package_attributes" in formatted
    assert "Dirk Grappendorf" not in formatted
    print("✅ format_custom_field_values")

    return True


def test_pydantic_models():
    """Test SetWorkPackageAttributesInput validation."""
    print("\n" + "=" * 70)
    print("Test 2: Pydantic Model Validation")
    print("=" * 70)

    from src.tools.work_packages import SetWorkPackageAttributesInput

    valid = SetWorkPackageAttributesInput(
        work_package_id=123,
        attributes={"assignee_id": 7, "customField1": "Done"},
    )
    assert valid.work_package_id == 123
    assert valid.validate_form is True
    print("✅ valid SetWorkPackageAttributesInput")

    try:
        SetWorkPackageAttributesInput(work_package_id=0, attributes={"subject": "x"})
        print("❌ should reject invalid work_package_id")
        return False
    except Exception:
        print("✅ rejects invalid work_package_id")

    return True


async def test_tools_with_mocks():
    """Test attribute MCP tools with mocked client calls."""
    print("\n" + "=" * 70)
    print("Test 3: Tool Functionality (Mocked)")
    print("=" * 70)

    from src.tools.work_packages import (
        SetWorkPackageAttributesInput,
        get_work_package,
        get_work_package_attributes,
        list_custom_field_values,
        set_work_package_attributes,
    )

    get_work_package = get_work_package.fn
    get_work_package_attributes = get_work_package_attributes.fn
    set_work_package_attributes = set_work_package_attributes.fn
    list_custom_field_values = list_custom_field_values.fn

    sample_wp = {
        "id": 123,
        "subject": "Attribute test",
        "lockVersion": 4,
        "percentageDone": 10,
        "customField1": "Pending",
        "_links": {
            "assignee": {"href": "/api/v3/users/7", "title": "Alice"},
            "responsible": {"href": "/api/v3/users/5", "title": "Bob"},
        },
    }

    sample_schema = {
        "assignee": {
            "name": "Assignee",
            "type": "User",
            "location": "_links",
            "writable": True,
            "required": False,
        },
        "responsible": {
            "name": "Accountable",
            "type": "User",
            "location": "_links",
            "writable": True,
            "required": False,
        },
        "customField1": {
            "name": "Status",
            "type": "String",
            "writable": True,
            "required": False,
        },
    }

    print("\n[3.1] get_work_package")
    with patch("src.tools.work_packages.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_work_package = AsyncMock(return_value=sample_wp)
        mock_get_client.return_value = mock_client

        result = await get_work_package(work_package_id=123)
        assert "Work Package #123" in result
        assert "Alice" in result
        assert "Bob" in result
        print("✅ get_work_package")

    print("\n[3.2] get_work_package_attributes")
    with patch("src.tools.work_packages.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_work_package = AsyncMock(return_value=sample_wp)
        mock_client.get_work_package_schema = AsyncMock(return_value=sample_schema)
        mock_get_client.return_value = mock_client

        result = await get_work_package_attributes(
            work_package_id=123,
            attributes="assignee,responsible,customField1",
            include_schema=True,
        )
        assert "assignee" in result
        assert "responsible" in result
        assert "customField1" in result
        assert "writable" in result
        print("✅ get_work_package_attributes")

    print("\n[3.3] set_work_package_attributes")
    updated_wp = {
        **sample_wp,
        "lockVersion": 5,
        "percentageDone": 75,
        "customField1": "Approved",
        "_links": {
            "assignee": {"href": "/api/v3/users/9", "title": "Carol"},
            "responsible": {"href": "/api/v3/users/5", "title": "Bob"},
        },
    }

    with patch("src.tools.work_packages.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.update_work_package_attributes = AsyncMock(return_value=updated_wp)
        mock_client.get_work_package_schema = AsyncMock(return_value=sample_schema)
        mock_get_client.return_value = mock_client

        result = await set_work_package_attributes(
            SetWorkPackageAttributesInput(
                work_package_id=123,
                attributes={
                    "assignee_id": 9,
                    "customField1": "Approved",
                    "percentage_done": 75,
                },
            )
        )
        assert "updated successfully" in result
        assert "Carol" in result
        assert "Approved" in result
        print("✅ set_work_package_attributes")

    print("\n[3.4] validation error handling")
    with patch("src.tools.work_packages.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.update_work_package_attributes = AsyncMock(
            side_effect=Exception('Validation failed: {"assignee": "is invalid"}')
        )
        mock_get_client.return_value = mock_client

        result = await set_work_package_attributes(
            SetWorkPackageAttributesInput(
                work_package_id=123,
                attributes={"assignee_id": 999},
            )
        )
        assert "❌" in result
        assert "Validation failed" in result
        print("✅ validation error handling")

    form_schema = {
        "customField4": {
            "name": "dot-Komponenten",
            "type": "[]CustomOption",
            "location": "_links",
            "writable": True,
            "required": False,
            "_embedded": {
                "allowedValues": [
                    {"id": 62, "value": "Core"},
                    {"id": 10, "value": "Formumat"},
                ]
            },
        }
    }

    print("\n[3.5] list_custom_field_values via work_package_id")
    with patch("src.tools.work_packages.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_work_package_form_schema = AsyncMock(return_value=form_schema)
        mock_get_client.return_value = mock_client

        result = await list_custom_field_values(
            work_package_id=991,
            field="dot-Komponenten",
        )
        mock_client.get_work_package_form_schema.assert_awaited_once_with(991)
        assert "dot-Komponenten" in result
        assert "**Formumat** (ID: 10)" in result
        print("✅ list_custom_field_values work package path")

    print("\n[3.6] list_custom_field_values via project_id")
    with patch("src.tools.work_packages.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_project_work_package_form = AsyncMock(
            return_value={"_embedded": {"schema": form_schema}}
        )
        mock_get_client.return_value = mock_client

        result = await list_custom_field_values(
            project_id=12,
            type_id=11,
            field="customField4",
        )
        mock_client.get_project_work_package_form.assert_awaited_once_with(12, 11)
        assert "project #12, type #11" in result
        assert "**Core** (ID: 62)" in result
        print("✅ list_custom_field_values project path")

    print("\n[3.7] list_custom_field_values validation")
    result = await list_custom_field_values()
    assert "❌" in result
    assert "Provide either work_package_id or project_id" in result

    result = await list_custom_field_values(work_package_id=991, project_id=12)
    assert "❌" in result
    assert "not both" in result

    result = await list_custom_field_values(work_package_id=991, type_id=11)
    assert "❌" in result
    assert "type_id can only be used with project_id" in result

    with patch("src.tools.work_packages.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_work_package_form_schema = AsyncMock(return_value=form_schema)
        mock_get_client.return_value = mock_client

        result = await list_custom_field_values(
            work_package_id=991,
            field="missing-field",
        )
        assert "❌" in result
        assert "No custom field matching" in result
    print("✅ list_custom_field_values validation")

    return True


async def test_client_attribute_update_flow():
    """Test client optimistic locking and form validation flow."""
    print("\n" + "=" * 70)
    print("Test 4: Client Attribute Update Flow")
    print("=" * 70)

    from src.client import OpenProjectClient

    client = OpenProjectClient("https://example.test", "secret-key")

    current_wp = {"id": 123, "lockVersion": 8, "_links": {"schema": {"href": "/api/v3/work_packages/schemas/1-2"}}}
    schema = {
        "assignee": {"type": "User", "location": "_links", "writable": True},
        "subject": {"type": "String", "writable": True},
    }
    form_result = {
        "_embedded": {
            "validationErrors": {},
            "payload": {
                "subject": "Updated",
                "_links": {"assignee": {"href": "/api/v3/users/4"}},
            },
        }
    }
    patched_wp = {"id": 123, "subject": "Updated", "lockVersion": 9}

    with patch.object(client, "get_work_package", AsyncMock(return_value=current_wp)), patch.object(
        client, "get_work_package_schema", AsyncMock(return_value=schema)
    ), patch.object(client, "validate_work_package_form", AsyncMock(return_value=form_result)), patch.object(
        client, "patch_work_package", AsyncMock(return_value=patched_wp)
    ) as mock_patch:
        result = await client.update_work_package_attributes(
            123,
            {"subject": "Updated", "assignee_id": 4},
            validate=True,
            validate_custom_fields=True,
        )

        assert result["subject"] == "Updated"
        patch_payload = mock_patch.await_args.args[1]
        assert patch_payload["lockVersion"] == 8
        assert patch_payload["_meta"] == {"validateCustomFields": True}
        assert patch_payload["_links"]["assignee"]["href"] == "/api/v3/users/4"
        print("✅ client update flow uses lockVersion and validated payload")

    with patch.object(client, "get_work_package", AsyncMock(return_value=current_wp)), patch.object(
        client, "get_work_package_schema", AsyncMock(return_value=schema)
    ), patch.object(
        client,
        "validate_work_package_form",
        AsyncMock(
            return_value={"_embedded": {"validationErrors": {"assignee": "is invalid"}}}
        ),
    ), patch.object(client, "patch_work_package", AsyncMock()) as mock_patch:
        try:
            await client.update_work_package_attributes(
                123,
                {"assignee_id": 999},
                validate=True,
            )
            print("❌ should raise on validation errors")
            return False
        except Exception as exc:
            assert "Validation failed" in str(exc)
            mock_patch.assert_not_called()
            print("✅ client rejects invalid form payloads")

    form_schema = {"customField4": {"name": "dot-Komponenten", "type": "[]CustomOption"}}
    form_result = {"_embedded": {"schema": form_schema}}

    with patch.object(client, "get_work_package", AsyncMock(return_value=current_wp)), patch.object(
        client, "validate_work_package_form", AsyncMock(return_value=form_result)
    ) as mock_form:
        schema = await client.get_work_package_form_schema(123)
        assert schema == form_schema
        mock_form.assert_awaited_once_with(123, {"lockVersion": 8})
        print("✅ get_work_package_form_schema sends lockVersion")

    with patch.object(
        client, "_request", AsyncMock(return_value={"_embedded": {"schema": form_schema}})
    ) as mock_request:
        await client.get_project_work_package_form(12, 11)
        mock_request.assert_awaited_once_with(
            "POST",
            "/projects/12/work_packages/form",
            {"_links": {"type": {"href": "/api/v3/types/11"}}},
        )
        print("✅ get_project_work_package_form posts type link")

    return True


def run_all_tests():
    print("=" * 70)
    print("WORK PACKAGE ATTRIBUTE TEST SUITE")
    print("=" * 70)

    results = [
        ("Attribute Utilities", test_attribute_utilities()),
        ("Pydantic Validation", test_pydantic_models()),
        ("Tool Functionality", asyncio.run(test_tools_with_mocks())),
        ("Client Update Flow", asyncio.run(test_client_attribute_update_flow())),
    ]

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"{name}: {'✅ PASSED' if ok else '❌ FAILED'}")

    print("\n" + "=" * 70)
    print(f"Total: {passed}/{len(results)} test suites passed")
    print("=" * 70)
    return all(ok for _, ok in results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
