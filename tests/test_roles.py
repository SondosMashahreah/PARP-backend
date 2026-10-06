from app.domain.roles import (
    ALL_AUTH_ROLES,
    RESEARCHER,
    REVIEWER,
    SYSTEM_ADMIN,
    normalize_role,
    validate_role,
)


def test_expected_roles_exist():
    assert RESEARCHER in ALL_AUTH_ROLES
    assert REVIEWER in ALL_AUTH_ROLES
    assert SYSTEM_ADMIN in ALL_AUTH_ROLES
    assert len(ALL_AUTH_ROLES) == 9


def test_legacy_user_maps_to_researcher():
    assert normalize_role("user") == RESEARCHER
    assert validate_role("user") == RESEARCHER
