"""Work package attribute parsing, formatting, and API payload building."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Standard HAL link fields and their API resource paths
LINK_FIELD_PATHS: Dict[str, str] = {
    "assignee": "/api/v3/users/{id}",
    "responsible": "/api/v3/users/{id}",
    "status": "/api/v3/statuses/{id}",
    "priority": "/api/v3/priorities/{id}",
    "type": "/api/v3/types/{id}",
    "project": "/api/v3/projects/{id}",
    "version": "/api/v3/versions/{id}",
    "category": "/api/v3/categories/{id}",
    "parent": "/api/v3/work_packages/{id}",
}

# snake_case / *_id aliases -> canonical link field name
LINK_FIELD_ALIASES: Dict[str, str] = {
    "assignee_id": "assignee",
    "responsible_id": "responsible",
    "status_id": "status",
    "priority_id": "priority",
    "type_id": "type",
    "project_id": "project",
    "version_id": "version",
    "category_id": "category",
    "parent_id": "parent",
}

# snake_case aliases -> camelCase API property names
SCALAR_FIELD_ALIASES: Dict[str, str] = {
    "start_date": "startDate",
    "due_date": "dueDate",
    "percentage_done": "percentageDone",
    "estimated_time": "estimatedTime",
    "remaining_time": "remainingTime",
    "schedule_manually": "scheduleManually",
    "ignore_non_working_days": "ignoreNonWorkingDays",
    "story_points": "storyPoints",
}

# Schema property types stored as HAL links
LINK_PROPERTY_TYPES: Set[str] = {
    "User",
    "Version",
    "CustomOption",
    "Category",
    "Priority",
    "Status",
    "Type",
    "Project",
    "WorkPackage",
}

CUSTOM_FIELD_PATTERN = re.compile(r"^customField(\d+)$", re.IGNORECASE)
RESERVED_KEYS = {"lockVersion", "validate", "validate_custom_fields"}


def normalize_attribute_name(name: str) -> str:
    """Normalize user-facing attribute names to OpenProject API names."""
    if not name:
        return name

    key = name.strip()
    lower = key.lower()

    if lower in LINK_FIELD_ALIASES:
        return LINK_FIELD_ALIASES[lower]

    if lower in SCALAR_FIELD_ALIASES:
        return SCALAR_FIELD_ALIASES[lower]

    cf_match = CUSTOM_FIELD_PATTERN.match(key)
    if cf_match:
        return f"customField{cf_match.group(1)}"

    cf_snake = re.match(r"^custom_field_(\d+)$", lower)
    if cf_snake:
        return f"customField{cf_snake.group(1)}"

    if "_" in key and key == lower:
        parts = key.split("_")
        return parts[0] + "".join(part.capitalize() for part in parts[1:])

    return key


def parse_attribute_filter(attributes: Optional[str]) -> Optional[Set[str]]:
    """Parse comma-separated attribute filter into normalized names."""
    if not attributes or not attributes.strip():
        return None

    names = {
        normalize_attribute_name(part.strip())
        for part in attributes.split(",")
        if part.strip()
    }
    return names or None


def extract_id_from_href(href: Optional[str]) -> Optional[int]:
    """Extract numeric ID from an OpenProject HAL href."""
    if not href:
        return None

    match = re.search(r"/(\d+)(?:/|$)", href)
    if match:
        return int(match.group(1))
    return None


def format_link_value(link: Any) -> Any:
    """Convert a HAL link object into a readable value."""
    if link is None:
        return None

    if isinstance(link, list):
        return [format_link_value(item) for item in link]

    if not isinstance(link, dict):
        return link

    href = link.get("href")
    if href is None:
        return None

    entity_id = extract_id_from_href(href)
    title = link.get("title")
    if entity_id is not None:
        return {"id": entity_id, "title": title, "href": href}
    return title or href


def get_schema_property(
    schema: Optional[Dict[str, Any]], attribute_name: str
) -> Optional[Dict[str, Any]]:
    """Look up a schema property by normalized attribute name."""
    if not schema:
        return None

    normalized = normalize_attribute_name(attribute_name)
    if normalized in schema:
        return schema[normalized]

    for prop_name, prop_def in schema.items():
        if prop_name.startswith("_"):
            continue
        if normalize_attribute_name(prop_name) == normalized:
            return prop_def

    return None


def extract_attribute_value(
    work_package: Dict[str, Any],
    attribute_name: str,
    schema_prop: Optional[Dict[str, Any]] = None,
) -> Any:
    """Extract a readable attribute value from a work package response."""
    api_name = normalize_attribute_name(attribute_name)
    links = work_package.get("_links", {})

    location = schema_prop.get("location") if schema_prop else None
    prefer_links = location == "_links" or api_name in LINK_FIELD_PATHS

    if prefer_links and api_name in links:
        return format_link_value(links.get(api_name))

    if api_name in work_package and api_name not in {"_links", "_embedded", "_type"}:
        value = work_package[api_name]
        if api_name == "description" and isinstance(value, dict):
            return value.get("raw", value)
        return value

    if api_name in links:
        return format_link_value(links.get(api_name))

    return None


def is_multi_value_field(field_type: Optional[str]) -> bool:
    """Return True when a schema field type stores multiple link values."""
    return bool(field_type and field_type.startswith("[]"))


def base_field_type(field_type: Optional[str]) -> Optional[str]:
    """Strip the OpenProject array prefix from a schema field type."""
    if field_type and field_type.startswith("[]"):
        return field_type[2:]
    return field_type


def normalize_multi_value_input(value: Any) -> List[Any]:
    """Coerce agent-friendly multi-value input into a list of items."""
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if "," in stripped:
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return [stripped]

    return [value]


def resolve_custom_option_item(
    value: Any, allowed_values: List[Dict[str, Any]]
) -> Any:
    """Resolve a custom option input to an id, href dict, or pass-through value."""
    if isinstance(value, dict):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("Empty custom option value")

        if stripped.startswith("/") or stripped.startswith("/api/v3"):
            return stripped
        if stripped.isdigit():
            return int(stripped)

        for option in allowed_values:
            option_value = option.get("value")
            if option_value is not None and option_value.casefold() == stripped.casefold():
                return option.get("id")

        raise ValueError(f"Unknown custom option value: {value}")

    raise ValueError(f"Invalid custom option value: {value!r}")


def prepare_link_item_value(
    field_name: str,
    item: Any,
    schema_prop: Optional[Dict[str, Any]] = None,
) -> Any:
    """Validate one item in a multi-value link field before href resolution."""
    if item is None:
        raise ValueError(f"Invalid link value for {field_name}: null list item")
    return item


def resolve_link_href(
    field_name: str,
    value: Any,
    schema_prop: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve a HAL href for a link-backed attribute."""
    if value is None:
        return None

    if isinstance(value, dict):
        if "href" in value:
            href = value["href"]
            if href is None:
                return None
            if href.startswith("/api/v3"):
                return href
            if href.startswith("/"):
                return f"/api/v3{href}"
            return f"/api/v3/{href.lstrip('/')}"

        if "id" in value:
            value = value["id"]

    if isinstance(value, str):
        if value.startswith("/api/v3"):
            return value
        if value.startswith("/"):
            return f"/api/v3{value}"
        if value.isdigit():
            value = int(value)

    if isinstance(value, bool):
        raise ValueError(f"Invalid link value for {field_name}: boolean")

    if not isinstance(value, int):
        raise ValueError(
            f"Invalid link value for {field_name}: expected id, href, or null"
        )

    if field_name in LINK_FIELD_PATHS:
        return LINK_FIELD_PATHS[field_name].format(id=value)

    prop_type = schema_prop.get("type") if schema_prop else None
    base_type = base_field_type(prop_type)
    type_paths = {
        "User": "/api/v3/users/{id}",
        "Version": "/api/v3/versions/{id}",
        "CustomOption": "/api/v3/custom_options/{id}",
        "Category": "/api/v3/categories/{id}",
        "Priority": "/api/v3/priorities/{id}",
        "Status": "/api/v3/statuses/{id}",
        "Type": "/api/v3/types/{id}",
        "Project": "/api/v3/projects/{id}",
        "WorkPackage": "/api/v3/work_packages/{id}",
    }

    if base_type in type_paths:
        return type_paths[base_type].format(id=value)

    if field_name.startswith("customField"):
        return f"/api/v3/custom_options/{value}"

    raise ValueError(
        f"Cannot resolve link path for '{field_name}'. "
        "Provide an explicit href or use get_work_package_attributes with include_schema=true."
    )


def build_single_link_payload(
    field_name: str,
    value: Any,
    schema_prop: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a single HAL link object for the PATCH payload."""
    if is_custom_option_field(base_field_type(schema_prop.get("type") if schema_prop else None)):
        if schema_prop and not isinstance(value, dict):
            allowed_values = parse_allowed_values(schema_prop)
            if allowed_values:
                value = resolve_custom_option_item(value, allowed_values)

    href = resolve_link_href(field_name, value, schema_prop)
    if href is None:
        return {"href": None}
    return {"href": href}


def build_link_payload(
    field_name: str,
    value: Any,
    schema_prop: Optional[Dict[str, Any]] = None,
) -> Any:
    """Build HAL link object(s) for the PATCH payload."""
    field_type = schema_prop.get("type") if schema_prop else None

    if is_multi_value_field(field_type):
        items = normalize_multi_value_input(value)
        if not items:
            return []

        links: List[Dict[str, Any]] = []
        for item in items:
            prepared = prepare_link_item_value(field_name, item, schema_prop)
            link = build_single_link_payload(field_name, prepared, schema_prop)
            if link.get("href") is not None:
                links.append(link)
        return links

    return build_single_link_payload(field_name, value, schema_prop)


def attribute_uses_links(
    attribute_name: str,
    schema_prop: Optional[Dict[str, Any]] = None,
) -> bool:
    """Determine whether an attribute is stored in _links."""
    api_name = normalize_attribute_name(attribute_name)

    if api_name in LINK_FIELD_PATHS:
        return True

    if not schema_prop:
        return False

    if schema_prop.get("location") == "_links":
        return True

    return schema_prop.get("type") in LINK_PROPERTY_TYPES


def build_update_payload(
    attributes: Dict[str, Any],
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an OpenProject work package PATCH payload from attribute values."""
    if not attributes:
        raise ValueError("No attributes provided")

    payload: Dict[str, Any] = {}
    links: Dict[str, Any] = {}

    for raw_key, raw_value in attributes.items():
        if raw_key in RESERVED_KEYS:
            continue

        api_name = normalize_attribute_name(raw_key)
        if api_name in RESERVED_KEYS:
            continue

        schema_prop = get_schema_property(schema, api_name)

        if api_name == "description":
            if raw_value is None:
                payload["description"] = {"raw": ""}
            elif isinstance(raw_value, dict):
                payload["description"] = raw_value
            else:
                payload["description"] = {"raw": str(raw_value)}
            continue

        if attribute_uses_links(api_name, schema_prop):
            links[api_name] = build_link_payload(api_name, raw_value, schema_prop)
            continue

        payload[api_name] = raw_value

    if links:
        payload["_links"] = links

    return payload


def collect_readable_attributes(
    work_package: Dict[str, Any],
    schema: Optional[Dict[str, Any]] = None,
    attribute_filter: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Collect readable attribute values, optionally filtered and annotated with schema."""
    results: Dict[str, Dict[str, Any]] = {}

    if schema:
        for prop_name, prop_def in schema.items():
            if prop_name.startswith("_"):
                continue
            normalized = normalize_attribute_name(prop_name)
            if attribute_filter and normalized not in attribute_filter:
                continue

            results[normalized] = {
                "name": prop_def.get("name", normalized),
                "type": prop_def.get("type"),
                "writable": prop_def.get("writable", False),
                "required": prop_def.get("required", False),
                "location": prop_def.get("location"),
                "value": extract_attribute_value(work_package, normalized, prop_def),
            }
        return results

    candidate_names = set(LINK_FIELD_PATHS.keys())
    candidate_names.update(SCALAR_FIELD_ALIASES.values())
    candidate_names.update(
        {
            "subject",
            "description",
            "startDate",
            "dueDate",
            "date",
            "percentageDone",
            "estimatedTime",
            "duration",
            "scheduleManually",
            "ignoreNonWorkingDays",
            "storyPoints",
            "lockVersion",
            "createdAt",
            "updatedAt",
        }
    )

    for key in work_package:
        if CUSTOM_FIELD_PATTERN.match(key):
            candidate_names.add(key)

    for link_name in work_package.get("_links", {}):
        if CUSTOM_FIELD_PATTERN.match(link_name):
            candidate_names.add(link_name)

    for name in sorted(candidate_names):
        if attribute_filter and name not in attribute_filter:
            continue
        value = extract_attribute_value(work_package, name)
        if value is not None:
            results[name] = {"value": value}

    return results


def format_attribute_value(value: Any) -> str:
    """Format an attribute value for human-readable output."""
    if value is None:
        return "null"

    if isinstance(value, dict):
        if "id" in value:
            title = value.get("title")
            if title:
                return f"{title} (ID: {value['id']})"
            return f"ID: {value['id']}"
        if "raw" in value:
            return str(value["raw"])
        return str(value)

    if isinstance(value, list):
        return ", ".join(format_attribute_value(item) for item in value)

    return str(value)


def format_work_package_attributes(
    work_package: Dict[str, Any],
    attributes: Dict[str, Dict[str, Any]],
    include_schema: bool = False,
) -> str:
    """Format work package attributes for MCP tool output."""
    wp_id = work_package.get("id", "N/A")
    subject = work_package.get("subject", "No title")
    lock_version = work_package.get("lockVersion")

    text = f"Work Package #{wp_id}: {subject}\n\n"
    if lock_version is not None:
        text += f"lockVersion: {lock_version}\n\n"

    if not attributes:
        text += "No matching attributes found."
        return text

    text += f"Attributes ({len(attributes)}):\n\n"
    for attr_name, meta in attributes.items():
        value = meta.get("value")
        line = f"- **{attr_name}**: {format_attribute_value(value)}"

        if include_schema:
            details = []
            display_name = meta.get("name")
            if display_name and display_name != attr_name:
                details.append(f"label={display_name}")
            if meta.get("type"):
                details.append(f"type={meta['type']}")
            if meta.get("location"):
                details.append(f"location={meta['location']}")
            details.append("writable" if meta.get("writable") else "read-only")
            if meta.get("required"):
                details.append("required")
            if details:
                line += f" ({', '.join(details)})"

        text += line + "\n"

    return text


def format_validation_errors(validation_errors: Dict[str, Any]) -> str:
    """Format OpenProject form validation errors."""
    if not validation_errors:
        return ""

    lines = ["Validation errors:"]
    for field, message in validation_errors.items():
        if isinstance(message, dict):
            message = message.get("message", str(message))
        lines.append(f"- {field}: {message}")
    return "\n".join(lines)


def is_custom_option_field(field_type: Optional[str]) -> bool:
    """Return True when a schema field type stores CustomOption values."""
    return field_type in {"CustomOption", "[]CustomOption"}


def matches_custom_field_filter(
    prop_name: str, prop_def: Dict[str, Any], field_filter: Optional[str]
) -> bool:
    """Return True when a custom field matches an optional filter."""
    if not field_filter:
        return True

    normalized_filter = normalize_attribute_name(field_filter)
    normalized_name = normalize_attribute_name(prop_name)
    if normalized_filter == normalized_name:
        return True

    label = prop_def.get("name", "")
    return field_filter.strip().casefold() == label.casefold()


def parse_allowed_values(prop_def: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract allowed custom-field option values from a form schema property."""
    options: List[Dict[str, Any]] = []

    embedded_values = prop_def.get("_embedded", {}).get("allowedValues")
    if isinstance(embedded_values, list):
        for item in embedded_values:
            if not isinstance(item, dict):
                continue
            options.append(
                {
                    "id": item.get("id"),
                    "value": item.get("value") or item.get("title"),
                }
            )
        return options

    allowed_links = prop_def.get("_links", {}).get("allowedValues")
    if isinstance(allowed_links, list):
        for link in allowed_links:
            if not isinstance(link, dict):
                continue
            href = link.get("href", "")
            options.append(
                {
                    "id": extract_id_from_href(href),
                    "value": link.get("title"),
                }
            )
    elif isinstance(allowed_links, dict):
        href = allowed_links.get("href", "")
        options.append(
            {
                "id": extract_id_from_href(href),
                "value": allowed_links.get("title"),
            }
        )

    return options


def extract_custom_field_options(
    schema: Dict[str, Any], field_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Collect custom-field metadata and allowed values from a form schema."""
    fields: List[Dict[str, Any]] = []

    for prop_name, prop_def in schema.items():
        if prop_name.startswith("_") or not CUSTOM_FIELD_PATTERN.match(prop_name):
            continue
        if not isinstance(prop_def, dict):
            continue
        if not matches_custom_field_filter(prop_name, prop_def, field_filter):
            continue

        field_type = prop_def.get("type")
        field_info: Dict[str, Any] = {
            "api_name": normalize_attribute_name(prop_name),
            "label": prop_def.get("name", prop_name),
            "type": field_type,
            "writable": prop_def.get("writable", False),
            "required": prop_def.get("required", False),
        }

        if is_custom_option_field(field_type):
            field_info["options"] = parse_allowed_values(prop_def)

        fields.append(field_info)

    return sorted(fields, key=lambda item: item["api_name"])


def format_custom_field_values(
    fields: List[Dict[str, Any]], context: str = ""
) -> str:
    """Format custom-field allowed values for MCP tool output."""
    if not fields:
        return "No matching custom fields found."

    text = "✅ **Custom Field Values"
    if context:
        text += f" ({context})"
    text += ":**\n\n"

    for field in fields:
        label = field.get("label", field.get("api_name"))
        api_name = field.get("api_name")
        field_type = field.get("type", "Unknown")

        text += f"### {label}\n"
        text += f"- **API name**: `{api_name}`\n"
        text += f"- **Type**: {field_type}\n"
        text += f"- **Writable**: {'yes' if field.get('writable') else 'no'}"
        if field.get("required"):
            text += " | **Required**: yes"
        text += "\n"

        options = field.get("options")
        if options:
            text += f"\n**Allowed values ({len(options)}):**\n"
            for option in options:
                text += f"- **{option.get('value')}** (ID: {option.get('id')})\n"
        elif is_custom_option_field(field_type):
            text += "\nNo allowed values returned for this field.\n"
        else:
            text += f"\n*Allowed values not listed for type `{field_type}`.*\n"

        text += "\n"

    text += (
        "Use option IDs or titles with `set_work_package_attributes`. "
        "For multi-select fields (`[]CustomOption`), pass an array such as "
        "`[10, 62]` or `[\"Formumat\", \"Core\"]`. Use `[]` or `null` to clear.\n"
    )
    return text
