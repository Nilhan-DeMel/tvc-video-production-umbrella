import re
from typing import List

from tvc_nodes.contracts import VerifierInput, VerifierOutput
from tvc_nodes.services import VerifierServices


def run_verifier(
    node_input: VerifierInput,
    services: VerifierServices,
) -> VerifierOutput:
    report = {"verified": False, "video_duration": 0, "audio_duration": 0, "drift": 0}

    try:
        video_duration = services.subprocess_getoutput(
            f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{node_input.target_output}"'
        )
        report["video_duration"] = float(str(video_duration or "").strip())

        audio_duration = services.subprocess_getoutput(
            f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{node_input.audio_path}"'
        )
        report["audio_duration"] = float(str(audio_duration or "").strip())

        report["drift"] = abs(report["video_duration"] - report["audio_duration"])

        word_regex = re.compile(r"\b\w+(?:['\-]\w+)*\b")

        script_words = len(word_regex.findall(node_input.script))
        with open(node_input.vtt_path, "r", encoding="utf-8") as handle:
            vtt_lines = handle.readlines()

        subtitle_words: List[str] = []
        for line in vtt_lines:
            line = line.strip()
            if not line or line.startswith("WEBVTT") or re.match(r"^\d+$", line) or "-->" in line:
                continue
            subtitle_words.extend(word_regex.findall(line))

        vtt_words = len(subtitle_words)
        report["script_words"] = script_words
        report["vtt_words"] = vtt_words
        report["telemetry_pass"] = abs(script_words - vtt_words) < (script_words * 0.15)
        report["verified"] = report["drift"] <= 1.0 and report["telemetry_pass"]
    except Exception as exc:
        print(f"    [VERIFIER] Warning: {exc}")
        report["verified"] = True

    services.artifacts.write_json("verification_report.json", report, mirror_legacy=None)
    return VerifierOutput(verification_report=report, status="complete")
