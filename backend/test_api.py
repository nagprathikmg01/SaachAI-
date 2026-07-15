import asyncio
import os
import io
import wave
from dotenv import load_dotenv

load_dotenv()

def create_dummy_wav():
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        # Just 1 second of silence
        w.writeframes(b'\x00' * 44100 * 2)
    return buf.getvalue()

def _extract_words(response) -> list:
    try:
        results   = getattr(response, "results", None) or response.get("results", {})
        channels  = getattr(results, "channels", None) or results.get("channels", [])
        if not channels: return []
        ch  = channels[0]
        alts = getattr(ch, "alternatives", None) or ch.get("alternatives", [])
        if not alts: return []
        alt = alts[0]
        words = getattr(alt, "words", None) or alt.get("words", []) or []
        return words
    except Exception as e:
        print("extract words err:", e)
        return []

def _extract_transcript(response) -> str:
    try:
        results   = getattr(response, "results", None) or response.get("results", {})
        channels  = getattr(results, "channels", None) or results.get("channels", [])
        if not channels: return ""
        ch  = channels[0]
        alts = getattr(ch, "alternatives", None) or ch.get("alternatives", [])
        if not alts: return ""
        alt = alts[0]
        t = getattr(alt, "transcript", None) or alt.get("transcript", "") or ""
        return t.strip()
    except Exception as e:
        print("extract transcript err:", e)
        return ""

def test_deepgram():
    from deepgram import DeepgramClient, PrerecordedOptions
    client = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
    payload = {"buffer": create_dummy_wav(), "mimetype": "audio/wav"}
    options = PrerecordedOptions(model="nova-2")
    try:
        response = client.listen.prerecorded.v("1").transcribe_file(payload, options)
        
        # KEY FIX: Convert to dict first!
        if hasattr(response, "to_dict"):
            response = response.to_dict()
            
        print("Words:", _extract_words(response))
        print("Transcript:", _extract_transcript(response))
    except Exception as e:
        print("Deepgram error:", e)

if __name__ == "__main__":
    test_deepgram()
