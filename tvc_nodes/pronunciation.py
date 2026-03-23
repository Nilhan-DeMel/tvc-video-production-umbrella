from dataclasses import asdict, dataclass
import re
from typing import Dict, List


PRONUNCIATION_RULESET_ID = "pronunciation_rules.v1"


@dataclass(frozen=True)
class PronunciationRule:
    id: str
    scope: str
    match: str
    display_text: str
    spoken_alias_edge: str
    reason: str
    phoneme_ssml: str = ""
    lexicon_key: str = ""
    pattern: str = ""
    case_sensitive: bool = False


_PHRASE_RULES: List[PronunciationRule] = [
    PronunciationRule(
        id="phrase.polish_rhythm_visual_clarity",
        scope="phrase",
        match="with polish, rhythm, and visual clarity",
        display_text="with polish, rhythm, and visual clarity",
        spoken_alias_edge="with refinement, rhythm, and visual clarity",
        reason="Disambiguate the lowercase business-marketing noun 'polish' from the nationality pronunciation.",
    ),
]

_TOKEN_RULES: List[PronunciationRule] = [
    PronunciationRule(
        id="token.resume_job_application",
        scope="token",
        match="resume",
        display_text="resume",
        spoken_alias_edge="résumé",
        reason="Disambiguate the job-application noun from the verb 'resume'.",
        pattern=r"(?:(?<=\byour )|(?<=\bsend your )|(?<=\battach your )|(?<=\bemail your ))resume\b",
        case_sensitive=True,
    ),
]


def _rule_replacement(rule: PronunciationRule, backend: str) -> str:
    if backend == "edge_tts":
        return rule.spoken_alias_edge
    if rule.phoneme_ssml:
        return rule.phoneme_ssml
    return rule.spoken_alias_edge


def _apply_rule(text: str, rule: PronunciationRule, backend: str) -> Dict[str, object]:
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    if rule.scope == "phrase":
        pattern = re.escape(rule.match)
    else:
        pattern = rule.pattern or rf"\b{re.escape(rule.match)}\b"
    updated, count = re.subn(pattern, _rule_replacement(rule, backend), text, flags=flags)
    return {"text": updated, "count": count}


def resolve_pronunciation(display_script: str, backend: str = "edge_tts", voice: str = "") -> dict:
    display = str(display_script or "")
    spoken = display
    matched_rules = []

    for rule in _PHRASE_RULES:
        applied = _apply_rule(spoken, rule, backend)
        spoken = str(applied["text"])
        count = int(applied["count"])
        if count > 0:
            payload = asdict(rule)
            payload["match_count"] = count
            matched_rules.append(payload)

    for rule in _TOKEN_RULES:
        applied = _apply_rule(spoken, rule, backend)
        spoken = str(applied["text"])
        count = int(applied["count"])
        if count > 0:
            payload = asdict(rule)
            payload["match_count"] = count
            matched_rules.append(payload)

    return {
        "ruleset_id": PRONUNCIATION_RULESET_ID,
        "display_script": display,
        "spoken_script": spoken,
        "matched_rules": matched_rules,
        "matched_rule_ids": [str(rule.get("id", "")).strip() for rule in matched_rules if str(rule.get("id", "")).strip()],
        "backend": backend,
        "voice": str(voice or ""),
        "display_spoken_diff": display != spoken,
    }
