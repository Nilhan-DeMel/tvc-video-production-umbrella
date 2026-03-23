import hashlib
import json
import os
import time
from typing import Any, Dict

from tvc_nodes.contracts import SceneDirectorInput, SceneDirectorOutput
from tvc_nodes.services import SceneDirectorServices


def _write_json_safely(services: SceneDirectorServices, name: str, payload: Any) -> None:
    try:
        services.artifacts.write_json(name, payload, mirror_legacy=None)
    except Exception:
        pass


def _normalize_scene_data(
    services: SceneDirectorServices,
    payload: Any,
    script_text: str,
    narration_style: str,
) -> dict:
    data = services.normalize_scene_payload(payload, script_text, narration_style=narration_style)
    return services.enforce_scene_mode_style(data, narration_style)


def _scene_director_prompt(
    node_input: SceneDirectorInput,
    narration_style: str,
    style_profile: dict,
    min_scene_count: int,
    unified_negative_prompt: str,
) -> str:
    return f"""You are a Master Film Director. Break this script into distinct VISUAL SCENES.

1. Segment strictly by complete visual ideas. NEVER break a sentence mid-clause.

2. Aim for 3-5 seconds of spoken audio per scene, but MEANING always overrides timing.

3. For each scene, create a 'visual_intent': a concrete, physical camera shot (no abstract metaphors).

4. Create a single global 'style_dna' (color palette, lens era, lighting texture) to unify the video.

5. Create a single 'meta_context' (1-line summary of the big picture).

6. CHARACTER CASTING: Identify any person, animal, or distinctive object that appears in MORE THAN ONE scene. For each, create a 'character_manifest' entry with a short ID and a 30-50 word hyper-specific physical description (age, gender, hair colour/style, eye colour, skin tone, exact clothing with fabrics/colours, and one unique identifying detail like a scar, badge, or hat). If no recurring subjects exist, set character_manifest to {{}}.

7. For each scene, add a 'subjects' array listing which character IDs appear in that scene. If none, use an array [].

8. CARDINALITY CONTRACT (STRICT): You MUST return AT LEAST {min_scene_count} scenes for this script. If needed, split by sentence-level visual beats, but keep each scene semantically coherent.

9. NARRATION STYLE MODE: {narration_style} ({style_profile.get("label", narration_style)}).
   STYLE INTENT HINT: {style_profile.get("scene_direction_hint", "")}
   If unsure, keep style_dna close to: "{style_profile.get("scene_style_dna_default", "")}"
   If unsure, keep meta_context close to: "{style_profile.get("scene_meta_context_default", "")}"
   SAFETY SANITIZATION (MANDATORY): For every scene visual_intent, explicitly avoid readable text/signage/typography
   and avoid figure/face morphing artifacts.
   Append this exact suffix to each visual_intent:
   "{unified_negative_prompt}"

Return ONLY JSON:

{{

  "style_dna": "Consistent cinematic palette: deep navy, amber...",

  "meta_context": "Documentary about...",

  "character_manifest": {{"professor": "70-year-old man, wispy white Einstein-style hair, circular gold-rimmed spectacles, olive tweed blazer with brown leather elbow patches, navy silk bow tie, deep-set pale blue eyes"}},

  "scenes": [

    {{"id": 1, "text": "Exact sentence(s) from script",
                                       "visual_intent": "Wide drone shot of...", "subjects": ["professor"]}}

  ]

}}

Original Request Topic: {node_input.request_prompt or "Narration"}

SCRIPT TO SEGMENT:

{node_input.script}"""


def _deterministic_local_recovery(
    services: SceneDirectorServices,
    script_text: str,
    narration_style: str,
) -> dict:
    fallback_sentences = services.sentence_scene_recovery(script_text) or ["Narration segment."]
    fallback_profile = services.narration_profile(narration_style)
    visual_prefix = str(
        fallback_profile.get("scene_visual_prefix", "Cinematic shot showing:")
        or "Cinematic shot showing:"
    )
    return {
        "style_dna": str(
            fallback_profile.get(
                "scene_style_dna_default",
                "Premium cinematic campaign look, clean framing, polished lighting.",
            )
            or "Premium cinematic campaign look, clean framing, polished lighting."
        ),
        "meta_context": str(
            fallback_profile.get(
                "scene_meta_context_default",
                "Narrative progression from opening hook to confident close.",
            )
            or "Narrative progression from opening hook to confident close."
        ),
        "character_manifest": {},
        "scenes": [
            {
                "id": i + 1,
                "text": str(sentence),
                "visual_intent": f"{visual_prefix} {str(sentence).strip()}. {services.unified_negative_prompt}",
                "subjects": [],
            }
            for i, sentence in enumerate(fallback_sentences)
        ],
    }


def _finalize_result(
    services: SceneDirectorServices,
    script_hash: str,
    data: dict,
    node_report: dict,
    scene_director_diag: dict,
) -> SceneDirectorOutput:
    _write_json_safely(services, "pre_scene_manifest_repaired.json", data)
    scene_director_diag["final_contract_valid"] = len(data.get("scenes", [])) > 0
    scene_director_diag["final_scene_count"] = len(data.get("scenes", []))
    if not scene_director_diag.get("final_repaired_source"):
        scene_director_diag["final_repaired_source"] = "deterministic_fallback"
    scene_director_diag["final_node_source"] = node_report.get("source", "")
    _write_json_safely(services, "scene_director_diagnostics.json", scene_director_diag)
    services.artifacts.write_json("scene_manifest.json", data, mirror_legacy=None)

    manifest = services.manifest.load() or {}
    manifest["scene_script_hash"] = script_hash
    services.manifest.save(manifest)

    node_report.update(
        {
            "status": "scenes_directed",
            "scene_count": len(data.get("scenes", [])),
            "actual_scene_count": len(data.get("scenes", [])),
            "contract_valid": len(data.get("scenes", [])) > 0,
            "pre_scene_forensic_file": services.artifacts.path("pre_scene_manifest.json"),
            "pre_scene_repaired_file": services.artifacts.path("pre_scene_manifest_repaired.json"),
            "diagnostics_file": services.artifacts.path("scene_director_diagnostics.json"),
        }
    )
    services.update_scene_audio_prompt_report("SceneDirector", node_report)

    return SceneDirectorOutput(
        visual_scenes=data["scenes"],
        style_dna=data["style_dna"],
        meta_context=data["meta_context"],
        character_manifest=data.get("character_manifest", {}),
        status="scenes_directed",
        node_report=node_report,
    )


def run_scene_director(
    node_input: SceneDirectorInput,
    services: SceneDirectorServices,
) -> SceneDirectorOutput:
    script_text = str(node_input.script or "")
    narration_style = services.normalize_narration_style(
        node_input.narration_style or services.narration_style_default
    )
    deterministic_user_context_mode = services.is_deterministic_user_context_mode(
        {
            "input_source": node_input.input_source,
            "context_rewrite": node_input.context_rewrite,
        }
    )
    style_profile = services.narration_profile(narration_style)
    script_hash = services.get_hash(
        f"{services.get_hash(script_text)}|{style_profile.get('cache_key', narration_style)}"
    )
    min_scene_count = services.minimum_scene_count_for_script(script_text)
    scene_file = services.artifacts.read_path("scene_manifest.json")
    node_report = {
        "status": "pending",
        "source": "unknown",
        "scene_count": 0,
        "requested_min_scene_count": min_scene_count,
        "actual_scene_count": 0,
        "contract_valid": False,
        "failure": "",
        "narration_style": narration_style,
    }

    if deterministic_user_context_mode:
        scene_director_diag = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "node": "SceneDirector",
            "api_bypassed": True,
            "api_calls_made": 0,
            "bypass_reason": "deterministic_user_context_mode",
            "first_response_char_count": 0,
            "first_response_sha256_16": "",
            "local_repair_success": True,
            "local_repair_reason": "deterministic_primary_no_api",
            "repair_retry_success": False,
            "repair_retry_reason": "not_attempted_deterministic_no_api",
            "final_repaired_source": "deterministic_primary",
            "final_contract_valid": False,
            "final_scene_count": 0,
            "min_scene_count_required": int(min_scene_count),
        }
        try:
            data = services.deterministic_scene_builder(script_text, narration_style=narration_style)
            node_report["source"] = "deterministic_primary"
        except Exception as exc:
            print(f"    [SCENE DIRECTOR] Deterministic primary failed ({exc}). Using local sentence recovery.")
            data = _deterministic_local_recovery(services, script_text, narration_style)
            node_report["source"] = "deterministic_local_recovery"
            node_report["failure"] = f"deterministic_primary_exception:{str(exc)[:220]}"
            scene_director_diag["local_repair_success"] = False
            scene_director_diag["local_repair_reason"] = f"deterministic_primary_exception:{str(exc)[:220]}"
            scene_director_diag["final_repaired_source"] = "deterministic_local_recovery"

        data = _normalize_scene_data(services, data, script_text, narration_style)
        _write_json_safely(
            services,
            "pre_scene_manifest_prompt.json",
            {
                "node": "SceneDirector",
                "prompt_template_id": "PROMPT_F_SCENE_DIRECTOR_SEGMENTATION",
                "api_bypassed": True,
                "bypass_reason": "deterministic_user_context_mode",
                "mode": "USER_CONTEXT_deterministic",
                "contents": "",
            },
        )
        _write_json_safely(
            services,
            "pre_scene_manifest.json",
            {
                "api_bypassed": True,
                "bypass_reason": "deterministic_user_context_mode",
                "mode": "USER_CONTEXT_deterministic",
                "raw_response_text": "",
                "repair_error": "not_applicable_api_bypassed",
            },
        )
        node_report["api_bypassed"] = True
        node_report["bypass_reason"] = "deterministic_user_context_mode"
        return _finalize_result(services, script_hash, data, node_report, scene_director_diag)

    manifest = services.manifest.load() or {}
    if manifest.get("scene_script_hash") == script_hash and os.path.exists(scene_file):
        try:
            with open(scene_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            data = _normalize_scene_data(services, data, script_text, narration_style)
            print("    [RESUMING] Valid scenes & Style DNA found. Skipping Director API call.")
            node_report.update(
                {
                    "status": "scenes_directed",
                    "source": "cache_resume",
                    "scene_count": len(data["scenes"]),
                    "actual_scene_count": len(data["scenes"]),
                    "contract_valid": True,
                }
            )
            services.update_scene_audio_prompt_report("SceneDirector", node_report)
            return SceneDirectorOutput(
                visual_scenes=data["scenes"],
                style_dna=data["style_dna"],
                meta_context=data["meta_context"],
                character_manifest=data.get("character_manifest", {}),
                status="scenes_directed",
                node_report=node_report,
            )
        except Exception as exc:
            node_report["failure"] = f"cache_invalid: {exc}"

    prompt = _scene_director_prompt(
        node_input=node_input,
        narration_style=narration_style,
        style_profile=style_profile,
        min_scene_count=min_scene_count,
        unified_negative_prompt=services.unified_negative_prompt,
    )
    data = None
    primary_error = None
    low_cardinality_detected = False
    scene_director_model = "accounts/fireworks/models/kimi-k2p5"
    scene_director_system_instruction = "Return strict JSON for film scenes segmentation."
    scene_director_diag = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "node": "SceneDirector",
        "first_response_char_count": 0,
        "first_response_sha256_16": "",
        "local_repair_success": False,
        "local_repair_reason": "",
        "repair_retry_success": False,
        "repair_retry_reason": "",
        "final_repaired_source": "",
        "final_contract_valid": False,
        "final_scene_count": 0,
        "min_scene_count_required": int(min_scene_count),
    }
    _write_json_safely(
        services,
        "pre_scene_manifest_prompt.json",
        {
            "node": "SceneDirector",
            "prompt_template_id": "PROMPT_F_SCENE_DIRECTOR_SEGMENTATION",
            "model": scene_director_model,
            "system_instruction": scene_director_system_instruction,
            "contents": prompt,
        },
    )
    try:
        response = services.smart_retry(
            services.fireworks_chat_completion,
            "fireworks_llm",
            contents=prompt,
            model=scene_director_model,
            config=services.generate_content_config(
                system_instruction=scene_director_system_instruction,
                temperature=0.2,
            ),
            prompt_template_id="PROMPT_F_SCENE_DIRECTOR_SEGMENTATION",
            trace_node="SceneDirector",
        )
        response_text = str(response.text or "").strip()
        scene_director_diag["first_response_char_count"] = len(response_text)
        if response_text:
            scene_director_diag["first_response_sha256_16"] = hashlib.sha256(
                response_text.encode("utf-8")
            ).hexdigest()[:16]
        repaired_first_payload = None
        first_payload_error = None
        try:
            repaired_first_payload = services.json_repair(response_text)
            _write_json_safely(services, "pre_scene_manifest.json", repaired_first_payload)
            scene_director_diag["local_repair_success"] = True
            scene_director_diag["local_repair_reason"] = "local_json_repair_ok"
        except Exception as exc:
            first_payload_error = exc
            scene_director_diag["local_repair_success"] = False
            scene_director_diag["local_repair_reason"] = f"local_json_repair_failed:{str(exc)[:220]}"
            _write_json_safely(
                services,
                "pre_scene_manifest.json",
                {
                    "raw_response_text": response_text,
                    "repair_error": str(exc),
                },
            )
        if first_payload_error is not None:
            raise first_payload_error
        data = services.normalize_scene_payload(
            repaired_first_payload,
            script_text,
            narration_style=narration_style,
        )
        node_report["source"] = "primary"
        scene_director_diag["final_repaired_source"] = "first_response_local_repair"
        primary_count = len(data.get("scenes", []))
        if primary_count < min_scene_count:
            low_cardinality_detected = True
            node_report["failure"] = f"primary_scene_cardinality_low:{primary_count}<{min_scene_count}"
            data = None
    except Exception as exc:
        primary_error = exc
        print(f"    [SCENE DIRECTOR] Primary parse needs repair ({exc}). Running strict repair retry...")

    if data is None:
        if low_cardinality_detected:
            repair_prompt = f"""Expand this scene segmentation into strict JSON object schema with AT LEAST {min_scene_count} scenes:
{{
  "style_dna": "string",
  "meta_context": "string",
  "character_manifest": {{}},
  "scenes": [{{"id": 1, "text": "string", "visual_intent": "string", "subjects": []}}]
}}

Rules:
- Keep scenes grounded in the provided script.
- scenes must include at least {min_scene_count} coherent visual beats.
- Every scene requires text and visual_intent.
- subjects must be an array.

SCRIPT:
{script_text}

FAILED_ERROR:
primary_scene_cardinality_low
"""
        else:
            repair_prompt = f"""Repair this scene segmentation into strict JSON object schema:
{{
  "style_dna": "string",
  "meta_context": "string",
  "character_manifest": {{}},
  "scenes": [{{"id": 1, "text": "string", "visual_intent": "string", "subjects": []}}]
}}

Rules:
- Keep scenes grounded in the provided script.
- scenes must be a non-empty array.
- Every scene requires text and visual_intent.
- subjects must be an array.

SCRIPT:
{script_text}

FAILED_ERROR:
{str(primary_error)[:600]}
"""
        try:
            repair_response = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=repair_prompt,
                config=services.generate_content_config(
                    system_instruction="Return strict JSON object only. No markdown or prose.",
                    temperature=0.0,
                ),
                prompt_template_id="PROMPT_F_SCENE_DIRECTOR_REPAIR",
                trace_node="SceneDirector",
            )
            data = services.normalize_scene_payload(
                services.json_repair(str(repair_response.text or "").strip()),
                script_text,
                narration_style=narration_style,
            )
            node_report["source"] = "repair_retry"
            scene_director_diag["repair_retry_success"] = True
            scene_director_diag["repair_retry_reason"] = "repair_retry_json_ok"
            scene_director_diag["final_repaired_source"] = "repair_retry"
        except Exception as exc:
            print(f"    [SCENE DIRECTOR] Repair retry failed: {exc}")
            node_report["failure"] = f"repair_failed: {exc}"
            scene_director_diag["repair_retry_success"] = False
            scene_director_diag["repair_retry_reason"] = f"repair_retry_failed:{str(exc)[:220]}"

    if data is None:
        data = services.deterministic_scene_builder(script_text, narration_style=narration_style)
        node_report["source"] = "deterministic_fallback"
        scene_director_diag["final_repaired_source"] = "deterministic_fallback"
    else:
        scene_count = len(data.get("scenes", []))
        if scene_count < min_scene_count:
            print(
                f"    [SCENE DIRECTOR] Scene cardinality guard triggered ({scene_count} < {min_scene_count}). Using deterministic fallback."
            )
            data = services.deterministic_scene_builder(script_text, narration_style=narration_style)
            node_report["source"] = "deterministic_cardinality_fallback"
            scene_director_diag["final_repaired_source"] = "deterministic_fallback"
            if not node_report.get("failure"):
                node_report["failure"] = f"scene_cardinality_low:{scene_count}<{min_scene_count}"

    data = _normalize_scene_data(services, data, script_text, narration_style)
    return _finalize_result(services, script_hash, data, node_report, scene_director_diag)
