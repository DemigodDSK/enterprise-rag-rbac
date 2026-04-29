"""Loads rbac_config.json and exposes Role / Classification enums + permission matrix."""
import json
import os
from enum import Enum


def _resolve_config_path() -> str:
    explicit = os.environ.get("RBAC_CONFIG_PATH")
    if explicit and os.path.exists(explicit):
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "config", "rbac_config.json"),
        os.path.join(here, "..", "..", "config", "rbac_config.json"),
        os.path.join(here, "..", "..", "..", "config", "rbac_config.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return candidates[0]


RBAC_CONFIG_PATH = _resolve_config_path()

with open(RBAC_CONFIG_PATH, "r") as f:
    RBAC_CONFIG = json.load(f)

Role = Enum("Role", {k.upper(): k for k in RBAC_CONFIG["roles"]})
Classification = Enum("Classification", RBAC_CONFIG["classification_levels"])

# Maps both 'INTERNAL' and 'Internal' → enum value
CLS_MAP = {}
for name in RBAC_CONFIG["classification_levels"]:
    CLS_MAP[name] = Classification[name]
    CLS_MAP[name.title()] = Classification[name]

ROLE_PERMISSIONS = {}
ALL_CATEGORIES: set = set()
for role_name, perms in RBAC_CONFIG["roles"].items():
    role_enum = Role[role_name.upper()]
    ROLE_PERMISSIONS[role_enum] = {
        "categories": perms["categories"],
        "max_classification": Classification[perms["max_classification"]],
        "can_view_audit_log": perms["can_view_audit_log"],
        "can_manage_users": perms["can_manage_users"],
    }
    ALL_CATEGORIES.update(perms["categories"])
ALL_CATEGORIES = sorted(ALL_CATEGORIES)

CONFIDENTIAL_DOCS = set(RBAC_CONFIG.get("confidential_documents", []))
