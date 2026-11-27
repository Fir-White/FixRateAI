"""Operational MVP rights; stored membership roles are never rewritten."""
import os

ENGINEERING_ROLES = frozenset(("engineer", "chief_engineer"))
MVP_ENGINEERING = frozenset(("engineering_workspace", "order_table", "review_report", "edit_plan",
                             "edit_equipment", "edit_service", "prepare_catalog"))
GATES = {
    "engineering_workspace": ("chief_engineer",),
    "order_table": ("chief_engineer",),
    "review_report": ("chief_engineer",),
    "edit_plan": ("chief_engineer", "dispatcher", "admin"),
    "edit_equipment": ("chief_engineer", "admin"),
    "edit_service": ("chief_engineer", "admin"),
    "prepare_catalog": ("chief_engineer", "admin"),
    "edit_source_workbook": ("chief_engineer",),
    "site_access": ("chief_engineer", "admin"),
    "approve_exception": ("chief_engineer",),
}

TOOL_PERMISSIONS = {
    **dict.fromkeys(("order_table_read", "order_table_bindings", "order_table_preview",
                     "order_table_apply", "order_table_export"), "order_table"),
    "report_review": "review_report",
    **dict.fromkeys(("portfolio_save", "draft_policy_edit", "draft_place", "draft_undo_preview", "draft_undo",
                     "draft_save", "draft_split", "optimization_start", "optimization_apply", "optimization_cancel",
                     "publication_prepare"), "edit_plan"),
    **dict.fromkeys(("equipment_create", "equipment_edit", "equipment_retire", "component_install",
                     "component_edit", "component_replace"), "edit_equipment"),
    **dict.fromkeys(("regulation_create", "regulation_edit"), "edit_service"),
    **dict.fromkeys(("catalog_import_preview", "catalog_import", "catalog_decision"), "prepare_catalog"),
    **dict.fromkeys(("workbook_upload", "workbook_from_catalog", "workbook_version_from_file", "workbook_catalog",
                     "workbook_issued_orders", "workbook_order_rows", "workbook_order_preview", "workbook_order_apply"),
                    "edit_source_workbook"),
}


def permission_profile():
    profile = os.environ.get("FIXRATE_PERMISSION_PROFILE", "legacy")
    if profile not in ("legacy", "mvp"):
        raise ValueError("FIXRATE_PERMISSION_PROFILE must be legacy or mvp")
    return profile


def has_role(role, roles, *, exact=False, permission=None):
    """Keep compatibility by default; grant MVP extras only by explicit gate."""
    if permission == "edit_source_workbook":
        return role in GATES[permission]
    if permission_profile() == "mvp" and role in ENGINEERING_ROLES:
        if permission is not None:
            return permission in MVP_ENGINEERING
        role = "engineer"
    if exact:
        return role in roles
    hierarchy = {"chief_engineer": {"chief_engineer", "engineer", "dispatcher"},
                 "engineer": {"engineer", "dispatcher"}}
    return bool(hierarchy.get(role, {role}).intersection(roles))


def permits(role, permission):
    return has_role(role, GATES[permission], exact=True, permission=permission)


def tool_allowed(role, tool):
    return has_role(role, tool.roles, exact=True, permission=TOOL_PERMISSIONS.get(tool.name))


def public_permissions(role):
    profile = permission_profile()
    if profile == "legacy":
        return {}
    return dict(permissionProfile=profile, permissions=[gate for gate in GATES if permits(role, gate)])
