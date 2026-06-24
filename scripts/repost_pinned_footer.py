import json
import os
import time
import uuid
import urllib.request
import urllib.error
GUILD_ID = 684734347177230451
FOOTER = "Use the flags to translate"
SEPARATOR = "https://www.zupimages.net/up/24/24/stl1.png"
ORANGE = 0xE67E22
WEBHOOK_NAME = "Gstar Partage"
API = "https://discord.com/api/v10"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(_ROOT, "extensions", "assets")
FORUMS = {
    "questions":  (1055993732505284690, "banner_questions.png",  "1095601816164651089"),
    "estimates":  (1028316725457981440, "banner_appraisals.png", "1028343824528986223"),
    "trades":     (1107401292655120435, "banner_trades.png",     "1107402307651510412"),
    "activities": (1034240207219855402, "banner_activities.png", "1518491970526384219"),
}
LANGS = [("fr", "🇫🇷"), ("de", "🇩🇪"), ("it", "🇮🇹"), ("es", "🇪🇸"),
         ("pl", "🇵🇱"), ("ru", "🇷🇺"), ("cs", "🇨🇿"), ("tr", "🇹🇷")]
FLAG_COMPONENTS = [
    {"type": 1, "components": [{"type": 2, "style": 2, "emoji": {"name": fl},
                               "custom_id": f"mflag:{c}"} for c, fl in LANGS[:4]]},
    {"type": 1, "components": [{"type": 2, "style": 2, "emoji": {"name": fl},
                               "custom_id": f"mflag:{c}"} for c, fl in LANGS[4:]]},
]
env = {}
with open(os.path.join(_ROOT, ".env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
TOKEN = env["DISCORD_BOT_TOKEN"].strip().strip('"').strip("'")
UA = "DiscordBot (https://nostar.fr, 1.0)"
def api(method, path, payload=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Authorization", "Bot " + TOKEN)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(payload).encode()
    for _ in range(6):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
                return json.loads(b) if b else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("Retry-After", "2")) + 0.5); continue
            print("  HTTP", e.code, e.read().decode()[:160]); raise
        except Exception:
            time.sleep(3)
    raise RuntimeError("abandon")
def clean_embed(e):
    ne = {}
    for k in ("title", "description"):
        if e.get(k):
            ne[k] = e[k]
    ne["color"] = e.get("color", ORANGE)
    if e.get("fields"):
        ne["fields"] = [{"name": f["name"], "value": f["value"],
                         "inline": f.get("inline", False)} for f in e["fields"]]
    if e.get("image", {}).get("url"):
        ne["image"] = {"url": e["image"]["url"]}
    if e.get("footer", {}).get("text"):
        ne["footer"] = {"text": e["footer"]["text"]}
    return ne
guild = api("GET", f"/guilds/{GUILD_ID}")
avatar = (f"https://cdn.discordapp.com/icons/{GUILD_ID}/{guild['icon']}.png?size=256"
          if guild.get("icon") else "https://cdn.discordapp.com/embed/avatars/0.png")
for name, (fid, banner_file, tag_id) in FORUMS.items():
    print(f"\n### {name} ({fid})")
    active = api("GET", f"/guilds/{GUILD_ID}/threads/active")
    olds = [t for t in active["threads"]
            if t.get("parent_id") == str(fid) and t["name"].startswith("📌 Read before posting")]
    if not olds:
        print("  pas de post info trouvé, skip"); continue
    to_delete = [t["id"] for t in olds]
    src = next((t for t in olds if t.get("flags", 0) & 2), olds[0])
    old = src
    old_id = src["id"]
    starter = api("GET", f"/channels/{old_id}/messages/{old_id}")
    embeds = starter.get("embeds", [])
    content = [clean_embed(e) for e in embeds if (e.get("title") or e.get("description") or e.get("fields"))]
    if not content:
        print("  aucun embed de contenu trouvé, skip"); continue
    content[-1]["footer"] = {"text": FOOTER}
    banner_embed = {"color": ORANGE, "image": {"url": f"attachment://{banner_file}"}}
    new_embeds = [banner_embed] + content
    hooks = api("GET", f"/channels/{fid}/webhooks")
    hook = next((h for h in hooks if h.get("name") == WEBHOOK_NAME), None)
    if hook is None:
        hook = api("POST", f"/channels/{fid}/webhooks", {"name": WEBHOOK_NAME})
    payload = {
        "username": "Gstar GPT", "avatar_url": avatar,
        "thread_name": old["name"][:100],
        "embeds": new_embeds, "components": FLAG_COMPONENTS,
        "allowed_mentions": {"parse": []},
    }
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
            f'Content-Type: application/json\r\n\r\n').encode() + json.dumps(payload).encode() + b"\r\n"
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; '
             f'filename="{banner_file}"\r\nContent-Type: image/png\r\n\r\n').encode()
    body += open(os.path.join(ASSETS, banner_file), "rb").read() + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{API}/webhooks/{hook['id']}/{hook['token']}?wait=true",
                                 data=body, method="POST")
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                msg = json.loads(r.read()); break
        except Exception as e:
            print("  net", repr(e)[:50]); time.sleep(4)
    new_id = msg["channel_id"]
    for oid in to_delete:
        api("DELETE", f"/channels/{oid}"); time.sleep(0.8)
    api("PATCH", f"/channels/{new_id}",
        {"applied_tags": [str(tag_id)], "flags": 2, "locked": True, "archived": False})
    print(f"  nouveau: {new_id} (tag {tag_id}, pin+lock) | {len(to_delete)} ancien(s) supprimé(s)")
    time.sleep(1.0)
print("\n=== terminé ===")