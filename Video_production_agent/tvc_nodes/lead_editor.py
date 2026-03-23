import glob
import os
import subprocess
import time
from typing import Any, Dict, List, Tuple

from tvc_nodes.contracts import LeadEditorInput, LeadEditorOutput
from tvc_nodes.services import LeadEditorServices


def sec_to_ass(seconds: float) -> str:
    h, m = int(seconds // 3600), int((seconds % 3600) // 60)
    sc, cs = int(seconds % 60), int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 99
    return f"{h}:{m:02d}:{sc:02d}.{cs:02d}"


def _schedule_topic_cards_one_at_a_time(
    callouts: List[dict],
    epochs: List[dict],
    timeline_end: float,
) -> Tuple[List[dict], Dict[str, Any]]:
    report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "policy": "strict_one_at_a_time",
        "input_callouts": callouts,
        "resolved_anchors": [],
        "scheduled_windows": [],
        "dropped": [],
        "input_count": len(callouts) if isinstance(callouts, list) else 0,
        "valid_count": 0,
        "scheduled_count": 0,
        "dropped_count": 0,
        "adjusted_count": 0,
    }
    if not epochs:
        report["dropped"].append({"reason": "no_epochs"})
        report["dropped_count"] = len(report["dropped"])
        return [], report

    timeline_start = float(epochs[0].get("start_time", 0.0))
    last_epoch_end = float(epochs[-1].get("end_time", timeline_start))
    if timeline_end <= timeline_start:
        timeline_end = last_epoch_end
    timeline_end = max(timeline_end, last_epoch_end)
    report["timeline_start"] = round(timeline_start, 3)
    report["timeline_end"] = round(timeline_end, 3)

    valid = []
    for idx, callout in enumerate(callouts or []):
        if not isinstance(callout, dict):
            report["dropped"].append({"input_index": idx, "reason": "not_dict"})
            continue
        topic = str(callout.get("topic", "") or "").strip().upper()
        if not topic:
            report["dropped"].append({"input_index": idx, "reason": "empty_topic"})
            continue
        try:
            raw_after = callout.get("after_sentence", 1)
            if isinstance(raw_after, bool):
                raise ValueError("bool-not-allowed")
            sent_idx = int(raw_after) - 1
        except Exception:
            report["dropped"].append(
                {"input_index": idx, "reason": "invalid_after_sentence", "raw": callout.get("after_sentence")}
            )
            continue
        if sent_idx < 0 or sent_idx >= len(epochs):
            report["dropped"].append(
                {"input_index": idx, "reason": "out_of_range_after_sentence", "raw": callout.get("after_sentence")}
            )
            continue

        anchor_start = float(epochs[sent_idx].get("start_time", timeline_start))
        resolved = {
            "input_index": idx,
            "topic": topic,
            "after_sentence": sent_idx + 1,
            "anchor_start": round(anchor_start, 3),
        }
        report["resolved_anchors"].append(resolved)
        valid.append(resolved)

    report["valid_count"] = len(valid)
    if not valid:
        report["dropped_count"] = len(report["dropped"])
        return [], report

    available = max(0.8, timeline_end - timeline_start)
    adaptive_duration = available / float(max(1, len(valid)))
    card_duration = max(0.9, min(2.6, adaptive_duration * 0.6))
    gap = max(0.12, min(0.35, card_duration * 0.18))
    min_visible = 0.55

    report["card_duration_seconds"] = round(card_duration, 3)
    report["gap_seconds"] = round(gap, 3)

    scheduled = []
    cursor = timeline_start
    for item in valid:
        start = max(item["anchor_start"], cursor)
        end = min(start + card_duration, timeline_end)
        if (end - start) < min_visible:
            report["dropped"].append(
                {
                    "input_index": item["input_index"],
                    "topic": item["topic"],
                    "reason": "timeline_exhausted",
                    "anchor_start": item["anchor_start"],
                }
            )
            continue

        adjusted = abs(start - item["anchor_start"]) > 1e-4
        scheduled_item = {
            "input_index": item["input_index"],
            "topic": item["topic"],
            "after_sentence": item["after_sentence"],
            "anchor_start": item["anchor_start"],
            "start": round(start, 3),
            "end": round(end, 3),
            "adjusted": adjusted,
        }
        scheduled.append(scheduled_item)
        report["scheduled_windows"].append(scheduled_item)
        cursor = end + gap

    report["scheduled_count"] = len(scheduled)
    report["adjusted_count"] = sum(1 for item in scheduled if item.get("adjusted"))
    report["dropped_count"] = len(report["dropped"])
    return scheduled, report


def _duration_payload(node_input: LeadEditorInput) -> Dict[str, Any]:
    return {
        "duration_mode": node_input.duration_mode,
        "requested_target_duration_seconds": node_input.requested_target_duration_seconds,
        "estimated_duration_seconds": node_input.estimated_duration_seconds,
        "target_duration": node_input.target_duration,
        "actual_audio_duration_seconds": node_input.actual_audio_duration_seconds,
    }


def _build_ass_text(
    node_input: LeadEditorInput,
    services: LeadEditorServices,
    audio_duration: float,
) -> Tuple[str, Dict[str, Any]]:
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 1\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: ClassyBlurb,Arial,30,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,3,10,0,2,100,100,10,1\n"
        "Style: TopicCard,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&HB0000000,-1,0,0,0,100,100,2,0,4,12,0,8,400,400,10,1\n\n"
        f"Style: WatermarkTag,Arial,{services.watermark_font_size},&H0037D8FF,&H00FFC36E,&H004A0F2C,&H900A0415,-1,0,0,0,100,100,0,0,1,2,1,5,120,120,15,1\n"
        "Style: WatermarkLine,Arial,10,&H00FFC36E,&H0037D8FF,&H00301122,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    watermark_mode = services.normalize_watermark_mode(
        node_input.watermark_mode or services.watermark_mode_default
    )
    watermark_enabled = watermark_mode == "on"
    wm_text = "linkedin.com/in/nilhandemel"
    playres_x, playres_y = 1920, 1080
    wm_center_x, wm_center_y = playres_x // 2, playres_y // 2
    line_half_len = 306
    line_gap_from_text = 160
    line_thickness = 4
    accent_half_len = 61
    accent_gap_from_center = 40

    watermark_report: Dict[str, Any] = {
        "enabled": watermark_enabled,
        "mode": watermark_mode,
        "text": wm_text,
        "style": "WatermarkTag",
        "line_style": "WatermarkLine",
        "font_size": services.watermark_font_size,
        "playres": {"x": playres_x, "y": playres_y},
        "position": {"x": wm_center_x, "y": wm_center_y},
        "center_invariant": {
            "distance_from_top": wm_center_y,
            "distance_from_bottom": playres_y - wm_center_y,
            "is_equal": wm_center_y == (playres_y - wm_center_y),
        },
        "line_geometry": {},
        "timeline": {},
    }

    scheduled_cards, overlay_report = _schedule_topic_cards_one_at_a_time(
        node_input.topic_callouts,
        node_input.epochs,
        float(audio_duration),
    )
    if not isinstance(overlay_report, dict):
        overlay_report = {}

    lines = [header]
    for epoch in node_input.epochs:
        txt = str(epoch.get("text", "") or "").replace("\n", " ")
        lines.append(
            f"Dialogue: 0,{sec_to_ass(float(epoch['start_time']))},{sec_to_ass(float(epoch['end_time']))},ClassyBlurb,,0,0,0,,{txt}\n"
        )

    for card in scheduled_cards:
        lines.append(
            f"Dialogue: 1,{sec_to_ass(card['start'])},{sec_to_ass(card['end'])},TopicCard,,0,0,0,,{{\\fad(300,300)}}{card['topic']}\n"
        )

    if watermark_enabled:
        wm_start = float(node_input.epochs[0].get("start_time", 0.0)) if node_input.epochs else 0.0
        wm_end = max(wm_start + 0.05, float(audio_duration))
        if node_input.epochs:
            wm_end = max(wm_end, float(node_input.epochs[-1].get("end_time", wm_end)))

        main_y1 = wm_center_y - (line_thickness // 2)
        main_y2 = main_y1 + line_thickness
        left_x1 = wm_center_x - line_gap_from_text - line_half_len
        left_x2 = wm_center_x - line_gap_from_text
        right_x1 = wm_center_x + line_gap_from_text
        right_x2 = wm_center_x + line_gap_from_text + line_half_len

        accent_y1 = wm_center_y - 8
        accent_y2 = accent_y1 + 2
        left_accent_x1 = wm_center_x - accent_gap_from_center - accent_half_len
        left_accent_x2 = wm_center_x - accent_gap_from_center
        right_accent_x1 = wm_center_x + accent_gap_from_center
        right_accent_x2 = wm_center_x + accent_gap_from_center + accent_half_len

        watermark_report["timeline"] = {"start": round(wm_start, 3), "end": round(wm_end, 3)}
        watermark_report["line_geometry"] = {
            "main_left": {"x1": left_x1, "x2": left_x2, "y1": main_y1, "y2": main_y2},
            "main_right": {"x1": right_x1, "x2": right_x2, "y1": main_y1, "y2": main_y2},
            "accent_left": {"x1": left_accent_x1, "x2": left_accent_x2, "y1": accent_y1, "y2": accent_y2},
            "accent_right": {"x1": right_accent_x1, "x2": right_accent_x2, "y1": accent_y1, "y2": accent_y2},
        }

        lines.append(
            f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkTag,,0,0,0,,"
            f"{{\\an5\\pos({wm_center_x},{wm_center_y})\\blur0.8\\bord2\\shad1\\1c&H37D8FF&\\2c&HFFC36E&\\3c&H4A0F2C&\\4c&H900A0415&}}{wm_text}\n"
        )
        lines.append(
            f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
            f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&HFF9C62&\\alpha&H6A&}}m {left_x1} {main_y1} l {left_x2} {main_y1} l {left_x2} {main_y2} l {left_x1} {main_y2}\n"
        )
        lines.append(
            f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
            f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&HFF9C62&\\alpha&H6A&}}m {right_x1} {main_y1} l {right_x2} {main_y1} l {right_x2} {main_y2} l {right_x1} {main_y2}\n"
        )
        lines.append(
            f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
            f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H3CD8FF&\\alpha&H52&}}m {left_accent_x1} {accent_y1} l {left_accent_x2} {accent_y1} l {left_accent_x2} {accent_y2} l {left_accent_x1} {accent_y2}\n"
        )
        lines.append(
            f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
            f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H3CD8FF&\\alpha&H52&}}m {right_accent_x1} {accent_y1} l {right_accent_x2} {accent_y1} l {right_accent_x2} {accent_y2} l {right_accent_x1} {accent_y2}\n"
        )

    overlay_report["watermark"] = watermark_report
    return "".join(lines), overlay_report


def run_lead_editor(
    node_input: LeadEditorInput,
    services: LeadEditorServices,
) -> LeadEditorOutput:
    ass_path = services.artifacts.path("typography.ass")

    audio_duration_str = services.subprocess_getoutput(
        f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{node_input.audio_path}"'
    )
    try:
        audio_duration = float(str(audio_duration_str or "").strip())
    except ValueError:
        audio_duration = float(
            services.duration_meta_from_state(_duration_payload(node_input)).get(
                "effective_planning_duration_seconds",
                60,
            )
            or 60
        )

    ass_text, overlay_report = _build_ass_text(node_input, services, audio_duration)
    services.write_text_artifact("typography.ass", ass_text, mirror_legacy=None)
    services.artifacts.write_json("editor_overlay_report.json", overlay_report, mirror_legacy=None)

    asset_dir = services.artifacts.path("assets")
    os.makedirs(asset_dir, exist_ok=True)

    n = len(node_input.epochs)
    xfade = 0.5
    cmd = ["ffmpeg", "-y"]

    preflight_prev = ""
    for epoch in node_input.epochs:
        img_path = epoch.get("image_path")
        if not img_path or not os.path.exists(img_path):
            epoch_prefix = os.path.join(asset_dir, f"epoch_{epoch['id']:03d}_*png")
            matches = glob.glob(epoch_prefix)
            if matches:
                img_path = matches[0]
        if not img_path:
            img_path = os.path.join(asset_dir, f"epoch_{epoch['id']:03d}_placeholder.png")
        image_source = services.ensure_epoch_image_with_fallback(
            img_path,
            last_valid_path=preflight_prev,
            label=f"EDITOR-EPOCH-{epoch['id']:03d}",
        )
        epoch["image_path"] = img_path
        epoch["image_source"] = image_source
        if os.path.exists(img_path):
            preflight_prev = img_path

    for epoch in node_input.epochs:
        img_path = epoch.get("image_path")
        if img_path and os.path.exists(img_path):
            cmd += ["-i", img_path]
        else:
            raise RuntimeError(f"Editor preflight failed to materialize epoch image for {epoch['id']}")

    cmd += ["-i", node_input.audio_path]

    filt = []
    for i, epoch in enumerate(node_input.epochs):
        dur = float(epoch["duration"])
        if i < n - 1:
            dur += xfade
        frames = int(round(dur * 30))
        filt.append(
            f"[{i}:v]scale=1920:1080,zoompan=z='min(zoom+0.0003,1.05)':d={frames}"
            f":s=1920x1080:fps=30,setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )

    prev = "v0"
    for i in range(1, n):
        nxt = f"xf{i}"
        offset = round(float(node_input.epochs[i]["start_time"]), 3)
        filt.append(f"[{prev}][v{i}]xfade=transition=fade:duration={xfade}:offset={offset}[{nxt}]")
        prev = nxt

    rel_ass = os.path.relpath(ass_path, services.project_dir).replace("\\", "/")
    filt.append(f"[{prev}]ass='{rel_ass}'[outv]")

    filt_script = services.write_text_artifact("filter.txt", ";\n".join(filt), mirror_legacy=None)

    cmd += [
        "-filter_complex_script",
        filt_script,
        "-map",
        "[outv]",
        "-map",
        f"{len(node_input.epochs)}:a",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        node_input.target_output,
    ]

    try:
        services.subprocess_run(cmd, cwd=services.project_dir, check=True, capture_output=True)
        return LeadEditorOutput(status="rendered", final_video=node_input.target_output)
    except subprocess.CalledProcessError as exc:
        return LeadEditorOutput(
            status="render_failed",
            errors=[f"FFmpeg failed: {exc.stderr.decode()[-200:]}"],
        )
