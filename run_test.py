import sys
from tvc_langgraph_core import execute_multi_agent_narrator

def main():
    if len(sys.argv) < 3:
        print("Usage: python run_test.py <prompt> <output_path>")
        sys.exit(1)
        
    prompt = sys.argv[1]
    output_path = sys.argv[2]
    
    # Loading the active Gemini API key from the local vault via centralized SOTA loader
    from tvc_vault import get_secret
    api_key = get_secret("key_HGmChvaB")
    
    execute_multi_agent_narrator(
        user_prompt=prompt,
        final_output=output_path,
        api_key=api_key,
        target_duration=120
    )

if __name__ == "__main__":
    main()
