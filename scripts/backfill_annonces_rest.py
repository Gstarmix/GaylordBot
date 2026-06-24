import json
import time
import urllib.request
import urllib.error
GUILD = 684734347177230451
API = "https://discord.com/api/v10"
ANNOUNCE_ROLE_IDS = [
    "1518213206516957244",
    "1518213208173707374",
    "1518213209125814273",
    "1518213210455539872",
]
LOG = "/app/gaylord/.logs/backfill_annonces.log"
env = {}
for line in open("/app/gaylord/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k] = v
TOKEN = env["DISCORD_BOT_TOKEN"]
def log(msg):
    line = f"[{int(time.time())}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
def api(method, path, payload=None, audit=None):
    net_fails = 0
    while True:
        req = urllib.request.Request(API + path, method=method)
        req.add_header("User-Agent", "DiscordBot (https://nostar.fr, 1.0)")
        req.add_header("Authorization", "Bot " + TOKEN)
        if audit:
            req.add_header("X-Audit-Log-Reason", audit)
        if payload is not None:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(payload).encode()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    retry = json.loads(e.read()).get("retry_after", 1.0)
                except Exception:
                    retry = 1.0
                time.sleep(float(retry) + 0.3)
                continue
            if e.code in (500, 502, 503):
                time.sleep(2)
                continue
            return e.code, None
        except Exception as e:
            net_fails += 1
            if net_fails > 8:
                log(f"réseau KO persistant sur {path} ({e!r}) — skip.")
                return 0, None
            time.sleep(min(2 ** net_fails, 30))
            continue
def main():
    want = set(ANNOUNCE_ROLE_IDS)
    after = "0"
    scanned = patched = skipped = errors = 0
    log("=== Backfill démarré ===")
    while True:
        status, members = api("GET", f"/guilds/{GUILD}/members?limit=1000&after={after}")
        if status != 200 or not members:
            if status != 200:
                log(f"Liste membres: HTTP {status} (after={after}) — arrêt.")
            break
        for m in members:
            user = m.get("user", {})
            uid = user.get("id")
            after = uid
            if user.get("bot"):
                continue
            scanned += 1
            current = set(m.get("roles", []))
            if want.issubset(current):
                skipped += 1
                continue
            new_roles = list(current | want)
            st, _ = api("PATCH", f"/guilds/{GUILD}/members/{uid}",
                        {"roles": new_roles}, audit="Backfill roles d'annonces (S2)")
            if st in (200, 204):
                patched += 1
            else:
                errors += 1
                log(f"PATCH {uid} -> HTTP {st}")
            time.sleep(0.35)
        log(f"... scannés={scanned} patchés={patched} déjà_ok={skipped} erreurs={errors}")
        if len(members) < 1000:
            break
    log(f"=== Backfill terminé : scannés={scanned}, patchés={patched}, "
        f"déjà_ok={skipped}, erreurs={errors} ===")
if __name__ == "__main__":
    main()