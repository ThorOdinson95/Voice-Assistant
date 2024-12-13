#activation word - "Jarvis"

from datetime import date
from io import BytesIO
import threading
import queue
import time
import os

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

import google.generativeai as genai
from gtts import gTTS
from pygame import mixer
import speech_recognition as sr

mixer.pre_init(frequency=24000, buffer=2048)
mixer.init()

my_api_key = " "

if len(my_api_key) < 5:
    print("Please add your Google Gemini API key in the program.")
    quit()

genai.configure(api_key=my_api_key)

model = genai.GenerativeModel('gemini-pro',
    generation_config=genai.GenerationConfig(
        candidate_count=1,
        top_p=0.95,
        top_k=64,
        max_output_tokens=60,
        temperature=0.9,
    ))

chat = model.start_chat(history=[])

today = str(date.today())

numtext = 0
numtts = 0
numaudio = 0

def chatfun(request, text_queue, llm_done, stop_event):
    global numtext, chat

    response = chat.send_message(request, stream=True)
    shortstring = ''
    ctext = ''

    for chunk in response:
        try:
            if chunk.candidates[0].content.parts:
                ctext = chunk.candidates[0].content.parts[0].text.replace("*", "")

                if len(shortstring) > 10 or len(ctext) > 10:
                    shortstring = "".join([shortstring, ctext])
                    text_queue.put(shortstring)
                    print(shortstring, end='')
                    shortstring = ''
                    ctext = ''
                    numtext += 1
                else:
                    shortstring = "".join([shortstring, ctext])
                    ctext = ''
        except Exception:
            continue

    if len(ctext) > 0:
        shortstring = "".join([shortstring, ctext])
    if len(shortstring) > 0:
        print(shortstring, end='')
        text_queue.put(shortstring)
        numtext += 1

    llm_done.set()

def speak_text(text):
    mp3file = BytesIO()
    tts = gTTS(text, lang="en", tld='us')
    tts.write_to_fp(mp3file)
    mp3file.seek(0)
    print("AI:", text)

    try:
        mixer.music.load(mp3file, "mp3")
        mixer.music.play()
        while mixer.music.get_busy():
            time.sleep(0.2)
    except KeyboardInterrupt:
        mixer.music.stop()
        mp3file = None

    mp3file = None

def text2speech(text_queue, tts_done, llm_done, audio_queue, stop_event):
    global numtext, numtts

    while not stop_event.is_set():
        if not text_queue.empty():
            text = text_queue.get()
            if len(text) > 0:
                try:
                    mp3file1 = BytesIO()
                    tts = gTTS(text, lang="en", tld='us')
                    tts.write_to_fp(mp3file1)
                except Exception:
                    continue
                audio_queue.put(mp3file1)
                numtts += 1
                text_queue.task_done()
        if llm_done.is_set() and numtts == numtext:
            tts_done.set()
            break

def play_audio(audio_queue, tts_done, stop_event):
    global numtts, numaudio
    while not stop_event.is_set():
        mp3audio1 = audio_queue.get()
        mp3audio1.seek(0)
        mixer.music.load(mp3audio1, "mp3")
        mixer.music.play()

        while mixer.music.get_busy():
            time.sleep(0.2)
        numaudio += 1
        audio_queue.task_done()
        if tts_done.is_set() and numtts == numaudio:
            break

def append2log(text):
    global today
    fname = 'chatlog-' + today + '.txt'
    with open(fname, "a", encoding='utf-8') as f:
        f.write(text + "\n")

def main():
    global today, numtext, numtts, numaudio, chat

    rec = sr.Recognizer()
    mic = sr.Microphone()

    rec.dynamic_energy_threshold = False
    rec.energy_threshold = 400

    sleeping = True

    while True:
        with mic as source:
            rec.adjust_for_ambient_noise(source, duration=0.5)
            try:
                print("Listening...")
                audio = rec.listen(source, timeout=10)
                text = rec.recognize_google(audio, language="en-EN")

                if len(text) > 0:
                    print(f"You: {text}\n")
                else:
                    continue

                if sleeping:
                    if "jarvis" in text.lower():
                        request = text.lower().split("jarvis")[1]
                        sleeping = False
                        chat = model.start_chat(history=[])
                        append2log(f"_{"*40}")
                        append2log(f"You: {request}\n")
                        speak_text("Hello, how can I assist you?")
                        continue
                    else:
                        continue
                else:
                    request = text.lower()
                    if "that's all" in request:
                        append2log(f"You: {request}\n")
                        speak_text("Goodbye!")
                        append2log("AI: Goodbye!\n")
                        sleeping = True
                        continue

                append2log(f"You: {request}\n")

                numtext = 0
                numtts = 0
                numaudio = 0

                text_queue = queue.Queue()
                audio_queue = queue.Queue()

                llm_done = threading.Event()
                tts_done = threading.Event()
                stop_event = threading.Event()

                llm_thread = threading.Thread(target=chatfun, args=(request, text_queue, llm_done, stop_event,))
                tts_thread = threading.Thread(target=text2speech, args=(text_queue, tts_done, llm_done, audio_queue, stop_event,))
                play_thread = threading.Thread(target=play_audio, args=(audio_queue, tts_done, stop_event,))

                llm_thread.start()
                tts_thread.start()
                play_thread.start()

                llm_done.wait()
                llm_thread.join()

                tts_done.wait()
                audio_queue.join()

                stop_event.set()
                tts_thread.join()
                play_thread.join()

                print('\n')

            except Exception:
                continue

if __name__ == "__main__":
    main()
