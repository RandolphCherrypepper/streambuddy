# Stream Buddy
This is an artificial intelligent cohost for your stream. It runs on various machine learning algorithms to put it all together.

# Setup

## Veadotube
https://veado.tube/

Used to animate the avatar given speech.

Will need 1, 2, or 4 images of the cohost avatar.

### Stable Diffusion
https://github.com/AUTOMATIC1111/stable-diffusion-webui
or
https://github.com/comfyanonymous/ComfyUI

Not required, but it is a fun way to generate an initial avatar.

### ebsynth or HyperReenact
https://ebsynth.com/
or
https://github.com/StelaBou/HyperReenact

Not required. Generate the avatar's expressions to match a single image or video of a facial expression or facial expressions (e.g. a picture/video of your own face being expressive).

## Third Party Account Requirements
* Twitch App required in the Twitch API console. https://dev.twitch.tv/docs/api/get-started/
* ChatGPT developer API key. https://platform.openai.com/docs/quickstart/account-setup

## Python
Install Python 3.10 (or better, but probably 3.10 is best for now).
Optionally install and run a virtual environment (such as `pip -m venv StreamBuddy`).

## Python Dependencies
See requirements.txt. Typical usage is `pip install -r requirements.txt` (after activating the virtual environment as desired).

## Initial Environment
Copy example.env to .env for Mac/Linux, or exampleenv.bat to env.bat for Windows.
Edit .env or env.bat and populate the `<redacted>` values with the keys and so forth.

Leave device code blank for now.

## Obtain Device Code

To get a Twitch Device Code, run the following (in Linux, Windows is similar):

```
source .env
curl --location 'https://id.twitch.tv/oauth2/device' --form "client_id=\"${TWITCH_AUTH_CLIENTID}\"" --form "scopes=\"${TWITCH_AUTH_SCOPES}\"" > devicecode.txt
```

Extract the string after `"device_code":` from `devicecode.txt`. Put that into .env or env.bat.

## OBS
CC is pushed into OBS using the built-in OBS websocket. OBS must be at least version 27.

Copy exampleconfig.toml to config.toml.

Check "Enable Websocket server" in `Tools > WebSocket Server Settings`. Click "Show Connect Info". Change the IP, Port, and Password in config.toml to match.

## Virtual Cables
https://vb-audio.com/Cable/index.htm

Needed to connect TTS audio to Veadotube and to OBS.

## Code Changes
Update `username` and `aliases` in `gptpersonalitytest.py`.
Update `my_username` in `theprogram.py`.

## Blank files.
Create empty files called chatlog.txt and speech.json.

# Running

## Activate the environment
For Mac/Linux, make sure to `source .env`. For Windows, make sure to run `env.bat`.

## Start
`python theprogram.py`

It takes some time to kick off.
