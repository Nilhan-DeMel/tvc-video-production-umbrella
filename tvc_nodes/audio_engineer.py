import asyncio
import json
import os
import time
from typing import Any, Dict

from tvc_nodes.contracts import AudioEngineerInput, AudioEngineerOutput
from tvc_nodes.services import AudioEngineerServices


def _duration_payload(node_input: AudioEngineerInput) -> Dict[str, Any]:
    return {
        "script": node_input.script,
        "context_summary": node_input.context_summary,
        "request_prompt": node_input.request_prompt,
        "input_source": node_input.input_source,
        "context_rewrite": node_input.context_rewrite,
        "narration_style": node_input.narration_style,
        "duration_mode": node_input.duration_mode,
        "requested_target_duration_seconds": node_input.requested_target_duration_seconds,
        "estimated_duration_seconds": node_input.estimated_duration_seconds,
        "target_duration": node_input.target_duration,
        "actual_audio_duration_seconds": node_input.actual_audio_duration_seconds,
    }


def _persist_stage_report(services: AudioEngineerServices, stage_report: dict) -> None:
    try:
        services.artifacts.write_json("audio_stage_report.json", stage_report, mirror_legacy=None)
    except Exception:
        pass


def _add_stage(services: AudioEngineerServices, stage_report: dict, stage_name: str, info: dict) -> None:
    row = {"stage": stage_name}
    row.update(info or {})
    stage_report["stages"].append(row)
    _persist_stage_report(services, stage_report)


async def _synthesize_audio_and_vtt(
    services: AudioEngineerServices,
    tts_script: str,
    tts_voice: str,
    tts_rate: str,
    tts_pitch: str,
    tts_volume: str,
) -> None:
    communicator = services.communicate_factory(
        tts_script,
        tts_voice,
        rate=tts_rate,
        pitch=tts_pitch,
        volume=tts_volume,
    )
    submaker = services.submaker_factory()
    chunks = []
    async for chunk in communicator.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
        elif chunk["type"] in ["WordBoundary", "SentenceBoundary"]:
            if chunk["type"] == "SentenceBoundary":
                print(f"    [AUDIO ENGINEER] Captured {chunk['type']} at {chunk['offset']/10000000:.2f}s")
            submaker.feed(chunk)
    services.write_binary_artifact("master_narration.mp3", b"".join(chunks), mirror_legacy=None)
    services.write_text_artifact(
        "narration.vtt",
        "WEBVTT\n\n" + submaker.get_srt().replace(",", "."),
        mirror_legacy=None,
    )


def run_audio_engineer(
    node_input: AudioEngineerInput,
    services: AudioEngineerServices,
) -> AudioEngineerOutput:
    duration_meta = services.duration_meta_from_state(_duration_payload(node_input))
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
    tts_profile = dict(style_profile.get("audio_tts", {}))
    requested_voice_preset = str(node_input.voice_preset or services.voice_preset_default).strip()
    voice_resolution = services.resolve_voice_preset(requested_voice_preset, tts_profile)
    tts_voice = str(voice_resolution.get("voice", "en-GB-RyanNeural") or "en-GB-RyanNeural")
    tts_rate = str(voice_resolution.get("rate", "+0%") or "+0%")
    tts_pitch = str(voice_resolution.get("pitch", "+0Hz") or "+0Hz")
    tts_volume = str(voice_resolution.get("volume", "+0%") or "+0%")
    script_hash = services.get_hash(
        f"{services.get_hash(node_input.script)}|{style_profile.get('cache_key', narration_style)}|"
        f"{requested_voice_preset}|{tts_voice}|{tts_rate}|{tts_pitch}|{tts_volume}"
    )

    manifest = services.manifest.load() or {}

    audio_file = services.artifacts.path("master_narration.mp3")
    audio_read_file = services.artifacts.read_path("master_narration.mp3")
    vtt_file = services.artifacts.path("narration.vtt")
    vtt_read_file = services.artifacts.read_path("narration.vtt")
    matrix_read_file = services.artifacts.read_path("vtt_matrix.json")
    audio_stage_file = services.artifacts.path("audio_stage_report.json")

    stage_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "script_hash": script_hash,
        "narration_style": narration_style,
        "style_profile": style_profile.get("label", narration_style),
        "api_bypassed": bool(deterministic_user_context_mode),
        "bypass_reason": "deterministic_user_context_mode" if deterministic_user_context_mode else "",
        "voice_preset_requested": requested_voice_preset,
        "voice_preset_effective": voice_resolution.get("effective_preset_id", requested_voice_preset),
        "voice_fallback_used": bool(voice_resolution.get("fallback_used", False)),
        "voice_fallback_reason": str(voice_resolution.get("fallback_reason", "") or ""),
        "voice_provider": str(voice_resolution.get("provider", "edge")),
        "voice_engine": str(voice_resolution.get("engine", "edge_tts")),
        "voice": tts_voice,
        "voice_identity": str(voice_resolution.get("voice_identity", tts_voice) or tts_voice),
        "voice_style_base": dict(voice_resolution.get("style_base", {}) or {}),
        "voice_preset_overlay": dict(voice_resolution.get("preset_overlay", {}) or {}),
        "tts_params": {"rate": tts_rate, "pitch": tts_pitch, "volume": tts_volume},
        "duration_mode": duration_meta.get("duration_mode"),
        "requested_target_duration_seconds": duration_meta.get("requested_target_duration_seconds"),
        "estimated_duration_seconds": duration_meta.get("estimated_duration_seconds"),
        "effective_planning_duration_seconds": duration_meta.get("effective_planning_duration_seconds"),
        "actual_audio_duration_seconds": duration_meta.get("actual_audio_duration_seconds"),
        "stages": [],
        "mapping_source": "",
        "status": "pending",
    }

    if (
        not deterministic_user_context_mode
        and manifest.get("audio_script_hash") == script_hash
        and os.path.exists(audio_read_file)
        and os.path.exists(vtt_read_file)
    ):
        try:
            with open(matrix_read_file, "r", encoding="utf-8") as handle:
                epochs = services.normalize_epochs_from_mapping(json.load(handle), node_input.visual_scenes)
            print("    [RESUMING] Valid audio and VTT alignment found. Skipping Forge.")
            stage_report["status"] = "audio_forged"
            stage_report["mapping_source"] = "cache_resume"
            _add_stage(services, stage_report, "resume", {"used": True, "epoch_count": len(epochs)})
            services.update_scene_audio_prompt_report(
                "Audio",
                {
                    "status": "audio_forged",
                    "source": "cache_resume",
                    "mapping_source": "cache_resume",
                    "epoch_count": len(epochs),
                    "total_epochs": len(epochs),
                    "contract_valid": len(epochs) > 0,
                    "audio_stage_report": audio_stage_file,
                },
            )
            return AudioEngineerOutput(
                audio_path=audio_read_file,
                vtt_path=vtt_read_file,
                actual_audio_duration_seconds=duration_meta.get("actual_audio_duration_seconds"),
                epochs=epochs,
                total_epochs=len(epochs),
                images_forged=node_input.images_forged,
                qa_attempts=node_input.qa_attempts,
                status="audio_forged",
            )
        except Exception as exc:
            _add_stage(services, stage_report, "resume", {"used": True, "status": "cache_invalid", "error": str(exc)[:220]})

    ingress_script = services.sanitize_tts_script(node_input.script)
    if not ingress_script:
        stage_report["status"] = "failed"
        _add_stage(services, stage_report, "ingress", {"status": "failed", "error": "empty_script"})
        services.update_scene_audio_prompt_report(
            "Audio",
            {
                "status": "failed",
                "source": "ingress",
                "mapping_source": "none",
                "contract_valid": False,
                "failure": "empty_script",
            },
        )
        return AudioEngineerOutput(
            images_forged=node_input.images_forged,
            qa_attempts=node_input.qa_attempts,
            status="failed",
            errors=["Voice Forge Failed: empty_script"],
        )

    _add_stage(services, stage_report, "ingress", {"status": "ok", "word_count": len(ingress_script.split())})

    cpp_system_instruction = (
        "You are a SOTA prosody engineer for AI Speech. Your ONLY job is to optimize this script for natural human-like pacing by removing or replacing breath-breaking commas. "
        f"STYLE GOAL: {style_profile.get('audio_cpp_goal', '')} "
        "Do NOT add content. Preserve wording and meaning. Output ONLY cleaned narration text."
    )
    tts_script = ingress_script
    cpp_source = "ingress"
    if deterministic_user_context_mode:
        _add_stage(
            services,
            stage_report,
            "neural_cpp",
            {
                "status": "bypassed",
                "api_bypassed": True,
                "bypass_reason": "deterministic_user_context_mode",
            },
        )
    else:
        try:
            cpp_response = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=ingress_script,
                config=services.generate_content_config(
                    system_instruction=cpp_system_instruction,
                    temperature=0.05,
                ),
                prompt_template_id="PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT",
                trace_node="Audio",
            )
            neural_text = services.sanitize_tts_script(str(cpp_response.text or "").strip())
            base_word_count = len(ingress_script.split())
            neural_word_count = len(neural_text.split())
            alignment = services.summarize_cpp_alignment(ingress_script, neural_text)
            overlap = float(alignment["base_token_recall"])
            if neural_text and base_word_count > 0 and neural_word_count > 0 and neural_word_count <= int(base_word_count * 1.35) and overlap >= 0.60:
                tts_script = neural_text
                cpp_source = "neural_cpp"
                _add_stage(services, stage_report, "neural_cpp", {"status": "accepted", "word_count": neural_word_count, **alignment})
            else:
                rejection_reasons = []
                if not neural_text or neural_word_count <= 0:
                    rejection_reasons.append("empty_candidate")
                if base_word_count > 0 and neural_word_count > int(base_word_count * 1.35):
                    rejection_reasons.append("runaway_word_growth")
                if overlap < 0.60:
                    rejection_reasons.append("low_base_token_recall")
                _add_stage(
                    services,
                    stage_report,
                    "neural_cpp",
                    {
                        "status": "rejected",
                        "word_count": neural_word_count,
                        "rejection_reasons": rejection_reasons or ["shape_drift"],
                        **alignment,
                    },
                )
        except Exception as exc:
            _add_stage(services, stage_report, "neural_cpp", {"status": "failed", "error": str(exc)[:220]})

    if cpp_source != "neural_cpp":
        tts_script = services.sanitize_tts_script(services.apply_cpp(ingress_script))
        cpp_source = "local_cpp_primary" if deterministic_user_context_mode else "local_cpp_fallback"
        _add_stage(
            services,
            stage_report,
            "local_cpp",
            {
                "status": "used",
                "word_count": len(tts_script.split()),
                "reason": "deterministic_primary" if deterministic_user_context_mode else "fallback_after_neural_cpp",
            },
        )
    tts_script = services.sanitize_tts_script(tts_script)
    _add_stage(services, stage_report, "sanitize", {"status": "ok", "word_count": len(tts_script.split())})

    try:
        asyncio.run(_synthesize_audio_and_vtt(services, tts_script, tts_voice, tts_rate, tts_pitch, tts_volume))
        _add_stage(services, stage_report, "edge_tts", {"status": "ok"})
    except Exception as exc:
        stage_report["status"] = "failed"
        _add_stage(services, stage_report, "edge_tts", {"status": "failed", "error": str(exc)[:220]})
        services.update_scene_audio_prompt_report(
            "Audio",
            {
                "status": "failed",
                "source": cpp_source,
                "mapping_source": "none",
                "contract_valid": False,
                "failure": f"Voice Forge Failed: {exc}",
            },
        )
        return AudioEngineerOutput(
            images_forged=node_input.images_forged,
            qa_attempts=node_input.qa_attempts,
            status="failed",
            errors=[f"Voice Forge Failed: {exc}"],
        )

    audio_duration = services.ffprobe_duration(audio_file)
    duration_meta = services.duration_meta_from_state(_duration_payload(node_input), actual_audio_duration=audio_duration)
    stage_report["actual_audio_duration_seconds"] = duration_meta.get("actual_audio_duration_seconds")
    _add_stage(
        services,
        stage_report,
        "audio_duration",
        {
            "status": "ok" if audio_duration is not None else "missing",
            "seconds": audio_duration,
        },
    )
    services.update_run_manifest_duration_fields(duration_meta)
    services.update_live_status(
        {"actual_audio_duration_seconds": duration_meta.get("actual_audio_duration_seconds")},
        force=True,
    )

    with open(services.artifacts.read_path("narration.vtt"), "r", encoding="utf-8") as handle:
        vtt_data = handle.read()

    scenes_json = json.dumps(node_input.visual_scenes, indent=2)
    mapping_prompt = f"""Map precise start_time and end_time VTT boundaries onto these STRICT pre-defined Visual Scenes.

Do NOT invent new scenes, alter the text, or change the IDs. Your ONLY job is to find the timestamp of the first spoken word and the last spoken word for each scene.

Return ONLY a JSON array that perfectly matches the input scenes, but with timestamps added:

[{{"id": 1, "start_time": float, "end_time": float, "duration": float,
    "text": "Exact string", "visual_intent": "Exact string from input"}}]

PRE-DEFINED SCENES TO MAP:

{scenes_json}

VTT TELEMETRY:

{vtt_data}"""

    epochs = services.build_local_epoch_mapping(node_input.visual_scenes, vtt_data, tts_script)
    mapping_source = "local_deterministic_primary"
    _add_stage(services, stage_report, "vtt_map_local_primary", {"status": "ok", "epoch_count": len(epochs)})

    if deterministic_user_context_mode:
        _add_stage(
            services,
            stage_report,
            "vtt_map_refine",
            {
                "status": "bypassed",
                "api_bypassed": True,
                "bypass_reason": "deterministic_user_context_mode",
                "epoch_count": len(epochs),
            },
        )
    else:
        try:
            mapping_response = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=mapping_prompt,
                config=services.generate_content_config(
                    system_instruction="Return strict JSON array.",
                    temperature=0.1,
                ),
                prompt_template_id="PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING",
                trace_node="Audio",
            )
            raw_epochs = services.json_repair(str(mapping_response.text or "").strip())
            candidate_epochs = services.normalize_epochs_from_mapping(raw_epochs, node_input.visual_scenes)
            if len(candidate_epochs) == len(epochs):
                epochs = candidate_epochs
                mapping_source = "llm_refine_primary"
                _add_stage(services, stage_report, "vtt_map_refine", {"status": "accepted", "epoch_count": len(epochs)})
            else:
                _add_stage(services, stage_report, "vtt_map_refine", {"status": "rejected", "reason": "epoch_count_mismatch"})
        except Exception as exc:
            _add_stage(services, stage_report, "vtt_map_refine", {"status": "failed", "error": str(exc)[:220]})

    services.artifacts.write_json("vtt_matrix.json", epochs, mirror_legacy=None)

    manifest["audio_script_hash"] = script_hash
    services.manifest.save(manifest)
    stage_report["mapping_source"] = mapping_source
    stage_report["status"] = "audio_forged"
    _persist_stage_report(services, stage_report)

    services.update_scene_audio_prompt_report(
        "Audio",
        {
            "status": "audio_forged",
            "source": cpp_source,
            "mapping_source": mapping_source,
            "api_bypassed": bool(deterministic_user_context_mode),
            "bypass_reason": "deterministic_user_context_mode" if deterministic_user_context_mode else "",
            "epoch_count": len(epochs),
            "total_epochs": len(epochs),
            "contract_valid": len(epochs) > 0,
            "audio_stage_report": audio_stage_file,
        },
    )

    print(f"    [AUDIO ENGINEER] {len(epochs)} epochs aligned. Audio: {audio_file}")

    return AudioEngineerOutput(
        audio_path=audio_file,
        vtt_path=vtt_file,
        actual_audio_duration_seconds=duration_meta.get("actual_audio_duration_seconds"),
        epochs=epochs,
        total_epochs=len(epochs),
        images_forged=0,
        qa_attempts=0,
        status="audio_forged",
    )
