import json, os, time, uuid, urllib.request, urllib.error
ORANGE = 0xE67E22
RED = 0xED4245
SEP = "https://www.zupimages.net/up/24/24/stl1.png"
FOOTER = "Use the flags to translate"
API = "https://discord.com/api/v10"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(_ROOT, "extensions", "assets")
FLAG_LANGS = [("fr","🇫🇷"),("de","🇩🇪"),("it","🇮🇹"),("es","🇪🇸"),("pl","🇵🇱"),("ru","🇷🇺"),("cs","🇨🇿"),("tr","🇹🇷")]
env = {}
with open(os.path.join(_ROOT, ".env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); env[k] = v
TOKEN = env["DISCORD_BOT_TOKEN"].strip().strip('"').strip("'")
H = {"Authorization": "Bot " + TOKEN, "User-Agent": "DiscordBot (https://nostar.fr, 1.0)"}
def api(method, path, payload=None):
    req = urllib.request.Request(API + path, method=method)
    for k, v in H.items(): req.add_header(k, v)
    if payload is not None:
        req.add_header("Content-Type", "application/json"); req.data = json.dumps(payload).encode()
    for _ in range(6):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read(); return json.loads(b) if b else {}
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(float(e.headers.get("Retry-After","2"))+0.5); continue
            print("  HTTP", e.code, e.read().decode()[:140]); return None
        except Exception: time.sleep(3)
    return None
def flags(prefix):
    return [{"type":1,"components":[{"type":2,"style":2,"emoji":{"name":fl},"custom_id":f"{prefix}:{c}"} for c,fl in FLAG_LANGS[:4]]},
            {"type":1,"components":[{"type":2,"style":2,"emoji":{"name":fl},"custom_id":f"{prefix}:{c}"} for c,fl in FLAG_LANGS[4:]]}]
BOT_ID = api("GET", "/users/@me")["id"]
def post(channel, embed, components=None, banner_file=None):
    payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    if components: payload["components"] = components
    if banner_file is None:
        api("POST", f"/channels/{channel}/messages", payload); time.sleep(1.0); return
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n').encode()
    body += json.dumps(payload).encode() + b"\r\n"
    fn = os.path.basename(banner_file)
    ctype = "image/gif" if fn.endswith(".gif") else "image/png"
    body += (f'--{b}\r\nContent-Disposition: form-data; name="files[0]"; filename="{fn}"\r\nContent-Type: {ctype}\r\n\r\n').encode()
    body += open(banner_file, "rb").read() + b"\r\n" + f"--{b}--\r\n".encode()
    req = urllib.request.Request(f"{API}/channels/{channel}/messages", data=body, method="POST")
    for k, v in H.items(): req.add_header(k, v)
    req.add_header("Content-Type", f"multipart/form-data; boundary={b}")
    for _ in range(5):
        try:
            urllib.request.urlopen(req, timeout=60); break
        except Exception as e: print("  net", repr(e)[:40]); time.sleep(4)
    time.sleep(1.0)
def purge(channel):
    msgs = api("GET", f"/channels/{channel}/messages?limit=50") or []
    mine = [m["id"] for m in msgs if m["author"]["id"] == BOT_ID]
    for mid in mine:
        api("DELETE", f"/channels/{channel}/messages/{mid}"); time.sleep(0.7)
    print(f"  purgé {len(mine)} ancien(s)")
def emb(title, desc, color=ORANGE, image=SEP, footer=False):
    e = {"title": title, "description": desc, "color": color, "image": {"url": image}}
    if footer: e["footer"] = {"text": FOOTER}
    return e
I18N = json.loads(open(os.path.join(ASSETS, "act4_info_i18n.json")).read())
xpsrc = open(os.path.join(_ROOT, "extensions", "xp_commands.py")).read().splitlines()
ns = {"CMD_CHANNEL_ID": 704586556446343179}
exec("\n".join(xpsrc[26:61]), ns)
INTRO, COMBAT, HERO = ns["INTRO"], ns["COMBAT"], ns["HERO"]
HONEY_T = "⛔ Do not post here"
HONEY_D = ("This channel is an **automated anti-bot trap**. Any message posted here "
           "triggers an **instant, automatic ban**. There is nothing to do here, just move on.")
print("### a4-bot-info"); CH = 1131254481212940400
purge(CH)
post(CH, {"color": ORANGE, "image": {"url": "attachment://banner_a4botinfo.png"}}, banner_file=os.path.join(ASSETS, "banner_a4botinfo.png"))
(t1, d1), (t2, d2) = I18N["a4bot"]["en"]
post(CH, emb(t1, d1))
post(CH, emb(t2, d2, footer=True), components=flags("a4flag"))
print("### pourcents-a4"); CH = 955172663410692166
purge(CH)
post(CH, {"color": ORANGE, "image": {"url": "attachment://banner_pcta4.png"}}, banner_file=os.path.join(ASSETS, "banner_pcta4.png"))
pt, pd = I18N["pct"]["en"]
post(CH, emb(pt, pd, footer=True), components=flags("pctflag"))
print("### xp-commands"); CH = 715194932620689481
purge(CH)
post(CH, {"color": ORANGE, "image": {"url": "attachment://banner_xpcommands.png"}}, banner_file=os.path.join(ASSETS, "banner_xpcommands.png"))
post(CH, emb(INTRO[0], INTRO[1]))
post(CH, {"title": COMBAT[0], "description": COMBAT[1], "color": ORANGE, "image": {"url": "attachment://combat.gif"}}, banner_file=os.path.join(ASSETS, "combat.gif"))
post(CH, {"title": HERO[0], "description": HERO[1], "color": ORANGE, "image": {"url": "attachment://hero.gif"}, "footer": {"text": FOOTER}}, components=flags("xpflag"), banner_file=os.path.join(ASSETS, "hero.gif"))
print("### honeypot"); CH = 1518210480542584912
purge(CH)
post(CH, {"color": ORANGE, "image": {"url": "attachment://banner_honeypot.png"}}, banner_file=os.path.join(ASSETS, "banner_honeypot.png"))
post(CH, emb(HONEY_T, HONEY_D, color=RED, footer=True), components=flags("honeyflag"))
print("=== terminé ===")