"""
Permission Matrix — Role-Based Access Control
=============================================
Defines which actions each role may perform.
Used by middleware and route guards throughout IMDF.

Roles: admin | reviewer | annotator | viewer
"""

from typing import Dict, List, Optional

# Action catalogue
ACTIONS = [
    # User & auth
    "manage_users",         # Create / disable / delete / change-role users
    "manage_api_keys",      # Create / revoke own API keys
    "view_all_users",       # List all users
    "view_own_profile",     # View own user info

    # Data & datasets
    "create_dataset",
    "edit_dataset",
    "delete_dataset",
    "view_own_datasets",
    "view_all_datasets",

    # Annotation
    "annotate",             # Submit annotations
    "view_own_tasks",       # View tasks assigned to self
    "view_all_tasks",       # View all tasks

    # Review
    "review",               # Approve / reject annotations
    "review_final",         # Final sign-off

    # Stats & reports
    "view_stats",
    "view_audit_logs",
    "export_data",

    # System
    "manage_system",        # System-level config / quotas
    "view_system_info",     # Read-only system info

    # Delivery
    "manage_delivery",
    "view_delivery",
]

# Permission matrix: role → set of allowed actions
PERMISSION_MATRIX: Dict[str, List[str]] = {
    "admin": [
        "manage_users",
        "manage_api_keys",
        "view_all_users",
        "view_own_profile",
        "create_dataset",
        "edit_dataset",
        "delete_dataset",
        "view_own_datasets",
        "view_all_datasets",
        "annotate",
        "view_own_tasks",
        "view_all_tasks",
        "review",
        "review_final",
        "view_stats",
        "view_audit_logs",
        "export_data",
        "manage_system",
        "view_system_info",
        "manage_delivery",
        "view_delivery",
    ],
    "reviewer": [
        "manage_api_keys",
        "view_own_profile",
        "view_own_datasets",
        "view_all_datasets",
        "annotate",
        "view_own_tasks",
        "view_all_tasks",
        "review",
        "review_final",
        "view_stats",
        "view_audit_logs",
        "export_data",
        "view_system_info",
        "view_delivery",
    ],
    "annotator": [
        "manage_api_keys",
        "view_own_profile",
        "view_own_datasets",
        "view_own_tasks",
        "annotate",
        "view_system_info",
    ],
    "viewer": [
        "manage_api_keys",
        "view_own_profile",
        "view_own_datasets",
        "view_own_tasks",
        "view_system_info",
    ],
}


def get_allowed_actions(role: str) -> List[str]:
    """Return the list of actions allowed for a given role."""
    return PERMISSION_MATRIX.get(role, PERMISSION_MATRIX.get("viewer", []))


def check_permission(role: str, action: str) -> bool:
    """Check whether a role is permitted to perform an action.

    Args:
        role: One of admin / reviewer / annotator / viewer
        action: An action string from ACTIONS

    Returns:
        True if permitted, False otherwise.
    """
    allowed = get_allowed_actions(role)
    return action in allowed


def require_permission(role: str, action: str) -> None:
    """Raise HTTPException(403) if the role lacks the action.

    Convenience wrapper for route handlers.
    """
    from fastapi import HTTPException

    if not check_permission(role, action):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' lacks permission '{action}'",
        )


def require_admin(current_user: dict) -> None:
    """Convenience: raise 403 if current user is not admin."""
    require_permission(current_user.get("role", "viewer"), "manage_users")
