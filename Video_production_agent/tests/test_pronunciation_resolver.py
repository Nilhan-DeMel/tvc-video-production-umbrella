from tvc_nodes.pronunciation import resolve_pronunciation


def test_phrase_rule_beats_token_rule_for_polish_visual_clarity():
    result = resolve_pronunciation(
        "I create AI-powered videos with polish, rhythm, and visual clarity.",
        backend="edge_tts",
    )

    assert (
        result["spoken_script"]
        == "I create AI-powered videos with refinement, rhythm, and visual clarity."
    )
    assert result["display_spoken_diff"] is True
    assert result["matched_rule_ids"] == ["phrase.polish_rhythm_visual_clarity"]


def test_safe_context_does_not_rewrite_polish_nationality():
    result = resolve_pronunciation(
        "We worked with Polish teams from Warsaw on the launch.",
        backend="edge_tts",
    )

    assert result["spoken_script"] == "We worked with Polish teams from Warsaw on the launch."
    assert result["display_spoken_diff"] is False
    assert result["matched_rule_ids"] == []

