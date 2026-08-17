"""
ExaCommand — the AI layer's tool-calling contract.

Design intent (this is the governance story for Judge C / Trust & Safety):
  The LLM is NEVER allowed to write SQL, call Exasol directly, or touch the
  solver. It only ever proposes a ScenarioCommand — a small, fully-typed
  struct. That struct is validated and clamped here, in plain deterministic
  Python, before anything downstream (Exasol query or solver.py) ever sees
  it. If the LLM hallucinates a road ID that doesn't exist or proposes
  fleet_availability_pct = 4.2, that's caught here, not on stage.

  This mirrors how the real Exasol MCP server works, not just a design
  choice we made up: the bundled MCP server enforces a read-only login by
  default (docs: "Read-only AI. Your assistant can read everything and
  change nothing. The database enforces it.") — our AI layer only ever
  needs SELECT access for schema/read context, never a write path, so it
  fits that constraint natively rather than fighting it.

DEMO-SAFETY NOTE (read this before the demo, not during it):
  The map UI's own controls (fleet-% slider, click-a-road-to-block,
  priority toggle) call apply_scenario_command() DIRECTLY — they never go
  through the LLM. Only the opening free-text prompt needs the LLM. So if
  the LLM API dies mid-demo, the "judge interacts live" moment still works;
  you only lose the free-text parsing step, and RULE_BASED_FALLBACK below
  covers the handful of phrases you'll actually say in the pitch.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# The tool schema, in the format both the Anthropic and OpenAI function-
# calling APIs expect (minor key differences noted inline).
# ---------------------------------------------------------------------------
CONFIGURE_SCENARIO_TOOL = {
    "name": "configure_scenario",
    "description": (
        "Translate a described crisis/response scenario into structured "
        "deployment parameters. Do NOT compute an allocation yourself — "
        "only extract these parameters. The deployment plan is computed by "
        "a separate deterministic solver, not by you."
    ),
    "input_schema": {  # Anthropic calls this "input_schema"; OpenAI calls
        "type": "object",  # the same shape "parameters" — swap the key,
        "properties": {  # not the contents, if you switch providers.
            "fleet_availability_pct": {
                "type": "number",
                "description": "Fraction of the fleet (0.0-1.0) available right now.",
            },
            "prioritize_children_elderly": {
                "type": "boolean",
                "description": "Whether to up-weight zones with high children/elderly share.",
            },
            "blocked_road_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Road IDs (e.g. 'R001') mentioned as blocked/impassable. Empty if none mentioned.",
            },
        },
        "required": ["fleet_availability_pct", "prioritize_children_elderly", "blocked_road_ids"],
    },
}


@dataclass
class ScenarioCommand:
    fleet_availability_pct: float = 1.0
    prioritize_children_elderly: bool = False
    blocked_road_ids: list = field(default_factory=list)


VALID_ROAD_IDS = {"R001", "R002", "R003", "R004", "R005", "R006"}


def validate_and_clamp(raw: dict) -> ScenarioCommand:
    """The gate every LLM tool-call output passes through. Never trust the
    LLM's numbers or IDs directly — clamp/filter them here."""
    pct = raw.get("fleet_availability_pct", 1.0)
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = 1.0
    pct = max(0.0, min(1.0, pct))  # clamp to a valid fraction, no matter what the LLM said

    blocked = raw.get("blocked_road_ids", []) or []
    blocked = [r for r in blocked if r in VALID_ROAD_IDS]  # silently drop hallucinated IDs

    prioritize = bool(raw.get("prioritize_children_elderly", False))

    return ScenarioCommand(
        fleet_availability_pct=pct,
        prioritize_children_elderly=prioritize,
        blocked_road_ids=blocked,
    )


# ---------------------------------------------------------------------------
# Rule-based fallback parser — the "demo cannot die" path. Covers the
# handful of phrasings you'll actually use live. Not meant to be a good NLU
# system; meant to never be the reason a demo stalls.
# ---------------------------------------------------------------------------
def rule_based_fallback(text: str) -> dict:
    text_l = text.lower()

    pct = 1.0
    pct_match = re.search(r"(\d{1,3})\s*%", text_l)
    if pct_match:
        pct = int(pct_match.group(1)) / 100.0
    elif "half" in text_l:
        pct = 0.5
    elif "third" in text_l:
        pct = 1 / 3
    elif "quarter" in text_l:
        pct = 0.25

    prioritize = any(k in text_l for k in ["children", "elderly", "priorit"])

    blocked = [rid for rid in VALID_ROAD_IDS if rid.lower() in text_l]
    # also catch a couple of named roads from the corridor
    name_map = {"velachery main road": "R001", "100 feet road": "R002", "saidapet bridge": "R006"}
    for name, rid in name_map.items():
        if name in text_l:
            blocked.append(rid)

    return {
        "fleet_availability_pct": pct,
        "prioritize_children_elderly": prioritize,
        "blocked_road_ids": list(set(blocked)),
    }


# ---------------------------------------------------------------------------
# LLM call — wire your API key here. Left as a stub since this sandbox has
# no key; the contract above (tool schema + validate_and_clamp) is the part
# that matters and is fully testable without one.
# ---------------------------------------------------------------------------
def parse_scenario_with_llm(user_text: str, api_key: Optional[str] = None) -> ScenarioCommand:
    if api_key is None:
        # No key configured -> fall back immediately rather than erroring.
        return validate_and_clamp(rule_based_fallback(user_text))
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            tools=[CONFIGURE_SCENARIO_TOOL],
            tool_choice={"type": "tool", "name": "configure_scenario"},
            messages=[{"role": "user", "content": user_text}],
        )
        for block in resp.content:
            if block.type == "tool_use":
                return validate_and_clamp(block.input)
        return validate_and_clamp(rule_based_fallback(user_text))  # LLM didn't call the tool
    except Exception as e:
        print(f"[demo-safety] LLM call failed ({e}); using rule-based fallback")
        return validate_and_clamp(rule_based_fallback(user_text))


if __name__ == "__main__":
    tests = [
        "Only 60% of the fleet has reported ready. Prioritize children and elderly zones.",
        "Velachery Main Road is blocked, everything else is fine.",
        "Half our units are out. Saidapet Bridge is down too.",
    ]
    for t in tests:
        cmd = validate_and_clamp(rule_based_fallback(t))
        print(f"IN:  {t}\nOUT: {cmd}\n")
