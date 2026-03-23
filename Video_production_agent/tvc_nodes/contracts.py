from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class SceneDirectorInput:
    request_prompt: str
    script: str
    input_source: str
    context_rewrite: str
    narration_style: str


@dataclass
class SceneDirectorOutput:
    visual_scenes: List[dict]
    style_dna: str
    meta_context: str
    character_manifest: Dict[str, str]
    status: str = "scenes_directed"
    node_report: Dict[str, Any] = field(default_factory=dict)

    def to_state_update(self) -> Dict[str, Any]:
        return {
            "visual_scenes": self.visual_scenes,
            "style_dna": self.style_dna,
            "meta_context": self.meta_context,
            "character_manifest": self.character_manifest,
            "status": self.status,
        }


@dataclass(frozen=True)
class TopicExtractorInput:
    script: str
    input_source: str
    context_rewrite: str


@dataclass
class TopicExtractorOutput:
    topic_callouts: List[dict]
    status: str = "topics_extracted"
    node_report: Dict[str, Any] = field(default_factory=dict)

    def to_state_update(self) -> Dict[str, Any]:
        return {
            "topic_callouts": self.topic_callouts,
            "status": self.status,
        }


@dataclass(frozen=True)
class PromptArchitectInput:
    script: str
    epochs: List[dict]
    total_epochs: int
    input_source: str
    context_rewrite: str
    narration_style: str
    style_dna: str
    meta_context: str
    character_manifest: Dict[str, str]


@dataclass
class PromptArchitectOutput:
    sota_prompts: List[str]
    qa_targets: List[str]
    status: str = "prompts_architected"
    node_report: Dict[str, Any] = field(default_factory=dict)

    def to_state_update(self) -> Dict[str, Any]:
        return {
            "sota_prompts": self.sota_prompts,
            "qa_targets": self.qa_targets,
            "status": self.status,
        }


@dataclass(frozen=True)
class WriterInput:
    request_prompt: str
    context_summary: str
    harvested_intelligence: str
    input_source: str
    context_rewrite: str
    narration_style: str
    status: str
    duration_attempts: int
    duration_mode: str
    requested_target_duration_seconds: Any
    estimated_duration_seconds: Any
    target_duration: Any
    actual_audio_duration_seconds: Any


@dataclass
class WriterOutput:
    script: str
    status: str = "drafted"
    duration_attempts: int = 0
    node_report: Dict[str, Any] = field(default_factory=dict)

    def to_state_update(self) -> Dict[str, Any]:
        return {
            "script": self.script,
            "status": self.status,
            "duration_attempts": self.duration_attempts,
        }


@dataclass(frozen=True)
class DurationGateInput:
    input_source: str
    context_rewrite: str
    script: str
    duration_attempts: int
    duration_mode: str
    requested_target_duration_seconds: Any
    estimated_duration_seconds: Any
    target_duration: Any
    actual_audio_duration_seconds: Any


@dataclass
class DurationGateOutput:
    status: str = "duration_fail"
    script: str = ""

    def to_state_update(self) -> Dict[str, Any]:
        payload = {"status": self.status}
        if self.script:
            payload["script"] = self.script
        return payload


@dataclass(frozen=True)
class AudioEngineerInput:
    script: str
    context_summary: str
    request_prompt: str
    input_source: str
    context_rewrite: str
    narration_style: str
    voice_preset: str
    visual_scenes: List[dict]
    images_forged: int
    qa_attempts: int
    duration_mode: str
    requested_target_duration_seconds: Any
    estimated_duration_seconds: Any
    target_duration: Any
    actual_audio_duration_seconds: Any


@dataclass
class AudioEngineerOutput:
    audio_path: str = ""
    vtt_path: str = ""
    actual_audio_duration_seconds: Any = None
    epochs: List[dict] = field(default_factory=list)
    total_epochs: int = 0
    images_forged: int = 0
    qa_attempts: int = 0
    status: str = "audio_forged"
    errors: List[str] = field(default_factory=list)
    node_report: Dict[str, Any] = field(default_factory=dict)

    def to_state_update(self) -> Dict[str, Any]:
        payload = {
            "audio_path": self.audio_path,
            "vtt_path": self.vtt_path,
            "actual_audio_duration_seconds": self.actual_audio_duration_seconds,
            "epochs": self.epochs,
            "total_epochs": self.total_epochs,
            "images_forged": self.images_forged,
            "qa_attempts": self.qa_attempts,
            "status": self.status,
        }
        if self.errors:
            payload["errors"] = self.errors
        return payload


@dataclass(frozen=True)
class SotaForgeInput:
    input_source: str
    context_rewrite: str
    total_epochs: int
    epochs: List[dict]
    sota_prompts: List[str]
    qa_targets: List[str]


@dataclass
class SotaForgeOutput:
    status: str = "sota_vision_complete"
    qa_scores: List[float] = field(default_factory=list)
    images_forged: int = 0
    epochs: List[dict] = field(default_factory=list)
    node_report: Dict[str, Any] = field(default_factory=dict)

    def to_state_update(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "qa_scores": self.qa_scores,
            "images_forged": self.images_forged,
            "epochs": self.epochs,
        }


@dataclass(frozen=True)
class LeadEditorInput:
    audio_path: str
    epochs: List[dict]
    topic_callouts: List[dict]
    watermark_mode: str
    target_output: str
    duration_mode: str
    requested_target_duration_seconds: Any
    estimated_duration_seconds: Any
    target_duration: Any
    actual_audio_duration_seconds: Any


@dataclass
class LeadEditorOutput:
    status: str = "rendered"
    final_video: str = ""
    errors: List[str] = field(default_factory=list)
    node_report: Dict[str, Any] = field(default_factory=dict)

    def to_state_update(self) -> Dict[str, Any]:
        payload = {"status": self.status}
        if self.final_video:
            payload["final_video"] = self.final_video
        if self.errors:
            payload["errors"] = self.errors
        return payload


@dataclass(frozen=True)
class VerifierInput:
    target_output: str
    audio_path: str
    script: str
    vtt_path: str


@dataclass
class VerifierOutput:
    verification_report: Dict[str, Any] = field(default_factory=dict)
    status: str = "complete"

    def to_state_update(self) -> Dict[str, Any]:
        return {
            "verification_report": self.verification_report,
            "status": self.status,
        }
