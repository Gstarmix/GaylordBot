import base64
import json
import os
import urllib.request
GUILD_ID = 684734347177230451
QUESTION_CHANNEL_ID = 1055993732505284690
PINNED_FLAG = 1 << 1
THREAD_TITLE = "Read before posting: how this channel works"
SITE_BASE = os.getenv("NOSTAR_SITE_INTERNAL_BASE", "http://preprod:5001").rstrip("/")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = {}
with open(os.path.join(_ROOT, ".env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
DISCORD_TOKEN = env["DISCORD_BOT_TOKEN"].strip().strip('"').strip("'")
BOT_TOKEN = env.get("GSTAR_BOT_TOKEN", "").strip().strip('"').strip("'")
BASIC_AUTH = env.get("NOSTAR_SITE_BASIC_AUTH", "").strip()
PINNED_MD = (
    "Here you ask your questions about **NosTale**, and the **Gstar GPT** "
    "(the assistant of [nostar.fr](https://www.nostar.fr)) answers you. Here is how it works.\n\n"
    "### 1. Create your post\n"
    "Write a **clear title** and give as much detail as possible (your class, your level, "
    "screenshots if useful).\n\n"
    "### 2. The Gstar GPT prepares your topic\n"
    "It rephrases your title if needed and automatically adds the right **tags**. Meanwhile the "
    "topic is locked: that is normal, wait a few seconds.\n\n"
    "### 3. Click « View the topic on Nostar »\n"
    "A button to the site appears under your post. Your question is **already written** there: "
    "just press **Send**. Do it within **10 minutes**, otherwise the topic is removed and you get "
    "your text back by DM.\n\n"
    "### 4. Get your answer\n"
    "The answer appears on the site and arrives on Discord, **under your topic**. The thread then "
    "unlocks: players can add to it or correct it.\n\n"
    "---\n\n"
    "**Good to know**\n"
    "- **Stay on topic** — only questions about NosTale; off-topic posts are removed.\n"
    "- **Daily limit** — you can open 2 topics per day.\n"
    "- **Everything stays public** — each topic ends up on the [site forum](https://www.nostar.fr/forum), "
    "readable by everyone.\n"
    "- **Even faster** — you can also ask the Gstar GPT directly on the site with the chat button.\n"
    "- **No trolling** — avoid trolling or needless flooding.\n"
    "- **One topic per thread** — keep each thread to its original question."
)
def _discord(path):
    req = urllib.request.Request(f"https://discord.com/api/v10{path}",
                                 headers={"Authorization": f"Bot {DISCORD_TOKEN}",
                                          "User-Agent": "DiscordBot (https://nostar.fr, 1.0)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())
def find_pinned_thread_id() -> int | None:
    threads = _discord(f"/guilds/{GUILD_ID}/threads/active").get("threads", [])
    for t in threads:
        if t.get("parent_id") == str(QUESTION_CHANNEL_ID) and (t.get("flags", 0) & PINNED_FLAG):
            return int(t["id"])
    return None
def push(thread_id: int) -> None:
    url = f"{SITE_BASE}/forum/_pinned_info/{thread_id}"
    headers = {"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json",
               "User-Agent": "DiscordBot (https://nostar.fr, 1.0)"}
    if ":" in BASIC_AUTH:
        headers["Authorization"] = "Basic " + base64.b64encode(BASIC_AUTH.encode()).decode()
    data = json.dumps({"title": THREAD_TITLE, "md": PINNED_MD}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"push {thread_id} -> HTTP {r.status} {r.read().decode()[:200]}")
if __name__ == "__main__":
    tid = find_pinned_thread_id()
    if not tid:
        print("Aucun thread épinglé trouvé dans #questions.")
    else:
        print("Thread épinglé:", tid)
        push(tid)