import os
import re
import json
import time
import pathlib
import urllib.request
import urllib.error
ENV = "/app/gaylord/.env"
THREAD_ID = "1330649463257305098"
SAURON_BOT = "1031590974658465872"
API = "https://discord.com/api/v10"
OUT = pathlib.Path("/app/nostar/preprod/_inspirations/evaluation_discord")
MED = OUT / "medias"
UA = "DiscordBot (https://nostar.fr, 1.0)"
def load_token():
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("DISCORD_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DISCORD_BOT_TOKEN introuvable dans " + ENV)
TOKEN = load_token()
HEAD = {"Authorization": "Bot " + TOKEN, "User-Agent": UA}
def api_get(url):
    for _ in range(6):
        req = urllib.request.Request(url, headers=HEAD)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("Retry-After", "2")) + 0.5)
                continue
            raise SystemExit(f"HTTP {e.code} sur {url}\n{e.read().decode('utf-8', 'replace')[:400]}")
    raise SystemExit("Trop de 429")
def clean(name):
    return re.sub(r"_{2,}", "_", re.sub(r"[^a-zA-Z0-9_.-]", "_", name)).strip("_")
def download(url, fname):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                (MED / fname).write_bytes(r.read())
                return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2)
                continue
            return False
        except Exception:
            return False
    return False
messages, before = [], None
while True:
    url = f"{API}/channels/{THREAD_ID}/messages?limit=100" + (f"&before={before}" if before else "")
    batch = api_get(url)
    if not batch:
        break
    messages += batch
    before = batch[-1]["id"]
    time.sleep(0.4)
    if len(batch) < 100:
        break
messages.sort(key=lambda m: int(m["id"]))
MED.mkdir(parents=True, exist_ok=True)
lines, n_med, n_emb = [], 0, 0
for m in messages:
    a = m.get("author", {})
    entry = ["---", f"**Auteur :** {a.get('username', '?')} ({a.get('id', '?')})",
             f"**Date :** {m.get('timestamp', '')[:19].replace('T', ' ')}"]
    if m.get("content"):
        entry.append("**Contenu :**\n" + m["content"])
    for att in m.get("attachments", []):
        fn = clean(f"{m['id']}_{att.get('filename', 'fichier')}")
        ct = att.get("content_type") or ""
        if download(att["url"], fn):
            n_med += 1
            entry.append((f"![{att.get('filename')}](medias/{fn})" if ct.startswith("image")
                          else f"[Fichier: {att.get('filename')}](medias/{fn})"))
    for emb in m.get("embeds", []):
        n_emb += 1
        el = ["**Embed :**"]
        if emb.get("title"):
            el.append(f"**Titre :** {emb['title']}")
        if emb.get("description"):
            el.append(emb["description"])
        for f in emb.get("fields", []):
            el.append(f"**{f.get('name', '')} :** {f.get('value', '')}")
        for key in ("image", "thumbnail"):
            u = (emb.get(key) or {}).get("url")
            if u:
                fn = clean(f"{m['id']}_embed_{key}.png")
                if download(u, fn):
                    n_med += 1
                    el.append(f"![embed {key}](medias/{fn})")
        entry.append("\n".join(el))
    lines.append("\n".join(entry) + "\n")
OUT.joinpath("dump.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Messages: {len(messages)} | médias: {n_med} | embeds: {n_emb}")
print("Sortie:", OUT)