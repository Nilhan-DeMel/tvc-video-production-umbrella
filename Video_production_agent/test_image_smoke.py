import os
import tvc_langgraph_core as core

def test():
    try:
        success = core.bfl_generate_image(
            "A futuristic server room glowing with neon blue lights, highly detailed, 4k",
            1920,
            1080,
            "test_flux_smoke.jpg",
        )
        if success and os.path.exists("test_flux_smoke.jpg"):
            print("BFL IMAGE SMOKE TEST PASSED. Image saved to test_flux_smoke.jpg")
        else:
            print("BFL IMAGE SMOKE TEST FAILED.")
    except Exception as e:
        print("BFL IMAGE SMOKE TEST CRASHED.", e)

if __name__ == "__main__":
    test()
