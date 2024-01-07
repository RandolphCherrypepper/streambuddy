import os
import sys
import json
import requests
# pip install websocket-client
import websocket as ws
# pip install obsws-python
import obsws_python as obs
import subprocess

from datetime import datetime, timedelta

import numpy as np
import speech_recognition as sr
import whisper
import torch
from queue import Queue

# CHANGE THIS TO YOUR TWITCH DISPLAY USERNAME
my_username = "RandolphCherrypepper"

def setup_asr():
    ENERGY_THRESHOLD = 900
    # Thread safe Queue for passing data from the threaded recording callback.
    data_queue = Queue()
    # We use SpeechRecognizer to record our audio because it has a nice feature where it can detect when speech ends.
    recorder = sr.Recognizer()
    recorder.dynamic_energy_threshold = False
    recorder.energy_threshold = ENERGY_THRESHOLD # wtf is the unit on this? also this gets ignored
    # Definitely do this, dynamic energy compensation lowers the energy threshold dramatically to a point where the SpeechRecognizer never stops recording.

    source = sr.Microphone(sample_rate=16000, device_index=6)
    audio_model = whisper.load_model('large-v3')
    record_timeout = 2

    with source:
        recorder.adjust_for_ambient_noise(source)

    def record_callback(_, audio:sr.AudioData) -> None:
        """
        Threaded callback function to receive audio data when recordings finish.
        audio: An AudioData containing the recorded bytes.
        """
        # Grab the raw bytes and push it into the thread safe queue.
        data = audio.get_raw_data()
        # TODO insert some kind of noise reduction here!! AND BAIL IF DEAD AIR
        data_queue.put(data)
        # reiterate this in case it changes dynamically against our wishes
        recorder.energy_threshold = ENERGY_THRESHOLD

    # Create a background thread that will pass us raw audio bytes.
    # We could do this manually but SpeechRecognizer provides a nice helper.
    recorder.listen_in_background(source, record_callback, phrase_time_limit=record_timeout)
    print("Whisper Model loaded. 📣")
    return (audio_model, data_queue)

def obs_connect():
    # pass conn info if not in config.toml
    return obs.ReqClient(timeout=10)

def load_token():
    # Try to load the token first.
    try:
        with open('.token','r', encoding='utf-8-sig') as infile:
            auth_object = json.loads(infile.read())
            auth_object['access_token']
            auth_object['refresh_token']
            return auth_object
    except:
        return None

def verify_token_response(response):
    # verify the auth response
    auth_object = None
    if response.status_code < 200 or response.status_code >= 300:
        raise Exception(f'Fail. {response.status_code} {response.text}')
    if response.headers['Content-Type'] != 'application/json':
        raise Exception(f"Got bad content type {response.headers['Content-Type']}")
    try:
        auth_object = json.loads(response.text)
        auth_object['access_token']
        auth_object['refresh_token']
    except:
        raise Exception('Could not parse response body or missing access_token or refresh_token')
    with open('.token','w', encoding='utf-8-sig') as outfile:
        outfile.write(json.dumps(auth_object))
    print("Token successfully fetched. 🎉")
    return auth_object

def fetch_token():
    # Fetch a Twitch token
    # First try to load the token.
    loaded = load_token()
    if loaded is not None:
        print("Token successfully loaded without fetch.")
        return loaded

    cid = os.environ['TWITCH_AUTH_CLIENTID'].strip()
    scopes = os.environ['TWITCH_AUTH_SCOPES'].strip()
    device_code = os.environ['TWITCH_AUTH_DEVICECODE'].strip()
    response = requests.post("https://id.twitch.tv/oauth2/token", files={
        "client_id": (None, f'{cid}'),
        "scopes": (None, f'{scopes}'),
        "device_code": (None, f'{device_code}'),
        "grant_type": (None, 'urn:ietf:params:oauth:grant-type:device_code'),
        })

    # verify the auth response
    return verify_token_response(response)

def refresh_token(auth_object):
    cid = os.environ['TWITCH_AUTH_CLIENTID'].strip()
    secret = os.environ['TWITCH_AUTH_SECRET'].strip()
    response = requests.post("https://id.twitch.tv/oauth2/token", data={
        "grant_type": 'refresh_token',
        "refresh_token": auth_object["refresh_token"],
        "client_id": cid,
        "client_secret": secret,
        })

    # verify the auth response
    return verify_token_response(response)

def connect_websocket():
    wso = ws.WebSocket()
    wso.settimeout(3)
    wso.connect("wss://irc-ws.chat.twitch.tv:443")
    return wso

my_name = my_username.lower()
my_channel = f"#{my_name}"
def auth_connection(websocket, token, do_retry=True):
    access_token = token['access_token']
    websocket.send("CAP REQ :twitch.tv/membership twitch.tv/tags twitch.tv/commands")
    message = websocket.recv()
    print("CAP sent")
    websocket.send(f"PASS oauth:{access_token}")
    websocket.send(f"NICK {my_name}");
    print("PASS and NICK sent")
    message = websocket.recv()
    if 'login authentication failed' in message.lower():
        if do_retry:
            print('Token is no good anymore. Trying to refresh.')
            token = refresh_token(token)
            websocket = connect_websocket()
            auth_connection(websocket, token, do_retry=False)
        else:
            raise Exception('Token could not be authed. 😢')

    print("Presumably websocket auth'd. Response length " + str(len(message)))

def yoink_tags(metadata):
    # remove the starting @
    tag_info = {}
    metadata = metadata[1:]
    # split each tag that is separated by ;
    metadatums = metadata.split(';')
    for metadatum in metadatums:
        # split each key, value pair separated by =
        parts = metadatum.split('=')
        tag_info[parts[0]] = parts[1]
    return tag_info

GPT_IN_LINES = 12
GPT_INTERVAL = timedelta(seconds=120)
LINE_BREAK = "\r\n"
ping_msg = "PING :tmi.twitch.tv"
pong_msg = "PONG :tmi.twitch.tv"
msg_sep = "\r\n"
def run(websocket, obsws, audio_model, data_queue):
    keep_running = True
    chatbuffertext = ""
    ccbuffertext = ""
    obsbuffertext = ""
    gptbuffertext = ""
    last_gpt_write = datetime(1970,1,1)
    last_gpt_output = datetime.now().isoformat()
    # The last time a recording was retrieved from the queue.
    phrase_time = None
    phrase_timeout = 3

    websocket.send(f"JOIN {my_channel}")
    websocket.send(f"PRIVMSG {my_channel} 🤖")

    while keep_running:

        ### ANALYZE VOICE

        now = datetime.utcnow()
        # Pull raw recorded audio from the queue.
        if not data_queue.empty():
            phrase_complete = False
            # If enough time has passed between recordings, consider the phrase complete.
            # Clear the current working audio buffer to start over with the new data.
            #if phrase_time and now - phrase_time > timedelta(seconds=phrase_timeout):
            if phrase_time is None or now - phrase_time > timedelta(seconds=phrase_timeout):
                phrase_complete = True
            # This is the last time we received new audio data from the queue.
            phrase_time = now
                
            # Combine audio data from queue
            audio_data = b''.join(data_queue.queue)
            data_queue.queue.clear()
                
            # Convert in-ram buffer to something the model can use directly without needing a temp file.
            # Convert data from 16 bit wide integers to floating point with a width of 32 bits.
            # Clamp the audio stream frequency to a PCM wavelength compatible default of 32768hz max.
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # Read the transcription.
            result = audio_model.transcribe(audio_np, fp16=torch.cuda.is_available())
            
            # TODO any way to check the confidence of the transcription?? Throw out low confidence.

            resulttext = result['text'].strip()
            ccbuffertext += " " + resulttext
            obsbuffertext += " " + resulttext
            
            ccbuffertext = ccbuffertext.strip()
            obsbuffertext.strip()

            obsbuffertext = " ".join(obsbuffertext.split(" ")[-24:])
            obsws.send_stream_caption(obsbuffertext)
            
            # If we detected a pause between recordings, add a new item to our transcription.
            # Otherwise edit the existing one.
            if phrase_complete and len(ccbuffertext) > 2:
                is_ellipses = ccbuffertext[-3:] == '...'
                is_terminated = ccbuffertext[-1] == '.' or ccbuffertext[-1] == '?'
                if is_terminated and not is_ellipses:
                    gptbuffertext += f"RandolphCherrypepper: {ccbuffertext}{LINE_BREAK}"
                    websocket.send(f"PRIVMSG {my_channel} :(CC) {ccbuffertext}")
                    if 'all bots must die' in ccbuffertext.lower() or 'all robots must die' in ccbuffertext.lower():
                        keep_running = False
                    ccbuffertext = ""

        ### ANALYZE CHAT

        try:
            newtext = websocket.recv()
        except ws.WebSocketTimeoutException:
            newtext = ""
        fullbuffer = chatbuffertext + newtext
        chatbuffertext = ""
        messages = fullbuffer.split(msg_sep)
        if fullbuffer[-2:] != msg_sep:
            chatbuffertext = messages[-1]
            del messages[-1]

        for message in messages:
            message = message.replace(msg_sep,"").strip()
            if ping_msg in message:
                #PING :tmi.twitch.tv
                websocket.send(pong_msg)
                continue
            if 'PRIVMSG' in message:
                #@badge-info=...;...; :<user.....>.tmi.twitch.tv PRIVMSG #channel :msg
                # separate tags from channel from message
                parts = message.split(' :')
                metadata = parts[0]
                tag_info = yoink_tags(metadata)
                channel_info = parts[1].split(" ")
                #channel = channel_info[2]
                broadcaster = 'broadcaster' in tag_info['badges']
                chatmsg = parts[2].strip()
                if broadcaster and 'all bots must die' in chatmsg.lower():
                    keep_running = False
                username = tag_info['display-name']
                gptbuffertext += f"{username}: {chatmsg}{LINE_BREAK}"

        ### CHATGPT PERSONALITY

        # limit chatgpt buffer
        gptbufferlines = gptbuffertext.split(LINE_BREAK)
        gptbuffertext = LINE_BREAK.join(gptbufferlines[-1*GPT_IN_LINES:])
        # prepare next bot response
        if datetime.now() > last_gpt_write + GPT_INTERVAL:
            # write out the buffer for response
            with open('chatlog.txt','w', encoding='utf-8-sig') as outfile:
                outfile.write(gptbuffertext)
            subprocess.run([sys.executable, "gptpersonalitytest.py"], env=os.environ, shell=True, cwd=os.getcwd())
            last_gpt_write = datetime.now()
        # manage finished bot response
        with open("speech.json","r", encoding='utf-8-sig') as speechfile:
            try:
                gptdata = json.loads(speechfile.read())
            except:
                pass
            if gptdata["timestamp"] > last_gpt_output:
                # this is new speech we haven't seen before!
                # speak into channel. ideally speak through TTS but that's too slow
                speech = gptdata["speech"]
                websocket.send(f"PRIVMSG {my_channel} :(CHROMBALL) {speech}")
                gptbuffertext += f"Chromball: {speech}{LINE_BREAK}"
                last_gpt_output = gptdata["timestamp"]

    websocket.send(f"PRIVMSG {my_channel} :🚫🤖")

if __name__ == '__main__':
    obsws = obs_connect()
    audio_model, data_queue = setup_asr()
    token = fetch_token()
    socket = connect_websocket()
    auth_connection(socket, token)
    run(socket, obsws, audio_model, data_queue)