import asyncio
import edge_tts

async def main():
    text = "The year is 2026, and the global AI landscape has been irrevocably redrawn. From the sprawling tech hubs of Beijing and Shenzhen, a new generation of foundational models has awakened."
    comm = edge_tts.Communicate(text, "en-GB-RyanNeural")
    sub = edge_tts.SubMaker()
    async for chunk in comm.stream():
        if chunk["type"] != "audio":
            print(chunk)
            # Try feeding to SubMaker anyway
            sub.feed(chunk)
    
    print("--- VTT RAW ---")
    print(sub.get_srt())

asyncio.run(main())
