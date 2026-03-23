import json
import os
from typing import Any, List, Tuple

from tvc_nodes.contracts import PromptArchitectInput, PromptArchitectOutput
from tvc_nodes.services import PromptArchitectServices


def _compose_prompt_for_epoch(
    node_input: PromptArchitectInput,
    style_profile: dict,
    epoch: dict,
    raw_prompt: str,
) -> Tuple[str, str]:
    style_dna = (
        str(node_input.style_dna or "").strip()
        or style_profile.get("scene_style_dna_default", "Cinematic documentary palette")
    )
    meta_context = (
        str(node_input.meta_context or "").strip()
        or style_profile.get("scene_meta_context_default", "Documentary video")
    )
    character_manifest = node_input.character_manifest
    if not isinstance(character_manifest, dict):
        character_manifest = {}
    subjects = epoch.get("subjects", [])
    if not isinstance(subjects, list):
        subjects = []
    char_dna = ""
    for subject in subjects:
        subject_key = str(subject).strip()
        if subject_key and subject_key in character_manifest:
            char_dna += f" Character '{subject_key}': {character_manifest[subject_key]}."
    full_prompt = f"{style_dna}. {meta_context}.{char_dna} {raw_prompt}".strip()
    qa_target = raw_prompt.split("ABSOLUTE NEGATIVE")[0].strip()
    return full_prompt, qa_target


def _fallback_raw_prompt(style_profile: dict, epoch: dict) -> str:
    return (
        "Photorealistic 16:9 cinematic shot: "
        f"{epoch.get('visual_intent', epoch.get('text', style_profile.get('prompt_fallback_scene_label', 'Narration scene')))}"
    )


def _build_prompt_arrays(
    node_input: PromptArchitectInput,
    style_profile: dict,
    entries: Any,
) -> Tuple[List[str], List[str]]:
    epochs = node_input.epochs
    by_id = {}
    if isinstance(entries, list):
        for idx, item in enumerate(entries):
            if not isinstance(item, dict):
                continue
            epoch_id = None
            raw_id = item.get("id")
            if isinstance(raw_id, int):
                epoch_id = raw_id
            elif isinstance(raw_id, float):
                epoch_id = int(raw_id)
            elif isinstance(raw_id, str) and raw_id.strip().isdigit():
                epoch_id = int(raw_id.strip())
            if epoch_id is None and idx < len(epochs):
                fallback_id = epochs[idx].get("id", idx + 1)
                epoch_id = int(fallback_id) if isinstance(fallback_id, (int, float)) else idx + 1
            by_id[epoch_id] = item

    prompts = []
    qa_targets = []
    for idx, epoch in enumerate(epochs):
        raw_epoch_id = epoch.get("id", idx + 1)
        epoch_id = int(raw_epoch_id) if isinstance(raw_epoch_id, (int, float)) else idx + 1
        row = by_id.get(epoch_id)
        raw_prompt = ""
        if isinstance(row, dict):
            raw_prompt = str(row.get("sota_prompt", "") or "").strip()
        if not raw_prompt:
            raw_prompt = _fallback_raw_prompt(style_profile, epoch)
        final_prompt, qa_target = _compose_prompt_for_epoch(node_input, style_profile, epoch, raw_prompt)
        prompts.append(final_prompt)
        qa_targets.append(qa_target)
    return prompts, qa_targets


def _cache_valid(data: Any, needed: int) -> bool:
    if needed <= 0:
        return False
    if isinstance(data, list):
        prompts = [str(item).strip() for item in data if str(item).strip()]
        return len(prompts) >= needed
    if isinstance(data, dict):
        prompts = [str(item).strip() for item in data.get("prompts", []) if str(item).strip()]
        qa_targets = [str(item).strip() for item in data.get("qa_targets", []) if str(item).strip()]
        if len(qa_targets) < len(prompts):
            qa_targets.extend([prompt.split("ABSOLUTE NEGATIVE")[0].strip() for prompt in prompts[len(qa_targets):]])
        return len(prompts) >= needed and len(qa_targets) >= needed
    return False


def _env_flag_enabled(services: PromptArchitectServices, name: str) -> bool:
    value = services.getenv(name, "0")
    return str(value or "0").strip().lower() in {"1", "true", "on", "yes"}


def run_prompt_architect(
    node_input: PromptArchitectInput,
    services: PromptArchitectServices,
) -> PromptArchitectOutput:
    narration_style = services.normalize_narration_style(
        node_input.narration_style or services.narration_style_default
    )
    input_source = str(node_input.input_source or "").strip().upper()
    context_rewrite = services.normalize_context_rewrite(node_input.context_rewrite or "auto")
    deterministic_user_context_mode = input_source == "USER_CONTEXT" and context_rewrite != "force"
    suppress_prompt_architect_api = deterministic_user_context_mode or _env_flag_enabled(
        services, "TVC_SUPPRESS_PROMPT_ARCHITECT_API"
    )
    style_profile = services.narration_profile(narration_style)
    script_hash = services.get_hash(
        f"{services.get_hash(node_input.script)}|{style_profile.get('cache_key', narration_style)}|"
        f"{services.get_hash(str(node_input.style_dna or ''))}|{services.get_hash(str(node_input.meta_context or ''))}"
    )
    manifest = services.manifest.load() or {}
    prompts_file = services.artifacts.read_path("master_prompts.json")
    node_report = {
        "status": "pending",
        "source": "unknown",
        "prompt_count": 0,
        "qa_count": 0,
        "contract_valid": False,
        "failure": "",
        "narration_style": narration_style,
    }

    if suppress_prompt_architect_api:
        sota_prompts, qa_targets = _build_prompt_arrays(node_input, style_profile, [])
        services.artifacts.write_json(
            "master_prompts.json",
            {"prompts": sota_prompts, "qa_targets": qa_targets},
            mirror_legacy=None,
        )
        manifest["prompts_script_hash"] = script_hash
        services.manifest.save(manifest)
        suppress_source = (
            "deterministic_user_context_fallback" if deterministic_user_context_mode else "env_suppressed_fallback"
        )
        node_report.update(
            {
                "status": "prompts_architected",
                "source": suppress_source,
                "prompt_count": len(node_input.epochs),
                "qa_count": len(node_input.epochs),
                "contract_valid": True,
            }
        )
        services.update_scene_audio_prompt_report("PromptArchitect", node_report)
        print(
            f"    [PROMPT ARCHITECT] API suppressed ({suppress_source}). "
            "Using deterministic local prompt composition."
        )
        for idx, prompt in enumerate(sota_prompts):
            print(f"      - E[{idx+1}/{len(node_input.epochs)}] {prompt[:80]}...")
        return PromptArchitectOutput(
            sota_prompts=sota_prompts[: len(node_input.epochs)],
            qa_targets=qa_targets[: len(node_input.epochs)],
            status="prompts_architected",
            node_report=node_report,
        )

    if manifest.get("prompts_script_hash") == script_hash and os.path.exists(prompts_file):
        try:
            with open(prompts_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if _cache_valid(data, len(node_input.epochs)):
                if isinstance(data, list):
                    sota_prompts = [str(item).strip() for item in data if str(item).strip()]
                    qa_targets = [prompt.split("ABSOLUTE NEGATIVE")[0].strip() for prompt in sota_prompts]
                else:
                    sota_prompts = [str(item).strip() for item in data.get("prompts", []) if str(item).strip()]
                    qa_targets = [str(item).strip() for item in data.get("qa_targets", []) if str(item).strip()]
                    if len(qa_targets) < len(sota_prompts):
                        qa_targets.extend(
                            [prompt.split("ABSOLUTE NEGATIVE")[0].strip() for prompt in sota_prompts[len(qa_targets):]]
                        )
                print("    [RESUMING] Valid visual prompts found for this script. Skipping Architect API call.")
                node_report.update(
                    {
                        "status": "prompts_architected",
                        "source": "cache_resume",
                        "prompt_count": len(node_input.epochs),
                        "qa_count": len(node_input.epochs),
                        "contract_valid": True,
                    }
                )
                services.update_scene_audio_prompt_report("PromptArchitect", node_report)
                return PromptArchitectOutput(
                    sota_prompts=sota_prompts[: len(node_input.epochs)],
                    qa_targets=qa_targets[: len(node_input.epochs)],
                    status="prompts_architected",
                    node_report=node_report,
                )
            node_report["failure"] = "cache_invalid"
        except Exception as exc:
            node_report["failure"] = f"cache_parse_error: {exc}"

    epochs_json = json.dumps(
        [
            {
                "id": epoch["id"],
                "text": epoch["text"],
                "visual_intent": epoch.get("visual_intent", epoch["text"]),
            }
            for epoch in node_input.epochs
        ],
        indent=2,
    )

    system_instruction = f"""You are a master cinematic Vision Director and SOTA Prompt Engineer.

Given a JSON array of narrative text epochs, generate a JSON array of highly-specific, photorealistic, 16:9 cinematic image prompts for EACH epoch.

STYLE MODE CONTEXT: {narration_style} ({style_profile.get("label", narration_style)}).
STYLE HINT: {style_profile.get("prompt_tone_hint", "")}

You MUST use a TWO-STEP REASONING PROCESS:

1. [VISUAL INTENT FOUNDATION]: You have been given a pre-written 'visual_intent' for each epoch. Use this as your foundation. Do NOT ignore it.

2. [SOTA ARCHITECTURE]: Expand that visual intent into a photorealistic, 16:9 cinematic prompt using this EXACT 6-layer Photographic Taxonomy Matrix: [Subject] + [Environment] + [Lighting] + [Camera/Lens] + [Angle/Composition] + [Atmosphere].

CRITICAL NEGATIVE PROMPT INSTRUCTION: At the very end of EVERY prompt, you MUST append EXACTLY this string: " ABSOLUTE NEGATIVE PROMPT: No text, no words, no letters, no typography, no watermarks, no distorted objects."

Do NOT include the Style DNA or Meta-Context in your generation. They will be prepended automatically later.

Return ONLY strict JSON matching this schema exactly: [{{"id": 1, "sota_prompt": "Cinematic 16:9 [Angle] shot of [Subject] in [Environment], [Lighting], captured on [Camera/Lens], [Atmosphere]. ABSOLUTE NEGATIVE PROMPT: No text..."}}]"""

    prompts_data = None
    source = "primary"
    primary_error = None
    try:
        response = services.smart_retry(
            services.fireworks_chat_completion,
            "fireworks_llm",
            contents=epochs_json,
            config=services.generate_content_config(system_instruction=system_instruction, temperature=0.2),
            prompt_template_id="PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS",
            trace_node="PromptArchitect",
        )
        prompts_data = services.json_repair(str(response.text or "").strip())
    except Exception as exc:
        primary_error = exc

    if prompts_data is None:
        repair_prompt = f"""Repair this epoch prompt payload into strict JSON array schema:
[{{"id": 1, "sota_prompt": "string"}}]
Rules:
- One entry per epoch id from input.
- JSON only, no markdown.

EPOCHS:
{epochs_json}

FAILED_ERROR:
{str(primary_error)[:600]}
"""
        try:
            repair_response = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=repair_prompt,
                config=services.generate_content_config(
                    system_instruction="Return strict JSON array only. No prose.",
                    temperature=0.0,
                ),
                prompt_template_id="PROMPT_H_PROMPT_ARCHITECT_REPAIR",
                trace_node="PromptArchitect",
            )
            prompts_data = services.json_repair(str(repair_response.text or "").strip())
            source = "repair_retry"
        except Exception as exc:
            node_report["failure"] = f"repair_failed: {exc}"

    if prompts_data is not None:
        try:
            sota_prompts, qa_targets = _build_prompt_arrays(node_input, style_profile, prompts_data)
        except Exception as exc:
            print(
                "    [WARNING] Prompt Architect normalization failed. Falling back to literal translation. "
                f"{exc}"
            )
            prompts_data = None

    if prompts_data is None:
        source = "literal_fallback"
        sota_prompts, qa_targets = _build_prompt_arrays(node_input, style_profile, [])

    if len(sota_prompts) != len(node_input.epochs) or len(qa_targets) != len(node_input.epochs):
        source = "literal_fallback"
        sota_prompts, qa_targets = _build_prompt_arrays(node_input, style_profile, [])

    for idx, prompt in enumerate(sota_prompts):
        print(f"      - E[{idx+1}/{len(node_input.epochs)}] {prompt[:80]}...")

    services.artifacts.write_json(
        "master_prompts.json",
        {"prompts": sota_prompts, "qa_targets": qa_targets},
        mirror_legacy=None,
    )
    manifest["prompts_script_hash"] = script_hash
    services.manifest.save(manifest)

    node_report.update(
        {
            "status": "prompts_architected",
            "source": source,
            "prompt_count": len(sota_prompts),
            "qa_count": len(qa_targets),
            "contract_valid": len(sota_prompts) == len(node_input.epochs)
            and len(qa_targets) == len(node_input.epochs),
        }
    )
    services.update_scene_audio_prompt_report("PromptArchitect", node_report)

    print(f"    [PROMPT ARCHITECT] Successfully forged {len(sota_prompts)} master prompts.")

    return PromptArchitectOutput(
        sota_prompts=sota_prompts[: len(node_input.epochs)],
        qa_targets=qa_targets[: len(node_input.epochs)],
        status="prompts_architected",
        node_report=node_report,
    )
