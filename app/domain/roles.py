RESEARCHER = "researcher"
REVIEWER = "reviewer"
SCHOOL_MANAGER = "school_manager"
DIRECTORATE_MANAGER = "directorate_manager"
SCIENTIFIC_COMMITTEE = "scientific_committee"
ORGANIZING_COMMITTEE = "organizing_committee"
DECISION_MAKER = "decision_maker"
SYSTEM_ADMIN = "system_admin"

ALL_AUTH_ROLES = {
    RESEARCHER,
    REVIEWER,
    SCHOOL_MANAGER,
    DIRECTORATE_MANAGER,
    SCIENTIFIC_COMMITTEE,
    ORGANIZING_COMMITTEE,
    DECISION_MAKER,
    SYSTEM_ADMIN,
}

ROLE_CAPABILITIES = {
    RESEARCHER: [
        "training.join",
        "guide.read",
        "template.use",
        "research.submit",
        "research.track",
        "research.resubmit",
        "research.publish",
        "certificate.view",
    ],
    REVIEWER: [
        "review.invitation.accept",
        "review.confidentiality.accept",
        "review.assigned.read",
        "review.submit",
        "review.revision.read",
        "research.decide",
    ],
    SCHOOL_MANAGER: [
        "school.accounts.approve",
        "school.researchers.monitor",
        "school.indicators.read",
        "school.achievements.read",
    ],
    DIRECTORATE_MANAGER: [
        "directorate.accounts.manage",
        "directorate.performance.read",
        "directorate.reports.export",
    ],
    SCIENTIFIC_COMMITTEE: [
        "conference.manage",
        "conference.participations.review",
        "conference.notices.send",
    ],
    ORGANIZING_COMMITTEE: [
        "conference.assigned.read",
        "schedule.manage",
        "news.manage",
        "certificates.manage",
    ],
    DECISION_MAKER: [
        "dashboard.read",
        "observatory.read",
        "reports.export",
        "recommendations.follow",
        "policies.read",
    ],
    SYSTEM_ADMIN: [
        "permissions.manage",
        "reviewers.assign",
        "publication.payment.confirm",
        "content.manage",
        "backups.manage",
        "audit.read",
    ],
}

LEGACY_ALIASES = {"user": RESEARCHER}


def normalize_role(role: str | None) -> str:
    value = (role or "").strip().lower()
    return LEGACY_ALIASES.get(value, value)


def validate_role(role: str) -> str:
    normalized = normalize_role(role)
    if normalized not in ALL_AUTH_ROLES:
        raise ValueError("Unsupported role")
    return normalized
