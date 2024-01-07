# https://cookbook.openai.com/examples/assistants_api_overview_python

import os
import sys
import json
import time
import datetime
from openai import OpenAI
import datetime

client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)

model = "gpt-3.5-turbo-1106"

assistants = {}

# CHANGE THIS USERNAME TO YOUR TWITCH DISPLAY USERNAME
username = "RandolphCherrypepper"
# CHANGE THIS TO ANY NICKNAMES. reads like "You call RandolphCherrpepper <text>", so it needs to make sense as text there.
aliases = "one of Randolph, RCP, or Bryan"

personality = f"Your name is Chromball. You are part of an online community. You are cohosting a stream on Twitch with {username}. You call {username} {aliases}. You can find the bright side of anything."
speech = "Avoid using swear words and vulgarity. Focus on emotional language. Write speech in the style of H.G. Wells and Mary Shelley."

assistant_setup = (
        ('chat_summary', 'Summarize the conversation with one or two short sentences.'),
        ('emotion', f'{personality} You will be given a prompt that includes the topics of discussion. Given the sentiment of the text, describe your emotional response to the prompt. You must say one word. The one word must be one of the following: happy, sad, loved, scared, confident, angry, playful, embarrased.'),
        ('speech', f'{personality} {speech} You will be given a prompt that includes an emotion then topics of discussion. Respond to the prompt with one short sentence colored by the given emotion.'),
    )

for name, instruct in assistant_setup:
    assistants[name] = client.beta.assistants.create(
                     name=name,
                     instructions=instruct,
                     #tools=[],
                     model=model,
                   )

#multi_test_content = """skitkits: i want to jokingly respond "you're taking duck's job"
#RandolphCherrypepper: And it responded to me saying, these assistants it misheard me. But instead of models, we're going to call it a system.
#RandolphCherrypepper: I renamed a variable. I'm taking Duck's job.
#TallPear: how will Chromball feel if i think its a big stinky"""

#test_content = """RandolphCherrypepper: I can touch it up and... like make little improvements And I just don't have that time now to... The thread it created is... we populate the thread and Looks like you're done.
#RandolphCherrypepper: So our input... Chet's a rake. Conversation. Oh, you fuck.
#RandolphCherrypepper: to figure out how to do that better.
#RandolphCherrypepper: I do like that it's naming people.
#RandolphCherrypepper: discussing various topics. This is wrong.
#RandolphCherrypepper: Okay.
#RandolphCherrypepper: Okay, that's kind of great, but now... appropriate to emotion.
#RandolphCherrypepper: So I need to fix that. Tall pair.
#RandolphCherrypepper: How will Chromeball feel if I think it's... I'm sure Tall Fair doesn't... I'm loving the playful banter and This is so generic. Every time this is... I prefer what emotion says.
#RandolphCherrypepper: double checking, no timeouts.
#RandolphCherrypepper: So starting from... So chance a marine with one or two Did we do it? The conversation involves... given the sentiment of the... one word The one word you must... the one word The one word... Must be one of them this might work better if there's more Right now, what I'm really doing... I'm trying to... Prompt engineering. I'm trying to get the prompt Oh, and I forget that I wanted to learn... Studio WordPress It's in Tools, Options."""

test_content = ""
try:
    with open('chatlog.txt', 'r', encoding='utf-8-sig') as infile:
        test_content += infile.read()
except:
    print("failed to open chatlog.txt")
    sys.exit(1)

if test_content == "":
    print("empty chatlog.txt")
    sys.exit(2)

with open('speech.json','r', encoding='utf-8-sig') as prevout:
    try:
        bits = json.loads(prevout.read())
    except:
        bits = {"chatlog": ""}
    if bits["chatlog"] == test_content:
        print("we've already responded to this content.")
        sys.exit(3)

API_WAIT = 0.2

def wait_for_result(who, track):
    thread = track[who]["thread"]
    run = track[who]["run"]
    start = datetime.datetime.now()
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

        match run.status:
            case "completed":
                #print(f"{who} done!")
                messages = client.beta.threads.messages.list(thread_id=thread.id)

                first_message = None
                for message in messages:
                    if first_message is None:
                        first_message = message.content[0].text.value
                    assert message.content[0].type == "text"
                    #print({"role": message.role, "message": message.content[0].text.value})

                return first_message
            case "in_progress" | "queued":
                #interval = str(datetime.datetime.now() - start)
                #print(f"{who} {run.status} (elapsed {interval})")
                #time.sleep(API_WAIT)
                time.sleep(3)
            case _:
                # look for Failure including 'Rate limit reached', pause 20 seconds
                #print(f"something went wrong {run.status} ; {run.last_error}")
                return ""

track = {}

# create threads initially
for assistant, _ in assistant_setup:
    track[assistant] = {}
    track[assistant]["thread"] = client.beta.threads.create()
#print("Threads created, taking a nap.")
time.sleep(20)

start = datetime.datetime.now()

def build_run(assistant, track, content):
    # Create a message into the thread.
    track[assistant]["message"] = client.beta.threads.messages.create(
        thread_id=track[assistant]["thread"].id,
        role="user",
        content=content,
    )
    time.sleep(API_WAIT)

    # Create a run to associate assistant to a thread and wait for responses.
    track[assistant]["run"] = client.beta.threads.runs.create(
        thread_id=track[assistant]["thread"].id,
        assistant_id=assistants[assistant].id,
        #instructions="Please address the user as Jane Doe. The user has a premium account.",
    )
    time.sleep(API_WAIT)

    #print(f"{assistant} thread populated and run ready")
    return track

results = {}

build_run("chat_summary", track, test_content)
chat_summary = results["chat_summary"] = wait_for_result("chat_summary", track)

build_run("emotion", track, chat_summary)
emotion = results["emotion"] = wait_for_result("emotion", track)

build_run("speech", track, f"{emotion}. {chat_summary} ")
speech = results["speech"] = wait_for_result("speech", track)

#print("")
#print("Completed after", datetime.datetime.now() - start)
print("")
for assistant in ['chat_summary', 'emotion', 'speech']:
    print(assistant, results[assistant])
    client.beta.assistants.delete(assistants[assistant].id)

speech = speech.strip()
if speech[0] == '"' and speech[-1] == '"':
    # remove unnecessary surrounding quotes
    speech = speech[1:-1]

with open('speech.json','w', encoding='utf-8-sig') as outfile:
    outfile.write(json.dumps({
        "timestamp": datetime.datetime.now().isoformat(),
        "chatlog": test_content,
        "speech": speech,
        }))