import json
import os
import sys
import time
import urllib.request
import urllib.error
GUILD_ID = 684734347177230451
VERIFIE_ROLE_ID = 1518347349011988490
VIEW = 1 << 10
PUBLIC_CATEGORY_IDS = {
    684734349106479106,
    815425566168973362,
    1028314384440766485,
    684734349106479105,
    950925648854147142,
    706882223948824657,
    1122918711855161354,
    1170068126302474311,
}
ALWAYS_VISIBLE_IDS = {
    1518326390963966065,
}
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = {}
with open(os.path.join(_ROOT, ".env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
TOKEN = env["DISCORD_BOT_TOKEN"].strip().strip('"').strip("'")
H = {"Authorization": f"Bot {TOKEN}", "User-Agent": "DiscordBot (https://nostar.fr, 1.0)"}
UNDO = "--undo" in sys.argv
def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    h = dict(H)
    if payload is not None:
        h["Content-Type"] = "application/json"
    for _ in range(8):
        try:
            req = urllib.request.Request(f"https://discord.com/api/v10{path}", data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=30) as r:
                b = r.read()
                return r.status, (json.loads(b) if b else {})
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("Retry-After", "2")) + 0.5)
                continue
            print("  HTTP", e.code, e.read().decode()[:140]); return e.code, None
        except Exception:
            time.sleep(3)
    return 0, None
def overwrites(ch):
    return {o["id"]: o for o in ch.get("permission_overwrites", [])}
def ev_hidden(ch):
    o = overwrites(ch).get(str(GUILD_ID))
    return bool(o and (int(o.get("deny", "0")) & VIEW))
def set_ow(cid, oid, otype, allow_view, *, base_allow=0, base_deny=0):
    allow, deny = base_allow, base_deny
    if allow_view:
        allow |= VIEW; deny &= ~VIEW
    else:
        deny |= VIEW; allow &= ~VIEW
    api("PUT", f"/channels/{cid}/permissions/{oid}",
        {"type": otype, "allow": str(allow), "deny": str(deny)})
    time.sleep(0.4)
def gate_channel(ch, visible):
    ow = overwrites(ch)
    ev = ow.get(str(GUILD_ID), {})
    ver = ow.get(str(VERIFIE_ROLE_ID), {})
    set_ow(ch["id"], GUILD_ID, 0, visible,
           base_allow=int(ev.get("allow", "0")), base_deny=int(ev.get("deny", "0")))
    set_ow(ch["id"], VERIFIE_ROLE_ID, 0, (not UNDO),
           base_allow=int(ver.get("allow", "0")), base_deny=int(ver.get("deny", "0")))
def main():
    st, chans = api("GET", f"/guilds/{GUILD_ID}/channels")
    if not chans:
        print("Impossible de lister les salons."); return
    cats = {c["id"]: c for c in chans if c["type"] == 4}
    done = 0
    for c in chans:
        if c["type"] == 4:
            if int(c["id"]) in PUBLIC_CATEGORY_IDS:
                gate_channel(c, UNDO); done += 1
                print(("[undo] " if UNDO else "") + f"catégorie {c['name']} -> {'@everyone' if UNDO else 'Vérifié only'}")
            continue
        parent = c.get("parent_id")
        if parent is None or int(parent) not in PUBLIC_CATEGORY_IDS:
            continue
        cid = int(c["id"])
        if cid in ALWAYS_VISIBLE_IDS:
            gate_channel(c, True); done += 1
            print(f"  {c['name']} -> VISIBLE @everyone (verif)")
            continue
        if not UNDO and ev_hidden(c):
            print(f"  {c['name']} -> déjà caché, on ne touche pas")
            continue
        gate_channel(c, UNDO); done += 1
        print(("[undo] " if UNDO else "") + f"  {c['name']} -> {'@everyone' if UNDO else 'Vérifié only'}")
    print(f"\n=== {'UNDO ' if UNDO else ''}terminé : {done} salons/catégories traités ===")
    if not UNDO:
        print("Vérifie qu'un compte SANS Vérifié ne voit que #welcome (+#rules), puis qu'après "
              "« I accept » + choix de langue il voit tout.")
if __name__ == "__main__":
    main()