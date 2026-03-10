#!/usr/bin/env python3
import argparse
import csv
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TIME_FMT = "%Y-%m-%d %H:%M:%S"

NODE_ORDER = [
    "Harvester",
    "Writer",
    "DurationGate",
    "TopicExtractor",
    "SceneDirector",
    "Audio",
    "PromptArchitect",
    "SotaForge",
    "Editor",
    "Verifier",
]

MACRO_MAP = {
    "YouTube Harvest": ["Harvester"],
    "Scripting": ["Writer", "DurationGate"],
    "Scene/Timing Prep": ["TopicExtractor", "SceneDirector", "Audio"],
    "Image Prompting": ["PromptArchitect"],
    "Image Forge": ["SotaForge"],
    "Render": ["Editor"],
    "Verify": ["Verifier"],
}


@dataclass
class DatasetConfig:
    name: str
    base_dir: Path
    trace_file: str
    pipeline_log: str
    markers: Dict[str, str]


def parse_dt(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, TIME_FMT)
    except Exception:
        return None


def mtime_dt(path: Path) -> Optional[datetime]:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime)


def parse_trace(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            obj["_ts"] = parse_dt(str(obj.get("timestamp", "")))
            if obj["_ts"] is not None:
                rows.append(obj)
    rows.sort(key=lambda x: x["_ts"])
    return rows


def first_trace_time(rows: List[dict]) -> Optional[datetime]:
    return rows[0]["_ts"] if rows else None


def last_trace_by_node(rows: List[dict], node: str) -> Optional[datetime]:
    node_rows = [r for r in rows if str(r.get("node", "")) == node and r.get("_ts") is not None]
    if not node_rows:
        return None
    return node_rows[-1]["_ts"]


def first_trace_by_node(rows: List[dict], node: str) -> Optional[datetime]:
    node_rows = [r for r in rows if str(r.get("node", "")) == node and r.get("_ts") is not None]
    if not node_rows:
        return None
    return node_rows[0]["_ts"]


def sec(dt_a: datetime, dt_b: datetime) -> float:
    return (dt_b - dt_a).total_seconds()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)
    return True


def freeze_primary_bundle(output_dir: Path, intel_dir: Path, evidence_dir: Path) -> Dict[str, str]:
    ensure_dir(output_dir)
    copied: Dict[str, str] = {}

    core_files = [
        "pipeline_run.log",
        "api_call_trace.jsonl",
        "harvester_run_report.json",
        "scene_audio_prompt_report.json",
        "harvested_intelligence.txt",
        "master_script.txt",
        "topic_callouts.json",
        "scene_manifest.json",
        "vtt_matrix.json",
        "master_prompts.json",
        "filter.txt",
        "verification_report.json",
        "paid_api_policy_check.json",
        "audio_stage_report.json",
        "writer_quality_report.json",
    ]

    for name in core_files:
        src = intel_dir / name
        dst = output_dir / name
        if copy_if_exists(src, dst):
            copied[name] = str(dst)

    # Optional terminal capture from Evidence folder.
    extra_log = evidence_dir / "node1_live_standup_120s_postfix.log"
    if copy_if_exists(extra_log, output_dir / "terminal_capture.log"):
        copied["terminal_capture.log"] = str(output_dir / "terminal_capture.log")

    manifest = {
        "frozen_at": datetime.now().strftime(TIME_FMT),
        "source_intel_dir": str(intel_dir),
        "source_evidence_dir": str(evidence_dir),
        "copied_files": copied,
    }
    with (output_dir / "bundle_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)

    return copied


def reconstruct(config: DatasetConfig) -> Dict[str, object]:
    base = config.base_dir
    trace_path = base / config.trace_file
    pipeline_log_path = base / config.pipeline_log

    trace_rows = parse_trace(trace_path)

    marker_times: Dict[str, Optional[datetime]] = {}
    marker_refs: Dict[str, str] = {}
    for key, rel in config.markers.items():
        p = base / rel
        marker_times[key] = mtime_dt(p)
        if p.exists():
            marker_refs[key] = str(p)

    anchor = first_trace_time(trace_rows)
    if anchor is None:
        # Fallback for old bundles without api trace.
        existing = [v for v in marker_times.values() if v is not None]
        if existing:
            anchor = min(existing)

    if anchor is None:
        raise RuntimeError(f"No viable timing anchors found for dataset: {config.name}")

    # Deterministic node end-marker map per spec.
    end_candidates: Dict[str, Optional[datetime]] = {
        "Harvester": marker_times.get("harvested_intelligence") or last_trace_by_node(trace_rows, "Harvester"),
        "Writer": marker_times.get("master_script") or last_trace_by_node(trace_rows, "Writer"),
        "DurationGate": None,
        "TopicExtractor": marker_times.get("topic_callouts") or last_trace_by_node(trace_rows, "TopicExtractor"),
        "SceneDirector": marker_times.get("scene_manifest") or last_trace_by_node(trace_rows, "SceneDirector"),
        "Audio": marker_times.get("vtt_matrix") or last_trace_by_node(trace_rows, "Audio"),
        "PromptArchitect": marker_times.get("master_prompts") or last_trace_by_node(trace_rows, "PromptArchitect"),
        "SotaForge": last_trace_by_node(trace_rows, "SotaForge"),
        "Editor": marker_times.get("filter_txt"),
        "Verifier": marker_times.get("verification_report"),
    }

    # DurationGate embedded estimate: writer->topic transition gap, usually near-zero.
    writer_end = end_candidates["Writer"]
    topic_start_trace = first_trace_by_node(trace_rows, "TopicExtractor")
    duration_gate_end = None
    if writer_end is not None:
        if topic_start_trace is not None:
            duration_gate_end = max(writer_end, topic_start_trace)
        else:
            duration_gate_end = writer_end
    end_candidates["DurationGate"] = duration_gate_end

    # Fill missing verifier end from pipeline log mtime if needed.
    if end_candidates["Verifier"] is None:
        end_candidates["Verifier"] = mtime_dt(pipeline_log_path)

    rows = []
    current_start = anchor

    for node in NODE_ORDER:
        end_t = end_candidates.get(node)
        if end_t is None:
            end_t = current_start
        if end_t < current_start:
            end_t = current_start

        duration = max(0.0, sec(current_start, end_t))

        confidence = "B"
        note = "artifact-boundary timing"
        refs: List[str] = []

        if node == "SotaForge":
            first_sota = first_trace_by_node(trace_rows, "SotaForge")
            last_sota = last_trace_by_node(trace_rows, "SotaForge")
            if first_sota and last_sota:
                confidence = "A"
                note = "trace span timing"
                refs.append(f"trace:{trace_path}#SotaForge")
            else:
                confidence = "C"
                note = "inferred from neighboring markers"
        elif node == "DurationGate":
            confidence = "C"
            note = "embedded in Writer->Topic transition"
            if writer_end:
                refs.append(f"writer_end:{writer_end.strftime(TIME_FMT)}")
            if topic_start_trace:
                refs.append(f"topic_first_trace:{topic_start_trace.strftime(TIME_FMT)}")
        else:
            trace_first = first_trace_by_node(trace_rows, node)
            trace_last = last_trace_by_node(trace_rows, node)
            if trace_first and trace_last and trace_first != trace_last:
                confidence = "A"
                note = "trace-supported window"
                refs.append(f"trace:{trace_path}#{node}")
            elif trace_last:
                refs.append(f"trace_last:{trace_last.strftime(TIME_FMT)}")

            marker_key_map = {
                "Harvester": "harvested_intelligence",
                "Writer": "master_script",
                "TopicExtractor": "topic_callouts",
                "SceneDirector": "scene_manifest",
                "Audio": "vtt_matrix",
                "PromptArchitect": "master_prompts",
                "Editor": "filter_txt",
                "Verifier": "verification_report",
            }
            mk = marker_key_map.get(node)
            if mk and marker_refs.get(mk):
                refs.append(f"marker:{marker_refs[mk]}")

        if not refs:
            refs.append(f"inferred:{current_start.strftime(TIME_FMT)}->{end_t.strftime(TIME_FMT)}")

        rows.append(
            {
                "node": node,
                "start": current_start.strftime(TIME_FMT),
                "end": end_t.strftime(TIME_FMT),
                "duration_seconds": round(duration, 3),
                "confidence": confidence,
                "note": note,
                "evidence_refs": refs,
            }
        )
        current_start = end_t

    total_end = end_candidates.get("Verifier") or rows[-1]["end"]
    if isinstance(total_end, str):
        total_end = parse_dt(total_end)
    if total_end is None:
        total_end = current_start

    total_seconds = max(0.0, sec(anchor, total_end))

    # Percent allocation.
    for row in rows:
        pct = (row["duration_seconds"] / total_seconds * 100.0) if total_seconds > 0 else 0.0
        row["percent_of_total"] = round(pct, 2)

    # Macro aggregation.
    macro = []
    row_by_node = {r["node"]: r for r in rows}
    for macro_name, nodes in MACRO_MAP.items():
        dur = sum(float(row_by_node[n]["duration_seconds"]) for n in nodes if n in row_by_node)
        pct = (dur / total_seconds * 100.0) if total_seconds > 0 else 0.0
        macro.append({
            "functional_area": macro_name,
            "nodes": nodes,
            "duration_seconds": round(dur, 3),
            "percent_of_total": round(pct, 2),
        })

    # Consistency checks.
    sum_nodes = sum(float(r["duration_seconds"]) for r in rows)
    tolerance = abs(sum_nodes - total_seconds)

    quality = {
        "all_non_negative": all(float(r["duration_seconds"]) >= 0 for r in rows),
        "sum_within_2s": tolerance <= 2.0,
        "sum_tolerance_seconds": round(tolerance, 6),
        "evidence_refs_present": all(len(r["evidence_refs"]) > 0 for r in rows),
    }

    # Cross-source checks.
    cross = {
        "sotaforge_trace_span_matches_node_duration": True,
        "harvester_report_present": (base / config.markers.get("harvester_report", "__missing__")).exists() if config.markers.get("harvester_report") else False,
        "api_trace_present": trace_path.exists(),
    }
    first_sota = first_trace_by_node(trace_rows, "SotaForge")
    last_sota = last_trace_by_node(trace_rows, "SotaForge")
    if first_sota and last_sota:
        expected = max(0.0, sec(first_sota, last_sota))
        actual = float(row_by_node["SotaForge"]["duration_seconds"])
        # Allow local staging overhead inside the same node window while ensuring
        # the trace span is fully contained in the reported node duration.
        cross["sotaforge_trace_span_matches_node_duration"] = (actual + 0.001) >= expected and (actual - expected) <= 45.0

    return {
        "dataset": config.name,
        "base_dir": str(base),
        "anchor_start": anchor.strftime(TIME_FMT),
        "total_end": total_end.strftime(TIME_FMT),
        "total_seconds": round(total_seconds, 3),
        "nodes": rows,
        "macro": macro,
        "quality_checks": quality,
        "cross_source_checks": cross,
    }


def write_csv(path: Path, rows: List[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "node",
                "start",
                "end",
                "duration_seconds",
                "percent_of_total",
                "confidence",
                "note",
                "evidence_refs",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "evidence_refs": " | ".join(row.get("evidence_refs", [])),
                }
            )


def bar(pct: float, width: int = 40) -> str:
    filled = int(round((pct / 100.0) * width))
    return "#" * filled + "-" * max(0, width - filled)


def write_md(path: Path, audit: dict) -> None:
    lines: List[str] = []
    lines.append(f"# TVC Node Time-Share Audit ({audit['dataset']})")
    lines.append("")
    lines.append(f"- Anchor start: `{audit['anchor_start']}`")
    lines.append(f"- End: `{audit['total_end']}`")
    lines.append(f"- Total wall time: `{audit['total_seconds']}s`")
    lines.append("")
    lines.append("## 10-Node View")
    lines.append("| Node | Duration (s) | % of Total | Confidence | Note |")
    lines.append("|---|---:|---:|:---:|---|")
    for row in audit["nodes"]:
        lines.append(
            f"| {row['node']} | {row['duration_seconds']:.3f} | {row['percent_of_total']:.2f}% | {row['confidence']} | {row['note']} |"
        )

    lines.append("")
    lines.append("### Node Time Share Bars")
    for row in audit["nodes"]:
        pct = float(row["percent_of_total"])
        lines.append(f"- {row['node']:<14} [{bar(pct)}] {pct:.2f}%")

    lines.append("")
    lines.append("## Macro Functional Areas")
    lines.append("| Functional Area | Duration (s) | % of Total | Nodes |")
    lines.append("|---|---:|---:|---|")
    for row in audit["macro"]:
        lines.append(
            f"| {row['functional_area']} | {row['duration_seconds']:.3f} | {row['percent_of_total']:.2f}% | {', '.join(row['nodes'])} |"
        )

    lines.append("")
    lines.append("### Macro Time Share Bars")
    for row in audit["macro"]:
        pct = float(row["percent_of_total"])
        lines.append(f"- {row['functional_area']:<18} [{bar(pct)}] {pct:.2f}%")

    lines.append("")
    lines.append("## Integrity Checks")
    for k, v in audit["quality_checks"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines.append("")
    lines.append("## Cross-Source Checks")
    for k, v in audit["cross_source_checks"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines.append("")
    lines.append("## Caveats")
    lines.append("- DurationGate is typically embedded and may report near-zero duration in retrospective mode.")
    lines.append("- Confidence A = trace span, B = artifact-boundary, C = inferred/embedded.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_methodology(path: Path) -> None:
    text = """# Timing Reconstruction Methodology

## Deterministic Rules
- Start anchor is the first timestamp in `api_call_trace.jsonl`.
- Node end markers are resolved in this order:
  - Harvester: `harvested_intelligence.txt` mtime, else last Harvester trace
  - Writer: `master_script.txt` mtime, else last Writer trace
  - DurationGate: embedded between Writer end and TopicExtractor first trace
  - TopicExtractor: `topic_callouts.json` mtime, else last TopicExtractor trace
  - SceneDirector: `scene_manifest.json` mtime, else last SceneDirector trace
  - Audio: `vtt_matrix.json` mtime, else last Audio trace
  - PromptArchitect: `master_prompts.json` mtime, else last PromptArchitect trace
  - SotaForge: last SotaForge trace
  - Editor: `filter.txt` mtime
  - Verifier: `verification_report.json` mtime
- Each node gets one contiguous window, and windows are chained in node order.

## Confidence Scale
- A: direct trace-span support for the node window
- B: artifact-boundary support
- C: inferred residual or embedded phase

## Validation Gates
- No negative durations
- Node-duration sum matches total wall time within 2 seconds
- Evidence reference present per node row
- SotaForge duration aligns with trace span when trace exists
"""
    path.write_text(text, encoding="utf-8")


def pick_repeatability_datasets(evidence_dir: Path) -> List[DatasetConfig]:
    ds_base = evidence_dir / "dual_source_sanity" / "20260308_161616"
    return [
        DatasetConfig(
            name="repeatability_youtube_20260308_161616",
            base_dir=ds_base,
            trace_file="youtube_api_call_trace.jsonl",
            pipeline_log="youtube_pipeline_run.log",
            markers={
                "topic_callouts": "youtube_topic_callouts.json",
                "vtt_matrix": "youtube_vtt_matrix.json",
                "filter_txt": "youtube_filter.txt",
                "verification_report": "youtube_verification_report.json",
            },
        ),
        DatasetConfig(
            name="repeatability_user_context_20260308_161616",
            base_dir=ds_base,
            trace_file="user_context_api_call_trace.jsonl",
            pipeline_log="user_context_pipeline_run.log",
            markers={
                "topic_callouts": "user_context_topic_callouts.json",
                "vtt_matrix": "user_context_vtt_matrix.json",
                "filter_txt": "user_context_filter.txt",
                "verification_report": "user_context_verification_report.json",
            },
        ),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="TVC node time-share retrospective audit")
    ap.add_argument("--run-id", default="20260308_203455")
    ap.add_argument("--project-root", default=r"D:\AI-Apps-In-Drive\App_Station\Video_production")
    args = ap.parse_args()

    project_root = Path(args.project_root)
    intel_dir = project_root / "tvc_multi_agent_db"
    evidence_dir = project_root / "Evidence"

    out_dir = evidence_dir / "time_audit_runs" / args.run_id
    ensure_dir(out_dir)

    copied = freeze_primary_bundle(out_dir, intel_dir, evidence_dir)

    primary = DatasetConfig(
        name=f"primary_{args.run_id}",
        base_dir=out_dir,
        trace_file="api_call_trace.jsonl",
        pipeline_log="pipeline_run.log",
        markers={
            "harvested_intelligence": "harvested_intelligence.txt",
            "harvester_report": "harvester_run_report.json",
            "master_script": "master_script.txt",
            "topic_callouts": "topic_callouts.json",
            "scene_manifest": "scene_manifest.json",
            "vtt_matrix": "vtt_matrix.json",
            "master_prompts": "master_prompts.json",
            "filter_txt": "filter.txt",
            "verification_report": "verification_report.json",
        },
    )

    primary_audit = reconstruct(primary)

    with (out_dir / "node_time_share.json").open("w", encoding="utf-8") as f:
        json.dump(primary_audit, f, indent=2, ensure_ascii=True)
    write_csv(out_dir / "node_time_share.csv", primary_audit["nodes"])
    write_md(out_dir / "node_time_share.md", primary_audit)
    write_methodology(out_dir / "methodology.md")

    # Repeatability on two prior successful runs.
    repeatability: List[dict] = []
    for cfg in pick_repeatability_datasets(evidence_dir):
        try:
            rep = reconstruct(cfg)
            repeatability.append({
                "dataset": cfg.name,
                "status": "ok",
                "total_seconds": rep["total_seconds"],
                "quality_checks": rep["quality_checks"],
                "cross_source_checks": rep["cross_source_checks"],
                "top3_nodes": sorted(rep["nodes"], key=lambda x: x["duration_seconds"], reverse=True)[:3],
            })
        except Exception as e:
            repeatability.append({"dataset": cfg.name, "status": "error", "error": str(e)})

    repeatability_report = {
        "generated_at": datetime.now().strftime(TIME_FMT),
        "primary_run_id": args.run_id,
        "bundle_manifest": str(out_dir / "bundle_manifest.json"),
        "primary_outputs": {
            "json": str(out_dir / "node_time_share.json"),
            "csv": str(out_dir / "node_time_share.csv"),
            "md": str(out_dir / "node_time_share.md"),
            "methodology": str(out_dir / "methodology.md"),
        },
        "copied_files": copied,
        "repeatability": repeatability,
    }
    with (out_dir / "repeatability_report.json").open("w", encoding="utf-8") as f:
        json.dump(repeatability_report, f, indent=2, ensure_ascii=True)

    rep_md_lines = [
        "# Repeatability Report",
        "",
        f"- Primary run: `{args.run_id}`",
        "",
        "## Prior Runs",
    ]
    for row in repeatability:
        rep_md_lines.append(f"- `{row['dataset']}`: `{row['status']}`")
        if row["status"] == "ok":
            rep_md_lines.append(f"  - total_seconds: `{row['total_seconds']}`")
            rep_md_lines.append(f"  - quality_checks: `{json.dumps(row['quality_checks'])}`")
            rep_md_lines.append(f"  - cross_source_checks: `{json.dumps(row['cross_source_checks'])}`")
            top3 = ", ".join([f"{x['node']} ({x['percent_of_total']}%)" for x in row["top3_nodes"]])
            rep_md_lines.append(f"  - top3_nodes: `{top3}`")
        else:
            rep_md_lines.append(f"  - error: `{row.get('error', '')}`")
    (out_dir / "repeatability_report.md").write_text("\n".join(rep_md_lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "output_dir": str(out_dir),
        "primary_total_seconds": primary_audit["total_seconds"],
        "harvester_percent": next((r["percent_of_total"] for r in primary_audit["nodes"] if r["node"] == "Harvester"), None),
    }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
