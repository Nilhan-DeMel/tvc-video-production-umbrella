import tvc_config

def main():
    from tvc_vault import get_secret
    api_key = get_secret("key_HGmChvaB")
    if not api_key:
        return

    user_prompt = "Check the latest 3 YouTube videos on the smallest dogs in the world - and generate a 21 second video about how sweet and cute they are."
    final_output = os.path.join(tvc_config.PATHS["root"], "sota_v5_smallest_dogs.mp4")
    target_duration = 21

    print("Initiating SOTA TVC V5.0 Precision Run (Smallest Dogs)...")
    try:
        execute_multi_agent_narrator(
            user_prompt=user_prompt,
            final_output=final_output,
            api_key=api_key,
            target_duration=target_duration
        )
        print(f"Success! Output saved to: {final_output}")
    except Exception as e:
        print(f"Pipeline Failed: {e}")

if __name__ == "__main__":
    main()
