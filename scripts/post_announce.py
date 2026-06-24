import json, os, re, time, uuid, urllib.request
GUILD_ID = 684734347177230451
ORANGE = 0xE67E22
SEP = "https://www.zupimages.net/up/24/24/stl1.png"
FOOTER = "Use the flags to translate"
TEST_CHANNEL = 1518682000217735268
ANNOUNCE = {
    "nostar":    {"channel": 917332748866306088,  "role": 1518213209125814273, "banner": "banner_site.png",      "color": 0x2ECC71},
    "discord":   {"channel": 1020010915657170955, "role": 1518213210455539872, "banner": "banner_discord.png",   "color": 0x5865F2},
    "youtube":   {"channel": 1420622426777325599, "role": 1518213206516957244, "banner": "banner_youtube.png",   "color": 0xFF0000},
    "instagram": {"channel": 1420622471253725184, "role": 1518213208173707374, "banner": "banner_instagram.png", "color": 0xE1306C},
}
FLAG_LANGS = [("fr","🇫🇷"),("de","🇩🇪"),("it","🇮🇹"),("es","🇪🇸"),("pl","🇵🇱"),("ru","🇷🇺"),("cs","🇨🇿"),("tr","🇹🇷")]
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(_ROOT, "extensions", "assets")
env = {}
with open(os.path.join(_ROOT, ".env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); env[k] = v
TOKEN = env["DISCORD_BOT_TOKEN"].strip().strip('"').strip("'")
H = {"Authorization": "Bot " + TOKEN, "User-Agent": "DiscordBot (https://nostar.fr, 1.0)"}
def nodash(s):
    return (s or "").replace("—", "-").replace("–", "-")
def _op(req):
    for _ in range(8):
        try:
            return urllib.request.urlopen(req, timeout=30).read()
        except Exception:
            time.sleep(3)
    raise RuntimeError("network KO")
def _ua(url):
    r = urllib.request.Request(url)
    r.add_header("User-Agent", "Mozilla/5.0 (compatible; Discordbot/2.0)")
    r.add_header("Accept-Language", "en")
    return _op(r).decode("utf-8", "ignore")
def _og_image(html):
    m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    return m.group(1).replace("&amp;", "&") if m else ""
def flag_rows():
    return [{"type": 1, "components": [{"type": 2, "style": 2, "emoji": {"name": fl}, "custom_id": f"mflag:{c}"} for c, fl in FLAG_LANGS[:4]]},
            {"type": 1, "components": [{"type": 2, "style": 2, "emoji": {"name": fl}, "custom_id": f"mflag:{c}"} for c, fl in FLAG_LANGS[4:]]}]
def fetch_youtube(url):
    vid = re.search(r"(?:v=|youtu\.be/|embed/)([\w-]{11})", url).group(1)
    oe = json.loads(_ua(f"https://www.youtube.com/oembed?url={url}&format=json"))
    html = _ua(f"https://www.youtube.com/watch?v={vid}")
    thumb = _og_image(html) or f"https://i.ytimg.com/vi/{vid}/sddefault.jpg"
    chs = re.findall(r'"chapterRenderer":\{"title":\{"simpleText":"(.*?)"\}.*?"timeRangeStartMillis":(\d+)', html)
    mmss = lambda ms: f"{int(ms)//60000}:{int(ms)//1000%60:02d}"
    tc = "\n".join(f"`{mmss(ms)}` {nodash(t)}" for t, ms in chs[:12])
    return {"title": nodash(oe["title"]), "author": oe["author_name"], "thumbnail": thumb, "timecodes": tc}
def fetch_instagram(url):
    return {"image": _og_image(_ua(url))}
def post_announce(typ, *, title, body, link=None, image=None, button=None, to_test=True):
    cfg = ANNOUNCE[typ]
    channel = TEST_CHANNEL if to_test else cfg["channel"]
    content = f"<@&{cfg['role']}>" + (f" {link}" if link and typ in ("youtube", "instagram") else "")
    content_embed = {"title": title, "description": body, "color": cfg["color"],
                     "image": {"url": image or SEP}, "footer": {"text": FOOTER}}
    embeds = [{"color": ORANGE, "image": {"url": f"attachment://{cfg['banner']}"}}, content_embed]
    comps = []
    if button:
        comps.append({"type": 1, "components": [{"type": 2, "style": 5, "label": button["label"],
                      "emoji": {"name": button["emoji"]}, "url": button["url"]}]})
    comps += flag_rows()
    payload = {"content": content, "embeds": embeds, "components": comps,
               "allowed_mentions": {"roles": [cfg["role"]]}}
    b = uuid.uuid4().hex
    fp = os.path.join(ASSETS, cfg["banner"])
    body_bytes = (f'--{b}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n').encode() + json.dumps(payload).encode() + b"\r\n"
    body_bytes += (f'--{b}\r\nContent-Disposition: form-data; name="files[0]"; filename="{cfg["banner"]}"\r\nContent-Type: image/png\r\n\r\n').encode() + open(fp, "rb").read() + b"\r\n" + f"--{b}--\r\n".encode()
    req = urllib.request.Request(f"https://discord.com/api/v10/channels/{channel}/messages", data=body_bytes, method="POST")
    for k, v in H.items():
        req.add_header(k, v)
    req.add_header("Content-Type", f"multipart/form-data; boundary={b}")
    msg = json.loads(_op(req))
    print(f"[{typ}] posté dans {channel} -> {msg.get('id')}")
    return msg
if __name__ == "__main__":
    print("Importer ce module et appeler post_announce(...). Voir les exemples ci-dessus.")