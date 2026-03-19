"""
TVC post-production project model and editor helpers.

This module builds an editable project layer after initial render:
- text layers (subtitles/callouts/additional overlays)
- media slots (epoch image replacements)
- deterministic post render
- bounded Ralph correction loop
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    Image = None
    ImageDraw = None


PROJECT_SCHEMA_VERSION = 1


TEXT_STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "Clean Lower Third": {"anchor": "bottom", "effect": "fade"},
    "News Strap": {"anchor": "bottom", "effect": "slide_up"},
    "Breaking Banner": {"anchor": "top", "effect": "slide_down"},
    "Kinetic Word Pop": {"anchor": "center", "effect": "scale_pop"},
    "Typewriter Reveal": {"anchor": "bottom", "effect": "type"},
    "Fade Caption": {"anchor": "bottom", "effect": "fade"},
    "Slide Left Caption": {"anchor": "bottom", "effect": "slide_left"},
    "Slide Right Caption": {"anchor": "bottom", "effect": "slide_right"},
    "Rise From Bottom": {"anchor": "bottom", "effect": "slide_up"},
    "Drop From Top": {"anchor": "top", "effect": "slide_down"},
    "Scale In Emphasis": {"anchor": "center", "effect": "scale_pop"},
    "Blur In Focus": {"anchor": "center", "effect": "fade"},
    "Glow Headline": {"anchor": "top", "effect": "fade"},
    "Split-Line Headline": {"anchor": "top", "effect": "slide_down"},
    "Corner Tag": {"anchor": "top_left", "effect": "fade"},
    "Quote Card": {"anchor": "center", "effect": "fade"},
    "Stat Block": {"anchor": "top_right", "effect": "slide_left"},
    "Timeline Marker": {"anchor": "bottom", "effect": "slide_up"},
    "Bullet Stack": {"anchor": "left", "effect": "slide_right"},
    "Ticker Crawl": {"anchor": "bottom", "effect": "ticker"},
}


def list_text_styles() -> List[str]:
    return sorted(TEXT_STYLE_PRESETS.keys())


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _write_json(path: str, payload: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)


def _ffprobe_duration(path: str) -> float:
    if not path or not os.path.exists(path):
        return 0.0
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        return float(out)
    except Exception:
        return 0.0


def _sanitize_text(text: str) -> str:
    return str(text or "").replace("\n", " ").replace("\r", " ").strip()


def _sec_to_ass(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ensure_placeholder_image(path: str, label: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if Image is None:
        raise RuntimeError("Pillow is required for placeholder generation")
    _ = label
    img = Image.new("RGB", (1920, 1080), (10, 18, 36))
    draw = ImageDraw.Draw(img)
    draw.rectangle((80, 80, 1840, 1000), outline=(110, 130, 180), width=4)
    draw.rectangle((760, 500, 1160, 580), fill=(24, 36, 66))
    img.save(path)


def _project_dir_from_run(run_dir: str) -> str:
    return os.path.join(run_dir, "postproduction")


def _resolve_epoch_image(assets_dir: str, epoch_id: int) -> str:
    pattern = os.path.join(assets_dir, f"epoch_{int(epoch_id):03d}_*.png")
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else ""


def list_completed_runs(project_root: str, limit: int = 60, only_with_output: bool = True) -> List[Dict[str, Any]]:
    runs_root = os.path.join(project_root, "tvc_multi_agent_db", "runs")
    if not os.path.isdir(runs_root):
        return []
    rows: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(runs_root), reverse=True):
        run_dir = os.path.join(runs_root, name)
        if not os.path.isdir(run_dir):
            continue
        manifest = _read_json(os.path.join(run_dir, "run_manifest.json"), {})
        vr = _read_json(os.path.join(run_dir, "verification_report.json"), {})
        output = str(manifest.get("target_output", "") or "")
        rows.append(
            {
                "run_id": name,
                "run_dir": run_dir,
                "timestamp": manifest.get("timestamp", ""),
                "output_video": output,
                "output_exists": bool(output and os.path.exists(output)),
                "verified": vr.get("verified"),
                "telemetry_pass": vr.get("telemetry_pass"),
                "video_duration": vr.get("video_duration"),
            }
        )
        if only_with_output and not rows[-1]["output_exists"]:
            rows.pop()
            continue
        if len(rows) >= int(limit):
            break
    return rows


def create_post_project(project_root: str, run_id: str, project_name: str = "") -> str:
    run_dir = os.path.join(project_root, "tvc_multi_agent_db", "runs", run_id)
    if not os.path.isdir(run_dir):
        raise FileNotFoundError(f"Run not found: {run_id}")

    manifest = _read_json(os.path.join(run_dir, "run_manifest.json"), {})
    epochs = _read_json(os.path.join(run_dir, "vtt_matrix.json"), [])
    callouts = _read_json(os.path.join(run_dir, "topic_callouts.json"), [])
    vr = _read_json(os.path.join(run_dir, "verification_report.json"), {})
    audio_path = os.path.join(run_dir, "master_narration.mp3")
    base_video = str(manifest.get("target_output", "") or "")
    if not base_video or not os.path.exists(base_video):
        candidates = sorted(
            [
                os.path.join(run_dir, f)
                for f in os.listdir(run_dir)
                if f.lower().endswith(".mp4") and not f.lower().startswith("post_output_")
            ]
        )
        if candidates:
            base_video = candidates[-1]
    if not base_video or not os.path.exists(base_video):
        raise FileNotFoundError(f"Base video for run is missing: {run_id}")
    duration = float(vr.get("video_duration", 0.0) or 0.0) or _ffprobe_duration(base_video)

    assets_dir = os.path.join(run_dir, "assets")
    media_slots: List[Dict[str, Any]] = []
    for ep in epochs:
        ep_id = int(ep.get("id", len(media_slots) + 1) or (len(media_slots) + 1))
        img_path = _resolve_epoch_image(assets_dir, ep_id)
        media_slots.append(
            {
                "slot_id": f"epoch-{ep_id:03d}",
                "epoch_id": ep_id,
                "start": float(ep.get("start_time", 0.0) or 0.0),
                "end": float(ep.get("end_time", 0.0) or 0.0),
                "image_path": img_path,
                "original_image_path": img_path,
                "changed": False,
            }
        )

    text_layers: List[Dict[str, Any]] = []
    for ep in epochs:
        ep_id = int(ep.get("id", len(text_layers) + 1) or (len(text_layers) + 1))
        text_layers.append(
            {
                "id": f"subtitle-{ep_id:03d}",
                "track": "subtitle",
                "text": _sanitize_text(ep.get("text", "")),
                "style": "Fade Caption",
                "start": float(ep.get("start_time", 0.0) or 0.0),
                "end": float(ep.get("end_time", 0.0) or 0.0),
                "params": {
                    "font_size": 40,
                    "color": "FFFFFF",
                    "outline": 3,
                    "shadow": 1,
                    "entry_ms": 180,
                    "exit_ms": 180,
                    "x": 960,
                    "y": 980,
                },
            }
        )
    for idx, c in enumerate(callouts, start=1):
        after_sentence = int(c.get("after_sentence", 1) or 1)
        sent_idx = max(0, min(after_sentence - 1, max(0, len(epochs) - 1)))
        st = float(epochs[sent_idx].get("start_time", 0.0) or 0.0) if epochs else 0.0
        ed = min(duration, st + 2.8)
        text_layers.append(
            {
                "id": f"callout-{idx:03d}",
                "track": "callout",
                "text": _sanitize_text(c.get("topic", "")),
                "style": "News Strap",
                "start": st,
                "end": ed,
                "params": {
                    "font_size": 52,
                    "color": "FFFFFF",
                    "outline": 5,
                    "shadow": 2,
                    "entry_ms": 240,
                    "exit_ms": 240,
                    "x": 960,
                    "y": 150,
                },
            }
        )

    pp_dir = _project_dir_from_run(run_dir)
    os.makedirs(pp_dir, exist_ok=True)
    project_path = os.path.join(pp_dir, "post_project.json")
    project = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project_name": project_name or f"TVC Post Project {run_id}",
        "created_at": _now(),
        "updated_at": _now(),
        "run_id": run_id,
        "run_dir": run_dir,
        "project_root": project_root,
        "base_video": base_video,
        "audio_path": audio_path if os.path.exists(audio_path) else "",
        "duration": duration,
        "output_video": os.path.join(pp_dir, f"post_output_{run_id}.mp4"),
        "base_recut_video": os.path.join(pp_dir, f"recut_base_{run_id}.mp4"),
        "ass_path": os.path.join(pp_dir, f"post_overlay_{run_id}.ass"),
        "text_style_presets": list_text_styles(),
        "text_layers": text_layers,
        "media_slots": media_slots,
        "feature_layers": [],
    }
    _write_json(project_path, project)
    return project_path


def load_project(project_path: str) -> Dict[str, Any]:
    data = _read_json(project_path, {})
    if not data:
        raise FileNotFoundError(f"Project not found: {project_path}")
    return data


def save_project(project_path: str, project: Dict[str, Any]):
    project["updated_at"] = _now()
    _write_json(project_path, project)


def list_text_layers(project_path: str) -> List[Dict[str, Any]]:
    project = load_project(project_path)
    rows: List[Dict[str, Any]] = []
    for idx, layer in enumerate(project.get("text_layers", [])):
        rows.append(
            {
                "index": idx,
                "id": str(layer.get("id", "")),
                "track": str(layer.get("track", "")),
                "style": str(layer.get("style", "")),
                "start": float(layer.get("start", 0.0) or 0.0),
                "end": float(layer.get("end", 0.0) or 0.0),
                "text": str(layer.get("text", "")),
            }
        )
    return rows


def reorder_text_layers(project_path: str, ordered_layer_ids: List[str]) -> Dict[str, Any]:
    project = load_project(project_path)
    layers = list(project.get("text_layers", []))
    by_id = {str(x.get("id", "")): x for x in layers}
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in ordered_layer_ids:
        key = str(raw or "")
        if key and key in by_id and key not in seen:
            out.append(by_id[key])
            seen.add(key)
    for layer in layers:
        key = str(layer.get("id", ""))
        if key not in seen:
            out.append(layer)
    project["text_layers"] = out
    save_project(project_path, project)
    return {"status": "ok", "layer_count": len(out)}


def replace_epoch_image(project_path: str, epoch_id: int, image_path: str) -> Dict[str, Any]:
    project = load_project(project_path)
    image_path = os.path.abspath(image_path)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Replacement image missing: {image_path}")
    found = False
    for slot in project.get("media_slots", []):
        if int(slot.get("epoch_id", -1)) == int(epoch_id):
            slot["image_path"] = image_path
            slot["changed"] = True
            found = True
            break
    if not found:
        raise ValueError(f"Epoch slot not found: {epoch_id}")
    save_project(project_path, project)
    return {"status": "ok", "epoch_id": int(epoch_id), "image_path": image_path}


def update_text_layer(
    project_path: str,
    layer_id: str,
    text: Optional[str] = None,
    style: Optional[str] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    project = load_project(project_path)
    target = None
    for layer in project.get("text_layers", []):
        if str(layer.get("id", "")) == str(layer_id):
            target = layer
            break
    if target is None:
        raise ValueError(f"Layer not found: {layer_id}")
    if text is not None:
        target["text"] = _sanitize_text(text)
    if style is not None:
        if style not in TEXT_STYLE_PRESETS:
            raise ValueError(f"Unknown style: {style}")
        target["style"] = style
    if start is not None:
        target["start"] = float(start)
    if end is not None:
        target["end"] = float(end)
    if params:
        merged = dict(target.get("params", {}))
        merged.update(params)
        target["params"] = merged
    save_project(project_path, project)
    return {"status": "ok", "layer_id": layer_id}


def _build_ass_override(layer: Dict[str, Any]) -> str:
    style_name = str(layer.get("style", "Fade Caption"))
    style_cfg = TEXT_STYLE_PRESETS.get(style_name, TEXT_STYLE_PRESETS["Fade Caption"])
    p = dict(layer.get("params", {}))
    x = int(p.get("x", 960))
    y = int(p.get("y", 980))
    fs = int(p.get("font_size", 42))
    color = str(p.get("color", "FFFFFF")).strip().upper().replace("#", "")
    if len(color) != 6:
        color = "FFFFFF"
    outline = int(p.get("outline", 3))
    shadow = int(p.get("shadow", 1))
    opacity = int(p.get("opacity", 100))
    blur = float(p.get("blur", 0.6))
    offset_x = int(p.get("offset_x", 0))
    offset_y = int(p.get("offset_y", 0))
    entry_ms = int(p.get("entry_ms", 180))
    exit_ms = int(p.get("exit_ms", 180))
    effect = style_cfg.get("effect", "fade")
    x += offset_x
    y += offset_y
    opacity = max(0, min(100, opacity))
    alpha_val = int(round((100 - opacity) * 2.55))
    alpha_hex = f"{alpha_val:02X}"
    base = f"\\fs{fs}\\c&H{color}&\\alpha&H{alpha_hex}&\\bord{outline}\\shad{shadow}\\blur{blur:.2f}"

    if effect == "fade":
        return f"{{\\an2\\pos({x},{y}){base}\\fad({entry_ms},{exit_ms})}}"
    if effect == "slide_left":
        return f"{{\\an2\\move({x+500},{y},{x},{y}){base}\\fad({entry_ms},{exit_ms})}}"
    if effect == "slide_right":
        return f"{{\\an2\\move({x-500},{y},{x},{y}){base}\\fad({entry_ms},{exit_ms})}}"
    if effect == "slide_up":
        return f"{{\\an2\\move({x},{y+220},{x},{y}){base}\\fad({entry_ms},{exit_ms})}}"
    if effect == "slide_down":
        return f"{{\\an2\\move({x},{y-220},{x},{y}){base}\\fad({entry_ms},{exit_ms})}}"
    if effect == "scale_pop":
        return f"{{\\an5\\pos({x},{y}){base}\\fscx80\\fscy80\\t(0,220,\\fscx100\\fscy100)\\fad({entry_ms},{exit_ms})}}"
    if effect == "ticker":
        return f"{{\\an2\\move(2050,{y},-400,{y}){base}}}"
    if effect == "type":
        # ASS has no native typewriter without karaoke syllables; use gentle fade fallback.
        return f"{{\\an2\\pos({x},{y}){base}\\fad({entry_ms},{exit_ms})}}"
    return f"{{\\an2\\pos({x},{y}){base}\\fad({entry_ms},{exit_ms})}}"


def _write_ass_overlay(project: Dict[str, Any], ass_path: str):
    os.makedirs(os.path.dirname(ass_path), exist_ok=True)
    header = (
        "[Script Info]\n"
        "Title: TVC Post Overlay\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: PostText,Arial,42,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,45,1\n\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(header)
        layers = sorted(project.get("text_layers", []), key=lambda x: float(x.get("start", 0.0) or 0.0))
        for layer in layers:
            st = float(layer.get("start", 0.0) or 0.0)
            ed = float(layer.get("end", st + 1.0) or (st + 1.0))
            if ed <= st:
                continue
            text = _sanitize_text(layer.get("text", ""))
            if not text:
                continue
            override = _build_ass_override(layer)
            fh.write(f"Dialogue: 2,{_sec_to_ass(st)},{_sec_to_ass(ed)},PostText,,0,0,0,,{override}{text}\n")


def _build_recut_from_media_slots(project: Dict[str, Any], out_path: str) -> str:
    slots = sorted(project.get("media_slots", []), key=lambda s: float(s.get("start", 0.0) or 0.0))
    if not slots:
        return str(project.get("base_video", ""))
    temp_dir = os.path.join(os.path.dirname(out_path), "_recut_tmp")
    os.makedirs(temp_dir, exist_ok=True)
    dur_fallback = max(1.0, float(project.get("duration", 1.0) or 1.0) / max(1, len(slots)))
    clips: List[str] = []
    for idx, slot in enumerate(slots, start=1):
        st = float(slot.get("start", 0.0) or 0.0)
        ed = float(slot.get("end", st + dur_fallback) or (st + dur_fallback))
        dur = max(0.4, ed - st)
        img = str(slot.get("image_path", "") or "")
        if not img or not os.path.exists(img):
            img = os.path.join(temp_dir, f"epoch_{idx:03d}_placeholder.png")
            _ensure_placeholder_image(img, f"EPOCH {idx:03d}")
            slot["image_path"] = img
            slot["changed"] = True
        clip = os.path.join(temp_dir, f"clip_{idx:03d}.mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-i",
            img,
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            clip,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        clips.append(clip)

    concat_list = os.path.join(temp_dir, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as fh:
        for clip in clips:
            safe_clip = clip.replace("'", "''")
            fh.write(f"file '{safe_clip}'\n")
    concat_out = os.path.join(temp_dir, "base_concat.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", concat_out],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    audio = str(project.get("audio_path", "") or "")
    if audio and os.path.exists(audio):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                concat_out,
                "-i",
                audio,
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                out_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        shutil.copy2(concat_out, out_path)
    return out_path


def render_post_project(project_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    project = load_project(project_path)
    base_video = str(project.get("base_video", "") or "")
    if not os.path.exists(base_video):
        raise FileNotFoundError(f"Base video missing: {base_video}")
    out_video = output_path or str(project.get("output_video", "") or "")
    if not out_video:
        out_video = os.path.join(os.path.dirname(project_path), "post_output.mp4")
    ass_path = str(project.get("ass_path", "") or os.path.join(os.path.dirname(project_path), "post_overlay.ass"))
    needs_recut = any(bool(s.get("changed")) for s in project.get("media_slots", []))
    source_video = base_video
    if needs_recut:
        recut_path = str(project.get("base_recut_video", "") or os.path.join(os.path.dirname(project_path), "recut_base.mp4"))
        source_video = _build_recut_from_media_slots(project, recut_path)
        project["base_recut_video"] = source_video

    _write_ass_overlay(project, ass_path)
    os.makedirs(os.path.dirname(out_video), exist_ok=True)
    ass_dir = os.path.dirname(ass_path) or os.getcwd()
    ass_name = os.path.basename(ass_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        source_video,
        "-vf",
        f"ass={ass_name}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "copy",
        out_video,
    ]
    try:
        subprocess.run(cmd, cwd=ass_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        err = str(exc.stderr or "").strip()
        raise RuntimeError(f"Post-production ffmpeg render failed: {err[:1200]}") from exc

    project["output_video"] = out_video
    project["ass_path"] = ass_path
    project["last_render"] = {
        "timestamp": _now(),
        "source_video": source_video,
        "output_video": out_video,
        "needs_recut": needs_recut,
    }
    save_project(project_path, project)
    return {"status": "ok", "output_video": out_video, "source_video": source_video}


def _check_project_integrity(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    duration = float(project.get("duration", 0.0) or 0.0)
    for slot in project.get("media_slots", []):
        st = float(slot.get("start", 0.0) or 0.0)
        ed = float(slot.get("end", 0.0) or 0.0)
        if ed <= st:
            issues.append({"type": "slot_invalid_window", "slot_id": slot.get("slot_id"), "start": st, "end": ed})
        img = str(slot.get("image_path", "") or "")
        if not img or not os.path.exists(img):
            issues.append({"type": "slot_missing_image", "slot_id": slot.get("slot_id")})
        if duration and st > duration:
            issues.append({"type": "slot_out_of_duration", "slot_id": slot.get("slot_id"), "start": st})

    layers = sorted(project.get("text_layers", []), key=lambda x: float(x.get("start", 0.0) or 0.0))
    for i, layer in enumerate(layers):
        st = float(layer.get("start", 0.0) or 0.0)
        ed = float(layer.get("end", 0.0) or 0.0)
        if ed <= st:
            issues.append({"type": "layer_invalid_window", "layer_id": layer.get("id"), "start": st, "end": ed})
        if duration and ed > duration + 0.01:
            issues.append({"type": "layer_out_of_duration", "layer_id": layer.get("id"), "end": ed, "duration": duration})
        if i > 0:
            prev = layers[i - 1]
            prev_ed = float(prev.get("end", 0.0) or 0.0)
            if str(prev.get("track", "")) == str(layer.get("track", "")) and st < prev_ed:
                issues.append(
                    {
                        "type": "layer_overlap_same_track",
                        "prev_layer": prev.get("id"),
                        "layer_id": layer.get("id"),
                    }
                )

    out_video = str(project.get("output_video", "") or "")
    audio = str(project.get("audio_path", "") or "")
    if out_video and os.path.exists(out_video) and audio and os.path.exists(audio):
        drift = abs(_ffprobe_duration(out_video) - _ffprobe_duration(audio))
        if drift > 1.0:
            issues.append({"type": "verifier_drift", "drift_s": drift})
    return issues


def _repair_project(project: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    actions: List[Dict[str, Any]] = []
    duration = max(0.0, float(project.get("duration", 0.0) or 0.0))
    pp_dir = os.path.dirname(str(project.get("output_video", "") or "")) or os.path.dirname(str(project.get("ass_path", "") or ""))

    # Repair media slots
    prev_image = ""
    slots = sorted(project.get("media_slots", []), key=lambda s: float(s.get("start", 0.0) or 0.0))
    cursor = 0.0
    for idx, slot in enumerate(slots, start=1):
        st = max(0.0, float(slot.get("start", 0.0) or 0.0))
        ed = max(st + 0.4, float(slot.get("end", st + 0.4) or (st + 0.4)))
        if st < cursor:
            st = cursor
        if duration and ed > duration:
            ed = duration
        slot["start"] = st
        slot["end"] = ed
        cursor = ed

        img = str(slot.get("image_path", "") or "")
        if not img or not os.path.exists(img):
            if prev_image and os.path.exists(prev_image):
                slot["image_path"] = prev_image
                slot["changed"] = True
                actions.append({"action": "copy_previous_image", "slot_id": slot.get("slot_id")})
            else:
                ph = os.path.join(pp_dir, f"placeholder_{idx:03d}.png")
                _ensure_placeholder_image(ph, f"SLOT {idx:03d}")
                slot["image_path"] = ph
                slot["changed"] = True
                actions.append({"action": "create_placeholder_image", "slot_id": slot.get("slot_id"), "path": ph})
        prev_image = str(slot.get("image_path", "") or prev_image)
    project["media_slots"] = slots

    # Repair text layers
    layers = sorted(project.get("text_layers", []), key=lambda x: float(x.get("start", 0.0) or 0.0))
    last_by_track: Dict[str, float] = {}
    for layer in layers:
        track = str(layer.get("track", "overlay"))
        st = max(0.0, float(layer.get("start", 0.0) or 0.0))
        ed = max(st + 0.3, float(layer.get("end", st + 0.3) or (st + 0.3)))
        if duration and ed > duration:
            ed = duration
        prev_end = float(last_by_track.get(track, -1.0))
        if st < prev_end:
            gap = 0.12
            st = prev_end + gap
            ed = max(st + 0.3, ed + gap)
            if duration and ed > duration:
                ed = duration
            actions.append({"action": "shift_layer_to_avoid_overlap", "layer_id": layer.get("id"), "track": track})
        layer["start"] = st
        layer["end"] = ed
        last_by_track[track] = ed
    project["text_layers"] = layers
    return project, actions


def run_ralph_loop(project_path: str, max_loops: int = 4) -> Dict[str, Any]:
    project = load_project(project_path)
    max_loops = max(1, int(max_loops))
    loop_rows: List[Dict[str, Any]] = []
    final_status = "failed"
    output_video = str(project.get("output_video", "") or "")
    for idx in range(1, max_loops + 1):
        issues = _check_project_integrity(project)
        row: Dict[str, Any] = {"loop": idx, "issues": issues, "actions": []}
        if not issues:
            final_status = "passed"
            loop_rows.append(row)
            break
        project, actions = _repair_project(project)
        row["actions"] = actions
        save_project(project_path, project)
        try:
            render = render_post_project(project_path)
            output_video = str(render.get("output_video", output_video))
            row["render_status"] = "ok"
            row["output_video"] = output_video
        except Exception as exc:
            row["render_status"] = "failed"
            row["render_error"] = str(exc)
            loop_rows.append(row)
            final_status = "failed"
            break
        project = load_project(project_path)
        loop_rows.append(row)

    report = {
        "timestamp": _now(),
        "project_path": project_path,
        "max_loops": max_loops,
        "status": final_status,
        "loops": loop_rows,
        "output_video": output_video,
    }
    report_path = os.path.join(os.path.dirname(project_path), "ralph_loop_report.json")
    _write_json(report_path, report)
    return report


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("--run-id", required=True)
    p_create.add_argument("--name", default="")

    p_render = sub.add_parser("render")
    p_render.add_argument("--project", required=True)
    p_render.add_argument("--output", default="")

    p_replace = sub.add_parser("replace-image")
    p_replace.add_argument("--project", required=True)
    p_replace.add_argument("--epoch-id", type=int, required=True)
    p_replace.add_argument("--image", required=True)

    p_layer = sub.add_parser("edit-layer")
    p_layer.add_argument("--project", required=True)
    p_layer.add_argument("--layer-id", required=True)
    p_layer.add_argument("--text", default=None)
    p_layer.add_argument("--style", default=None)

    p_reorder = sub.add_parser("reorder-layers")
    p_reorder.add_argument("--project", required=True)
    p_reorder.add_argument("--layer-ids", required=True, nargs="+")

    p_ralph = sub.add_parser("ralph")
    p_ralph.add_argument("--project", required=True)
    p_ralph.add_argument("--max-loops", type=int, default=4)

    args = parser.parse_args()
    root = os.path.abspath(args.project_root)
    if args.command == "create":
        print(create_post_project(root, args.run_id, project_name=args.name))
        return 0
    if args.command == "render":
        out = render_post_project(args.project, output_path=(args.output or None))
        print(json.dumps(out, indent=2))
        return 0
    if args.command == "replace-image":
        out = replace_epoch_image(args.project, args.epoch_id, args.image)
        print(json.dumps(out, indent=2))
        return 0
    if args.command == "edit-layer":
        out = update_text_layer(args.project, args.layer_id, text=args.text, style=args.style)
        print(json.dumps(out, indent=2))
        return 0
    if args.command == "reorder-layers":
        out = reorder_text_layers(args.project, args.layer_ids)
        print(json.dumps(out, indent=2))
        return 0
    if args.command == "ralph":
        out = run_ralph_loop(args.project, max_loops=args.max_loops)
        print(json.dumps(out, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
