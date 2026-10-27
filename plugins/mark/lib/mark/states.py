"""Ticket state machine, as data.

Two chains share one vocabulary:

- feature: (drafting) -> designer -> coder-plan -> coder-impl -> (design-qa) -> tester,
  with three human review gates (review-requirement, review-design, review-plan).
  In `drafting` the orchestrator writes requirement.md with the human; no role runs.
- bug: fix-plan -> (designer, when the fix is in the UI directory) -> coder-impl -> tester,
  no review gates.

`status.md` answers "who acts next"; gate files answer "is it allowed". The
state machine never replaces a gate check.
"""
from __future__ import annotations

FEATURE = "feature"
BUG = "bug"
KINDS = (FEATURE, BUG)

# Directory name under the state dir for each ticket kind.
KIND_DIRS = {FEATURE: "features", BUG: "bugs"}

# Whose move it is in each status.
TERMINAL = frozenset({"passed", "superseded"})
HUMAN = frozenset({
    "review-requirement", "review-design", "review-plan",
    "blocked-plan", "blocked-spec", "blocked-unclear",
})
AGENT = frozenset({"designing", "planning", "developing", "design-qa", "testing", "failed-impl"})
# The orchestrator runs `mark merge`; a failed merge stops for the human (`mark next`).
MERGE = "pending-merge"
# The orchestrator writes the requirement with the human; no role is dispatched.
DRAFTING = "drafting"
# Statuses `mark set` cannot leave: only a human command (approve / reject) moves them on,
# or `mark merge` (pending-merge -> passed).
HELD = HUMAN | {MERGE}

INITIAL = {FEATURE: DRAFTING, BUG: "planning"}

_BLOCKED = ("blocked-plan", "blocked-spec", "blocked-unclear")

# Allowed moves. Every non-terminal status may also move to "superseded"
# (ticket folded into another one); that edge is added below.
_FEATURE_EDGES: dict[str, tuple[str, ...]] = {
    "drafting": ("review-requirement",),
    # planning: the project has no designer
    "review-requirement": ("designing", "planning", "drafting"),
    "designing": ("review-design", "blocked-spec", "blocked-unclear"),
    # design-qa / testing: a rework that changed only the UI keeps the approved plan (flow.ui_only_rework)
    "review-design": ("planning", "designing", "design-qa", "testing"),
    "planning": ("review-plan", "blocked-unclear"),
    "review-plan": ("developing", "planning"),
    "developing": ("design-qa", "testing", "blocked-plan", "blocked-spec", "blocked-unclear"),
    "design-qa": ("testing", "failed-impl", "blocked-spec"),
    "testing": ("pending-merge", "failed-impl", "blocked-spec", "blocked-unclear"),
    "failed-impl": ("design-qa", "testing", "blocked-plan", "blocked-spec", "blocked-unclear"),
    "pending-merge": ("passed", "failed-impl", "planning"),
    "blocked-plan": ("planning", "developing"),
    "blocked-spec": ("designing", "planning", "developing"),
    "blocked-unclear": ("designing", "planning", "developing", "testing"),
    "passed": (),
    "superseded": (),
}

_BUG_EDGES: dict[str, tuple[str, ...]] = {
    "planning": ("designing", "developing", "blocked-unclear"),
    "designing": ("developing", "testing", "blocked-unclear"),
    "developing": ("testing", "blocked-plan", "blocked-spec", "blocked-unclear"),
    "testing": ("pending-merge", "failed-impl", "blocked-spec", "blocked-unclear"),
    "failed-impl": ("testing", "blocked-plan", "blocked-spec", "blocked-unclear"),
    "pending-merge": ("passed", "failed-impl", "planning"),
    "blocked-plan": ("planning", "developing"),
    "blocked-spec": ("designing", "planning", "developing"),
    "blocked-unclear": ("designing", "planning", "developing", "testing"),
    "passed": (),
    "superseded": (),
}


def _with_superseded(edges: dict[str, tuple[str, ...]]) -> dict[str, frozenset[str]]:
    return {
        s: frozenset(nxt + (() if s in TERMINAL else ("superseded",)))
        for s, nxt in edges.items()
    }


TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    FEATURE: _with_superseded(_FEATURE_EDGES),
    BUG: _with_superseded(_BUG_EDGES),
}

# Role the orchestrator dispatches for an agent-side status.
ROLE_FOR_STATUS: dict[str, dict[str, str]] = {
    FEATURE: {
        "designing": "designer",
        "planning": "coder-plan",
        "developing": "coder-impl",
        "design-qa": "designer",
        "testing": "tester",
        "failed-impl": "coder-impl",
    },
    BUG: {
        "planning": "fix-plan",
        "designing": "designer",
        "developing": "coder-impl",
        "testing": "tester",
        "failed-impl": "coder-impl",
    },
}

# Statuses that require the `leftover` field (wrap-up accounting done).
LEFTOVER_REQUIRED = frozenset({"pending-merge", "passed"})


def statuses(kind: str) -> frozenset[str]:
    return frozenset(TRANSITIONS[kind])


def is_valid(kind: str, status: str) -> bool:
    return status in TRANSITIONS.get(kind, {})


def can_move(kind: str, old: str, new: str) -> bool:
    """True if `old -> new` is a legal move. Staying put is always legal."""
    if old == new:
        return is_valid(kind, old)
    return new in TRANSITIONS.get(kind, {}).get(old, frozenset())


def owner(kind: str, status: str) -> str:
    """Who acts in `status`: a role, `orchestrator`, `human` or `-`."""
    if status in (MERGE, DRAFTING):
        return "orchestrator"
    if status in AGENT:
        return ROLE_FOR_STATUS[kind].get(status, "-")
    return "human" if status in HUMAN else "-"


def side(status: str) -> str:
    """'human' | 'agent' | 'terminal' | 'unknown'."""
    if status in TERMINAL:
        return "terminal"
    if status in HUMAN:
        return "human"
    if status in AGENT or status in (MERGE, DRAFTING):
        return "agent"
    return "unknown"
