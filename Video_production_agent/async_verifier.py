import os
import sys
import json
from supreme_commander import supreme_video_commander

def test_async_returns():
    print("Verifying Async Status Returns (ISSUE-008)...")
    
    modes = ["--mode MODE_VOICE", "--mode MODE_ORCHESTRATE", "--mode MODE_ANIMATION", "--mode MODE_COMPILE"]
    
    for mode in modes:
        request = f"Test request {mode}"
        print(f"Testing {mode}...")
        result = supreme_video_commander(request)
        
        status = result.get("status")
        output = result.get("output")
        
        print(f"  Status: {status}")
        print(f"  Output: {output}")
        
        if output is None:
            print(f"[FAIL] {mode} returned null output.")
        else:
            print(f"[OK] {mode} returned valid path.")
            
if __name__ == "__main__":
    test_async_returns()
