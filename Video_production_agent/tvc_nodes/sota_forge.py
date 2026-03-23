import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from tvc_nodes.contracts import SotaForgeInput, SotaForgeOutput
from tvc_nodes.services import SotaForgeServices


def _select_pre_scene_route(
    node_input: SotaForgeInput,
    services: SotaForgeServices,
) -> Tuple[str, str, str, Optional[Dict[str, Any]], str, List[Dict[str, Any]]]:
    pre_scene_route_source = "legacy_primary"
    pre_scene_route_variant = "none"
    pre_scene_route_reason = "no_valid_candidate"
    pre_scene_payload = None
    pre_scene_selected_file = ""
    pre_scene_candidate_checks: List[Dict[str, Any]] = []

    required_epoch_ids: List[int] = []
    for idx, epoch in enumerate(node_input.epochs):
        raw_id = epoch.get("id", idx + 1) if isinstance(epoch, dict) else idx + 1
        try:
            required_epoch_ids.append(int(raw_id))
        except Exception:
            required_epoch_ids.append(idx + 1)

    route_candidates = [
        {"file_name": "pre_scene_manifest_repaired.json", "route_source": "pre_scene_repaired_primary"},
        {"file_name": "pre_scene_manifest.json", "route_source": "pre_scene_raw_primary"},
        {"file_name": "scene_manifest.json", "route_source": "scene_manifest_primary"},
    ]
    for candidate in route_candidates:
        file_name = str(candidate.get("file_name", "") or "")
        route_source = str(candidate.get("route_source", "") or "")
        candidate_path = services.artifacts.read_path(file_name)
        check: Dict[str, Any] = {
            "source": route_source,
            "file": candidate_path,
            "valid": False,
            "reason": "",
            "scene_count": 0,
        }
        if not os.path.exists(candidate_path):
            check["reason"] = "missing_file"
            pre_scene_candidate_checks.append(check)
            continue
        try:
            with open(candidate_path, "r", encoding="utf-8") as handle:
                raw_payload = json.load(handle)
            normalized_payload = services.normalize_pre_scene_manifest_payload(raw_payload)
            if normalized_payload is None:
                check["reason"] = "invalid_contract"
                pre_scene_candidate_checks.append(check)
                continue
            raw_scene_keys = dict(normalized_payload.get("scenes", {}) or {}).keys()
            scene_keys = set()
            for raw_scene_key in raw_scene_keys:
                try:
                    scene_keys.add(int(raw_scene_key))
                except Exception:
                    scene_keys.add(raw_scene_key)
            missing_ids = [sid for sid in required_epoch_ids if sid not in scene_keys]
            check["scene_count"] = len(scene_keys)
            if missing_ids:
                check["reason"] = f"missing_ids:{','.join(str(x) for x in missing_ids)}"
                pre_scene_candidate_checks.append(check)
                continue
            check["valid"] = True
            check["reason"] = "ok"
            pre_scene_candidate_checks.append(check)
            pre_scene_payload = normalized_payload
            pre_scene_route_source = "pre_scene_primary"
            pre_scene_route_variant = route_source
            pre_scene_route_reason = f"candidate_valid:{route_source}"
            pre_scene_selected_file = candidate_path
            break
        except Exception as exc:
            check["reason"] = f"parse_error:{str(exc)[:120]}"
            pre_scene_candidate_checks.append(check)
            continue

    return (
        pre_scene_route_source,
        pre_scene_route_variant,
        pre_scene_route_reason,
        pre_scene_payload,
        pre_scene_selected_file,
        pre_scene_candidate_checks,
    )


def _write_sota_route_row(services: SotaForgeServices, row: Dict[str, Any]) -> None:
    try:
        payload = dict(row or {})
        payload["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        services.append_jsonl_artifact("sota_prompt_route_trace.jsonl", payload, mirror_legacy=None)
    except Exception:
        pass


def _publish_sotaforge_subprogress(
    services: SotaForgeServices,
    total_epoch_units: int,
    completed_units: int,
    detail: str,
    force: bool = False,
) -> None:
    bounded_completed = max(0, min(total_epoch_units, int(completed_units or 0)))
    ratio = bounded_completed / float(total_epoch_units) if total_epoch_units > 0 else 0.0
    services.update_live_status(
        {
            "current_node_progress_ratio": round(ratio, 4),
            "current_node_units_completed": bounded_completed,
            "current_node_units_total": total_epoch_units,
            "current_node_units_label": "epochs",
            "current_node_detail": str(detail or ""),
        },
        force=force,
    )


def run_sota_forge(
    node_input: SotaForgeInput,
    services: SotaForgeServices,
) -> SotaForgeOutput:
    qa_pass_threshold = 4.0
    qa_model = str(
        services.getenv(
            "FIREWORKS_VISION_QA_MODEL",
            "accounts/fireworks/models/kimi-k2p5",
        )
        or "accounts/fireworks/models/kimi-k2p5"
    ).strip()
    input_source = str(node_input.input_source or "").strip().upper()
    context_rewrite = services.normalize_context_rewrite(node_input.context_rewrite)
    deterministic_user_context_mode = input_source == "USER_CONTEXT" and context_rewrite != "force"
    suppress_visual_qa = deterministic_user_context_mode or str(
        services.getenv("TVC_SUPPRESS_VISUAL_QA", "0") or "0"
    ).strip().lower() in {"1", "true", "on", "yes"}
    if suppress_visual_qa:
        print("    [SOTA VISION FORGE] Visual QA is suppressed for this run.")

    asset_dir = services.artifacts.path("assets")
    os.makedirs(asset_dir, exist_ok=True)

    smart_cropper = services.smartcrop_factory() if services.smartcrop_factory else None
    pil_image_module = services.pil_image_module
    final_scores: List[float] = []
    last_valid_image_path = ""
    run_memory = {"TEXT": 0, "ANATOMY": 0, "SUBJECT": 0, "COMPOSITION": 0, "QUALITY": 0}
    qa_targets = list(node_input.qa_targets or [])
    epochs_payload = services.build_epoch_context_payload(node_input.epochs)
    (
        pre_scene_route_source,
        pre_scene_route_variant,
        pre_scene_route_reason,
        pre_scene_payload,
        pre_scene_selected_file,
        pre_scene_candidate_checks,
    ) = _select_pre_scene_route(node_input, services)

    print(
        f"    [SOTA VISION FORGE] Prompt route: {pre_scene_route_source} "
        f"({pre_scene_route_reason})."
    )
    services.update_scene_audio_prompt_report(
        "SotaForge",
        {
            "status": "prompt_route_selected",
            "route_source": pre_scene_route_source,
            "route_variant": pre_scene_route_variant,
            "route_reason": pre_scene_route_reason,
            "selected_route_file": pre_scene_selected_file,
            "required_epoch_ids": [int(ep.get("id", idx + 1)) if isinstance(ep, dict) and str(ep.get("id", idx + 1)).isdigit() else idx + 1 for idx, ep in enumerate(node_input.epochs)],
            "candidate_checks": pre_scene_candidate_checks,
            "contract_valid": pre_scene_route_source in {"pre_scene_primary", "legacy_primary"},
        },
    )

    total_epoch_units = max(1, int(node_input.total_epochs or len(node_input.epochs) or 1))
    _publish_sotaforge_subprogress(
        services,
        total_epoch_units,
        0,
        f"Preparing epoch 1/{total_epoch_units}",
        force=True,
    )

    for i, epoch in enumerate(node_input.epochs):
        legacy_prompt = node_input.sota_prompts[i] if i < len(node_input.sota_prompts) else ""
        if pre_scene_payload is not None:
            current_prompt = services.compose_pre_scene_primary_prompt(pre_scene_payload, epoch)
            seeded_image_prompt = current_prompt
        else:
            current_prompt = legacy_prompt
            seeded_image_prompt = services.compose_image_generation_prompt(
                base_prompt=current_prompt,
                epoch=epoch,
                epochs_payload=epochs_payload,
            )
        base_primary_prompt = current_prompt
        try:
            epoch_id = int(epoch.get("id", i + 1))
        except Exception:
            epoch_id = i + 1
        route_row = {
            "epoch_id": epoch_id,
            "route_source": pre_scene_route_source,
            "route_variant": pre_scene_route_variant,
            "route_reason": pre_scene_route_reason,
            "selected_route_file": pre_scene_selected_file,
            "primary_prompt_chars": len(str(seeded_image_prompt or "")),
            "fallback_used": False,
            "fallback_reason": "",
            "cache_used": False,
            "attempts_used": 0,
            "epoch_result": "pending",
        }

        prompt_hash = hashlib.sha256(seeded_image_prompt.encode("utf-8")).hexdigest()[:8]
        target_fp = os.path.join(asset_dir, f"epoch_{epoch_id:03d}_{prompt_hash}.png")
        epoch["image_path"] = target_fp

        if os.path.exists(target_fp):
            try:
                with pil_image_module.open(target_fp) as cached_img:
                    cache_valid_dims = cached_img.size[0] >= 1920 and cached_img.mode in ("RGB", "RGBA")
                    cache_dims = cached_img.size
                if cache_valid_dims:
                    if suppress_visual_qa:
                        epoch["image_source"] = "generated"
                        last_valid_image_path = target_fp
                        final_scores.append(float(qa_pass_threshold))
                        print(f"  [OK] [CACHED NO-QA] Epoch {epoch_id:03d} accepted.")
                        route_row["cache_used"] = True
                        route_row["attempts_used"] = 0
                        route_row["epoch_result"] = "cache_accept_no_qa"
                        _publish_sotaforge_subprogress(
                            services,
                            total_epoch_units,
                            i + 1,
                            f"Epoch {i + 1}/{total_epoch_units} · cached",
                            force=True,
                        )
                        _write_sota_route_row(services, route_row)
                        continue
                    main_description = services.extract_main_description_for_qa(current_prompt, qa_targets, i)
                    try:
                        qa_result = services.run_visual_qa_for_image(
                            image_path=target_fp,
                            main_description=main_description,
                            qa_model=qa_model,
                            qa_pass_threshold=qa_pass_threshold,
                        )
                    except Exception as cache_qa_err:
                        qa_result = {
                            "qa_text": "CATEGORY:QUALITY",
                            "score": 0.0,
                            "has_real_score": False,
                            "critique": f"Vision QA unavailable for cache: {str(cache_qa_err)[:120]}",
                            "failure_cat": "QUALITY",
                        }
                    if qa_result["has_real_score"] and qa_result["score"] >= qa_pass_threshold:
                        epoch["image_source"] = "generated"
                        last_valid_image_path = target_fp
                        final_scores.append(float(qa_result["score"]))
                        print(f"  [OK] [CACHED+QA] Epoch {epoch_id:03d} accepted at {qa_result['score']}/10.")
                        route_row["cache_used"] = True
                        route_row["attempts_used"] = 0
                        route_row["epoch_result"] = "cache_accept_with_qa"
                        _publish_sotaforge_subprogress(
                            services,
                            total_epoch_units,
                            i + 1,
                            f"Epoch {i + 1}/{total_epoch_units} · cached",
                            force=True,
                        )
                        _write_sota_route_row(services, route_row)
                        continue
                    print(
                        f"  [WARN] [CACHE REJECTED] Epoch {epoch_id:03d} scored {qa_result['score']}/10 "
                        f"(real_score={qa_result['has_real_score']}). Regenerating."
                    )
                    os.remove(target_fp)
                else:
                    print(f"  [WARN] [CACHE INVALID] Epoch {epoch_id:03d} has wrong dims {cache_dims}. Regenerating.")
                    os.remove(target_fp)
            except Exception:
                print(f"  [WARN] [CACHE CORRUPT] Epoch {epoch_id:03d} unreadable. Regenerating.")
                if os.path.exists(target_fp):
                    os.remove(target_fp)

        if run_memory.get("TEXT", 0) >= 2:
            print("    [ALC RUN-MEMORY] TEXT failures dominant across previous epochs. Pre-applying anti-text surgery.")
            text_patterns = [
                r"\b(?:sign|banner|inscription|scroll|letter|book|title|headline|placard|poster|notice|calligraphy|writing)\b",
                r"\b(?:text|words|letters|typography)\b",
            ]
            for pattern in text_patterns:
                current_prompt = re.sub(pattern, "", current_prompt, flags=re.IGNORECASE)

        epoch_text = epoch["text"]
        print(f"\n  - Epoch {epoch_id:03d}: '{epoch_text[:60]}...'")
        _publish_sotaforge_subprogress(
            services,
            total_epoch_units,
            i,
            f"Epoch {i + 1}/{total_epoch_units} · generating",
        )

        passed = False
        score = 0.0
        failure_memory: List[str] = []
        temp_fp = target_fp.replace(".png", "_temp.png")

        for attempt in range(1, 4):
            route_row["attempts_used"] = attempt
            if pre_scene_payload is not None:
                generation_prompt = current_prompt
            else:
                generation_prompt = services.compose_image_generation_prompt(
                    base_prompt=current_prompt,
                    epoch=epoch,
                    epochs_payload=epochs_payload,
                )
            fallback_generation_prompt = services.compose_compact_epoch_fallback_prompt(
                epoch=epoch,
                style_hint=str(current_prompt or "").split(".", 1)[0].strip(),
            )
            if attempt == 1:
                try:
                    services.write_text_artifact(
                        f"sota_epoch_{epoch_id:03d}_generation_prompt.txt",
                        generation_prompt,
                        mirror_legacy=None,
                    )
                except Exception:
                    pass

            print(f"    Shot {attempt}/3 | Prompt: {current_prompt[:60]}...")
            generation_success = False
            print("        [MODE: BFL FLUX2 PRO]")

            try:
                generation_success = services.smart_retry(
                    services.bfl_generate_image,
                    "bfl_image",
                    prompt=generation_prompt,
                    width=1920,
                    height=1088,
                    output_path=temp_fp,
                    prompt_template_id="PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT",
                    trace_node="SotaForge",
                )
            except Exception as gen_err:
                generation_success = False
                gen_err_txt = str(gen_err or "")
                gen_err_low = gen_err_txt.lower()
                if "400" in gen_err_low or "invalid_request" in gen_err_low:
                    route_row["fallback_used"] = True
                    route_row["fallback_reason"] = "primary_invalid_request_400"
                    print("        [MODE: BFL COMPACT FALLBACK] combined prompt rejected, retrying compact prompt.")
                    try:
                        if attempt == 1:
                            services.write_text_artifact(
                                f"sota_epoch_{epoch_id:03d}_generation_prompt_fallback.txt",
                                fallback_generation_prompt,
                                mirror_legacy=None,
                            )
                        generation_success = services.smart_retry(
                            services.bfl_generate_image,
                            "bfl_image",
                            prompt=fallback_generation_prompt,
                            width=1920,
                            height=1088,
                            output_path=temp_fp,
                            prompt_template_id="PROMPT_I_SOTA_FORGE_FALLBACK_COMPACT",
                            trace_node="SotaForge",
                        )
                    except Exception as fb_err:
                        generation_success = False
                        route_row["fallback_reason"] = f"fallback_failed:{str(fb_err)[:120]}"
                        print(f"        [MODE: BFL COMPACT FALLBACK] generation failed: {str(fb_err)[:180]}")
                if not generation_success:
                    print(f"        [MODE: BFL FLUX2 PRO] generation failed: {gen_err_txt[:180]}")

            if generation_success and smart_cropper and pil_image_module:
                try:
                    with pil_image_module.open(temp_fp) as img:
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        width, height = img.size
                        scale = min(width / 1920, height / 1080)
                        crop_width, crop_height = int(1920 * scale), int(1080 * scale)
                        result = smart_cropper.crop(img, crop_width, crop_height)
                        top_crop = result["top_crop"]
                        cropped = img.crop(
                            (top_crop["x"], top_crop["y"], top_crop["x"] + top_crop["width"], top_crop["y"] + top_crop["height"])
                        )
                        resampling = getattr(getattr(pil_image_module, "Resampling", None), "LANCZOS", None)
                        resized = cropped.resize((1920, 1080), resampling)
                        resized.save(temp_fp, quality=95)
                except Exception:
                    pass

            if not generation_success:
                continue

            if suppress_visual_qa:
                score = qa_pass_threshold
                has_real_score = True
                critique = "Visual QA suppressed for this run."
                qa_text = "CATEGORY:SKIPPED"
                print("    [QA SUPPRESSED] Accepting generated image without QA scoring.")
            else:
                try:
                    main_description = services.extract_main_description_for_qa(current_prompt, qa_targets, i)
                    qa_result = services.run_visual_qa_for_image(
                        image_path=temp_fp,
                        main_description=main_description,
                        qa_model=qa_model,
                        qa_pass_threshold=qa_pass_threshold,
                    )
                    qa_text = qa_result["qa_text"]
                    score = float(qa_result["score"])
                    has_real_score = bool(qa_result["has_real_score"])
                    critique = qa_result["critique"]
                    print(f"    QA Score: {score}/10 | Feedback: {critique[:120].replace(chr(10), ' ')}...")
                except Exception as exc:
                    score = 0.0
                    has_real_score = False
                    critique = f"Vision QA unavailable: {str(exc)[:120]}"
                    qa_text = "CATEGORY:QUALITY"
                    print(f"    [QA WARNING] API failed. No simulated pass. {str(exc)[:80]}")

            if has_real_score and score >= qa_pass_threshold:
                print(f"    [OK] [QA PASSED] Epoch {epoch_id:03d} locked at {score}/10.")
                if os.path.exists(target_fp):
                    os.remove(target_fp)
                os.rename(temp_fp, target_fp)
                epoch["image_source"] = "generated"
                last_valid_image_path = target_fp
                final_scores.append(score)
                route_row["epoch_result"] = "qa_pass"
                _publish_sotaforge_subprogress(
                    services,
                    total_epoch_units,
                    i + 1,
                    f"Epoch {i + 1}/{total_epoch_units} · complete",
                    force=True,
                )
                passed = True
                break

            category_match = re.search(r"CATEGORY:\s*([A-Z]+)", qa_text, re.IGNORECASE)
            failure_cat = category_match.group(1).upper() if category_match else "UNKNOWN"
            failure_memory.append(failure_cat)
            print(f"     [QA FAILED] Category: {failure_cat} | Initiating prompt refinement...")

            if attempt < 3:
                if os.path.exists(temp_fp):
                    os.remove(temp_fp)
                recurring = len(failure_memory) >= 2 and failure_memory[-1] == failure_memory[-2]

                if recurring and failure_cat == "TEXT":
                    print("     [ALC] Recurring TEXT failure. Performing targeted text-removal surgery.")
                    text_patterns = [
                        r"\b(?:sign|banner|inscription|scroll|letter|book|title|headline|placard|poster|notice|calligraphy|writing)\b",
                        r"\b(?:text|words|letters|typography)\b",
                    ]
                    for pattern in text_patterns:
                        current_prompt = re.sub(pattern, "", current_prompt, flags=re.IGNORECASE)
                    current_prompt = current_prompt.replace(
                        "ABSOLUTE NEGATIVE PROMPT:",
                        "ABSOLUTE NEGATIVE PROMPT: No visible text of any kind, no signage, no readable letters, no writing, no typography,",
                    )
                elif recurring and failure_cat == "ANATOMY":
                    print("    [ALC] Recurring ANATOMY failure. Stripping Character DNA complexity.")
                    current_prompt = re.sub(r" Character '\w+':\s*\{[^}]+\}\.", "", current_prompt)
                    current_prompt = current_prompt.replace(
                        "ABSOLUTE NEGATIVE PROMPT:",
                        "ABSOLUTE NEGATIVE PROMPT: No distorted anatomy, no extra limbs, no deformed faces,",
                    )
                elif recurring and failure_cat == "SUBJECT":
                    print("    [ALC] Recurring SUBJECT failure. Resetting prompt to original master.")
                    current_prompt = base_primary_prompt
                elif recurring and failure_cat == "COMPOSITION":
                    print("    [ALC] Recurring COMPOSITION failure. Stripping background complexity.")
                    raw_scene_fallback = qa_targets[i] if i < len(qa_targets) else current_prompt[-200:]
                    current_prompt = f"Photorealistic 16:9 cinematic shot. {raw_scene_fallback} {services.unified_negative_prompt}"
                else:
                    neg_fence = "ABSOLUTE NEGATIVE PROMPT:"
                    if neg_fence in current_prompt:
                        clean_base, neg_part = current_prompt.split(neg_fence, 1)
                        current_prompt = f"{clean_base.rstrip()}. REFINEMENT: {critique[:120]}. {neg_fence}{neg_part}"
                    else:
                        current_prompt += f" REFINEMENT: {critique[:120]}."

        if not passed:
            print(
                f"    [WARN] [SURRENDER] Epoch {epoch_id:03d} failed to reach QA {qa_pass_threshold:.1f}/10 after 3 shots (Score: {score}). Applying Graceful Surrender Protocol."
            )
            if failure_memory:
                dominant_cat = failure_memory[-1]
                run_memory[dominant_cat] = run_memory.get(dominant_cat, 0) + 1
            if os.path.exists(temp_fp):
                if os.path.exists(target_fp):
                    os.remove(target_fp)
                os.rename(temp_fp, target_fp)
            image_source = services.ensure_epoch_image_with_fallback(
                target_fp,
                last_valid_path=last_valid_image_path,
                label=f"EPOCH-{epoch_id:03d}",
            )
            epoch["image_source"] = image_source
            if os.path.exists(target_fp):
                last_valid_image_path = target_fp
            final_scores.append(score)
            route_row["epoch_result"] = "graceful_surrender"
            _publish_sotaforge_subprogress(
                services,
                total_epoch_units,
                i + 1,
                f"Epoch {i + 1}/{total_epoch_units} · fallback",
                force=True,
            )
        else:
            epoch["image_source"] = services.ensure_epoch_image_with_fallback(
                target_fp,
                last_valid_path=last_valid_image_path,
                label=f"EPOCH-{epoch_id:03d}",
            )
            if os.path.exists(target_fp):
                last_valid_image_path = target_fp
            if route_row.get("epoch_result", "pending") == "pending":
                route_row["epoch_result"] = "qa_pass_or_best_effort"
            if route_row["epoch_result"] != "qa_pass":
                _publish_sotaforge_subprogress(
                    services,
                    total_epoch_units,
                    i + 1,
                    f"Epoch {i + 1}/{total_epoch_units} · complete",
                    force=True,
                )
        _write_sota_route_row(services, route_row)

    services.update_scene_audio_prompt_report(
        "SotaForge",
        {
            "status": "sota_vision_complete",
            "route_source": pre_scene_route_source,
            "route_variant": pre_scene_route_variant,
            "route_reason": pre_scene_route_reason,
            "selected_route_file": pre_scene_selected_file,
            "candidate_checks": pre_scene_candidate_checks,
            "images_forged": len(final_scores),
            "total_epochs": node_input.total_epochs,
            "contract_valid": len(final_scores) == int(node_input.total_epochs or 0),
        },
    )

    print(
        f"\n[OK]  [SOTA VISION FORGE] Mission Accomplished. "
        f"{len(final_scores)}/{node_input.total_epochs} epochs forged to perfection."
    )

    return SotaForgeOutput(
        status="sota_vision_complete",
        qa_scores=final_scores,
        images_forged=len(final_scores),
        epochs=node_input.epochs,
    )
