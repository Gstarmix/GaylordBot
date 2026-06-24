import json
import os
import re
import uuid
import urllib.request
GUILD_ID = 684734347177230451
QUESTION_CHANNEL_ID = 1055993732505284690
WEBHOOK_NAME = "Gstar Partage"
NOSTAR_TAG_ID = 1095601816164651089
RANKINGS_CHANNEL_ID = 1248412336042283129
STAR_HELPER = "<:star_singe_helper:1518510073562009710>"
SEPARATOR = "https://www.zupimages.net/up/24/24/stl1.png"
ORANGE = 0xE67E22
LANGS = [("fr","🇫🇷"),("de","🇩🇪"),("it","🇮🇹"),("es","🇪🇸"),
         ("pl","🇵🇱"),("ru","🇷🇺"),("cs","🇨🇿"),("tr","🇹🇷")]
API = "https://discord.com/api/v10"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANNER = os.path.join(_ROOT, "extensions", "assets", "banner_questions.png")
env = {}
with open(os.path.join(_ROOT, ".env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
TOKEN = env["DISCORD_BOT_TOKEN"].strip().strip('"').strip("'")
DAILY_LIMIT = int(env.get("GSTAR_DAILY_FORUM_LIMIT", "2"))
src = open(os.path.join(_ROOT, "extensions", "gstar_answer.py")).read()
VISIT_MIN = int(re.search(r"VISIT_TIMEOUT_SECONDS\s*=\s*(\d+)", src).group(1)) // 60
def api(method, path, payload=None, auth=True):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("User-Agent", "DiscordBot (https://nostar.fr, 1.0)")
    if auth:
        req.add_header("Authorization", "Bot " + TOKEN)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(payload).encode()
    with urllib.request.urlopen(req) as r:
        body = r.read()
        return json.loads(body) if body else {}
guild = api("GET", f"/guilds/{GUILD_ID}")
avatar = (f"https://cdn.discordapp.com/icons/{GUILD_ID}/{guild['icon']}.png?size=256"
          if guild.get("icon") else "https://cdn.discordapp.com/embed/avatars/0.png")
hooks = api("GET", f"/channels/{QUESTION_CHANNEL_ID}/webhooks")
hook = next((h for h in hooks if h.get("name") == WEBHOOK_NAME), None)
if hook is None:
    hook = api("POST", f"/channels/{QUESTION_CHANNEL_ID}/webhooks", {"name": WEBHOOK_NAME})
banner_embed = {"color": ORANGE, "image": {"url": "attachment://banner_questions.png"}}
embed_flow = {
    "title": "Welcome to #questions",
    "description": ("Here you ask your questions about **NosTale** and the **Gstar GPT**, "
                    "the assistant of [nostar.fr](https://www.nostar.fr), answers you. "
                    "Here's how it works."),
    "color": ORANGE,
    "image": {"url": SEPARATOR},
    "fields": [
        {"name": "1️⃣ Create your post", "inline": False,
         "value": ("Write a **clear title** and give as much detail as possible in your message "
                   "(your class, your level, screenshots if useful).")},
        {"name": "2️⃣ The Gstar GPT prepares your topic", "inline": False,
         "value": ("It rephrases your title if needed and automatically adds the right **tags**. "
                   "Meanwhile the topic is locked: that's normal, wait a few seconds.")},
        {"name": "3️⃣ Click « View the topic on Nostar »", "inline": False,
         "value": ("A button to the site appears under your post. Your question is **already written** "
                   f"there: just press **Send**. Do it within **{VISIT_MIN} minutes**, otherwise the "
                   "topic is removed and you get your text back by DM.")},
        {"name": "4️⃣ Get your answer", "inline": False,
         "value": ("The answer appears on the site and arrives here, **under your topic**. "
                   "The thread then unlocks: players can add to it or correct it.")},
    ],
}
embed_rules = {
    "title": "Good to know",
    "color": ORANGE,
    "image": {"url": SEPARATOR},
    "fields": [
        {"name": "🎯 Stay on topic", "inline": False,
         "value": ("This channel is only for questions about **NosTale**. "
                   "An off-topic post is removed automatically (you get your text back by DM).")},
        {"name": "🔢 Daily limit", "inline": False,
         "value": (f"You can open **{DAILY_LIMIT} topics per day**. Beyond that, come back tomorrow "
                   "or message Gstar directly by DM.")},
        {"name": "🌐 Everything stays public", "inline": False,
         "value": ("Each topic ends up on the [site forum](https://www.nostar.fr/forum), "
                   "readable by everyone, even without a Discord account.")},
        {"name": "💬 Even faster", "inline": False,
         "value": ("You can also ask the **Gstar GPT** directly on the site, with the chat button. "
                   "You can then share the conversation with a link.")},
        {"name": f"{STAR_HELPER} Helper ranking", "inline": False,
         "value": f"Your total helper % is shown in <#{RANKINGS_CHANNEL_ID}>."},
        {"name": "🚫 No trolling", "inline": False,
         "value": "Avoid trolling or needless flooding."},
        {"name": "🧵 One topic per thread", "inline": False,
         "value": "Avoid discussing things unrelated to the original question."},
    ],
}
_FLAG_COMPONENTS = [
    {"type": 1, "components": [{"type": 2, "style": 2, "emoji": {"name": fl},
                               "custom_id": f"mflag:{c}"} for c, fl in LANGS[:4]]},
    {"type": 1, "components": [{"type": 2, "style": 2, "emoji": {"name": fl},
                               "custom_id": f"mflag:{c}"} for c, fl in LANGS[4:]]},
]
payload = {
    "username": "Gstar GPT",
    "avatar_url": avatar,
    "thread_name": "📌 Read before posting: how this channel works",
    "embeds": [banner_embed, embed_flow, embed_rules],
    "components": _FLAG_COMPONENTS,
    "allowed_mentions": {"parse": []},
}
boundary = uuid.uuid4().hex
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
        f'Content-Type: application/json\r\n\r\n').encode() + json.dumps(payload).encode() + b"\r\n"
body += (f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; '
         f'filename="banner_questions.png"\r\nContent-Type: image/png\r\n\r\n').encode()
body += open(BANNER, "rb").read() + b"\r\n" + f"--{boundary}--\r\n".encode()
req = urllib.request.Request(f"{API}/webhooks/{hook['id']}/{hook['token']}?wait=true",
                             data=body, method="POST")
req.add_header("User-Agent", "DiscordBot (https://nostar.fr, 1.0)")
req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
with urllib.request.urlopen(req) as r:
    msg = json.loads(r.read())
thread_id = msg["channel_id"]
print("sujet créé:", thread_id, "| message:", msg["id"])
res = api("PATCH", f"/channels/{thread_id}",
          {"applied_tags": [str(NOSTAR_TAG_ID)], "flags": 2, "locked": True, "archived": False})
print("tags:", res.get("applied_tags"), "| épinglé:", bool(res.get("flags", 0) & 2),
      "| verrouillé:", res.get("thread_metadata", {}).get("locked"))
print(f"URL: https://discord.com/channels/{GUILD_ID}/{thread_id}")