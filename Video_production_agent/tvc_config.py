from pathlib import Path

# ==============================================================
# TVC CONFIGURATION & PATH REGISTRY (SOTA Pathlib Standard)
# ==============================================================

# Derive project root securely using Pathlib
PROJECT_ROOT = Path(__file__).resolve().parent

# Standard Directory Schema
PATHS = {
    "root": str(PROJECT_ROOT),
    "assets": str(PROJECT_ROOT / "assets"),
    "intelligence": str(PROJECT_ROOT / "tvc_multi_agent_db"),
    "intelligence_7min": str(PROJECT_ROOT / "intelligence_7min"),
    "evidence": str(PROJECT_ROOT / "Evidence"),
    "secrets": r"D:\AI\API\Secrets",
    "vault_index": str(PROJECT_ROOT / "vault_dump.json"),
    "mission_log": str(PROJECT_ROOT / "commander_mission_log.json")
}

# Ensure critical directories exist using Pathlib
def ensure_structure():
    Path(PATHS["assets"]).mkdir(parents=True, exist_ok=True)
    Path(PATHS["intelligence"]).mkdir(parents=True, exist_ok=True)
    Path(PATHS["evidence"]).mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print(f"TVC Project Root: {PROJECT_ROOT}")
    for name, path in PATHS.items():
        print(f"  - {name}: {path}")
