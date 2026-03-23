from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ArtifactStore:
    path: Callable[[str], str]
    read_path: Callable[[str], str]
    write_json: Callable[..., Any]


@dataclass(frozen=True)
class ManifestStore:
    load: Callable[[], dict]
    save: Callable[[dict], Any]


@dataclass(frozen=True)
class SceneDirectorServices:
    artifacts: ArtifactStore
    manifest: ManifestStore
    update_scene_audio_prompt_report: Callable[[str, dict], Any]
    smart_retry: Callable[..., Any]
    fireworks_chat_completion: Callable[..., Any]
    generate_content_config: Callable[..., Any]
    normalize_scene_payload: Callable[..., dict]
    enforce_scene_mode_style: Callable[[dict, str], dict]
    deterministic_scene_builder: Callable[..., dict]
    sentence_scene_recovery: Callable[[str], list]
    narration_profile: Callable[[str], dict]
    normalize_narration_style: Callable[[str], str]
    is_deterministic_user_context_mode: Callable[[Any], bool]
    minimum_scene_count_for_script: Callable[[str], int]
    get_hash: Callable[[str], str]
    json_repair: Callable[[str], Any]
    unified_negative_prompt: str
    narration_style_default: str


@dataclass(frozen=True)
class TopicExtractorServices:
    artifacts: ArtifactStore
    manifest: ManifestStore
    smart_retry: Callable[..., Any]
    fireworks_chat_completion: Callable[..., Any]
    generate_content_config: Callable[..., Any]
    is_deterministic_user_context_mode: Callable[[Any], bool]
    get_hash: Callable[[str], str]
    json_repair: Callable[[str], Any]


@dataclass(frozen=True)
class PromptArchitectServices:
    artifacts: ArtifactStore
    manifest: ManifestStore
    update_scene_audio_prompt_report: Callable[[str, dict], Any]
    smart_retry: Callable[..., Any]
    fireworks_chat_completion: Callable[..., Any]
    generate_content_config: Callable[..., Any]
    json_repair: Callable[[str], Any]
    normalize_narration_style: Callable[[str], str]
    normalize_context_rewrite: Callable[[str], str]
    narration_profile: Callable[[str], dict]
    get_hash: Callable[[str], str]
    getenv: Callable[[str, Any], Any]
    narration_style_default: str = "sales_saas"


@dataclass(frozen=True)
class WriterServices:
    artifacts: ArtifactStore
    manifest: ManifestStore
    smart_retry: Callable[..., Any]
    fireworks_chat_completion: Callable[..., Any]
    generate_content_config: Callable[..., Any]
    duration_meta_from_state: Callable[[Any], dict]
    normalize_narration_style: Callable[[str], str]
    normalize_context_rewrite: Callable[[str], str]
    is_deterministic_user_context_mode: Callable[[Any], bool]
    narration_profile: Callable[[str], dict]
    apply_cpp: Callable[[str], str]
    sanitize_tts_script: Callable[[str], str]
    clean_transcript_text: Callable[[str], str]
    word_token_set: Callable[[str], Any]
    meaningful_terms: Callable[..., Any]
    get_hash: Callable[[str], str]
    getenv: Callable[[str, Any], Any]
    write_text_artifact: Callable[..., Any]
    narration_style_default: str = "sales_saas"


@dataclass(frozen=True)
class DurationGateServices:
    normalize_context_rewrite: Callable[[str], str]
    duration_meta_from_state: Callable[[Any], dict]
    write_text_artifact: Callable[..., Any]


@dataclass(frozen=True)
class AudioEngineerServices:
    artifacts: ArtifactStore
    manifest: ManifestStore
    update_scene_audio_prompt_report: Callable[[str, dict], Any]
    smart_retry: Callable[..., Any]
    fireworks_chat_completion: Callable[..., Any]
    generate_content_config: Callable[..., Any]
    duration_meta_from_state: Callable[[Any, Any], dict]
    update_run_manifest_duration_fields: Callable[[dict], Any]
    sanitize_tts_script: Callable[[str], str]
    summarize_cpp_alignment: Callable[[str, str], dict]
    is_deterministic_user_context_mode: Callable[[Any], bool]
    normalize_narration_style: Callable[[str], str]
    narration_profile: Callable[[str], dict]
    resolve_voice_preset: Callable[[str, dict], dict]
    normalize_epochs_from_mapping: Callable[[Any, Any], list]
    build_local_epoch_mapping: Callable[[Any, str, str], list]
    update_live_status: Callable[[dict, bool], Any]
    apply_cpp: Callable[[str], str]
    ffprobe_duration: Callable[[str], Any]
    communicate_factory: Callable[..., Any]
    submaker_factory: Callable[..., Any]
    write_text_artifact: Callable[..., Any]
    write_binary_artifact: Callable[..., Any]
    json_repair: Callable[[str], Any]
    get_hash: Callable[[str], str]
    pronunciation_resolver: Callable[[str, str, str], dict]
    narration_style_default: str = "sales_saas"
    voice_preset_default: str = "style_default"


@dataclass(frozen=True)
class SotaForgeServices:
    artifacts: ArtifactStore
    update_scene_audio_prompt_report: Callable[[str, dict], Any]
    update_live_status: Callable[[dict, bool], Any]
    smart_retry: Callable[..., Any]
    bfl_generate_image: Callable[..., Any]
    normalize_context_rewrite: Callable[[str], str]
    getenv: Callable[[str, Any], Any]
    build_epoch_context_payload: Callable[[Any], list]
    normalize_pre_scene_manifest_payload: Callable[[Any], Any]
    compose_pre_scene_primary_prompt: Callable[[dict, dict], str]
    compose_image_generation_prompt: Callable[[str, dict, list], str]
    compose_compact_epoch_fallback_prompt: Callable[[dict, str], str]
    extract_main_description_for_qa: Callable[[str, list, int], str]
    run_visual_qa_for_image: Callable[[str, str, str, float], dict]
    ensure_epoch_image_with_fallback: Callable[[str, str, str], str]
    append_jsonl_artifact: Callable[..., Any]
    write_text_artifact: Callable[..., Any]
    smartcrop_factory: Callable[[], Any]
    pil_image_module: Any
    unified_negative_prompt: str


@dataclass(frozen=True)
class LeadEditorServices:
    artifacts: ArtifactStore
    write_text_artifact: Callable[..., Any]
    ensure_epoch_image_with_fallback: Callable[[str, str, str], str]
    normalize_watermark_mode: Callable[[str], str]
    duration_meta_from_state: Callable[[Any], dict]
    subprocess_getoutput: Callable[[str], str]
    subprocess_run: Callable[..., Any]
    project_dir: str
    watermark_mode_default: str
    watermark_font_size: int


@dataclass(frozen=True)
class VerifierServices:
    artifacts: ArtifactStore
    subprocess_getoutput: Callable[[str], str]
