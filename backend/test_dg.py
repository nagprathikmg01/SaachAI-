import asyncio
from deepgram import DeepgramClient, PrerecordedOptions

def main():
    client = DeepgramClient("fake_key")
    try:
        print(dir(client.listen.prerecorded.v("1")))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
