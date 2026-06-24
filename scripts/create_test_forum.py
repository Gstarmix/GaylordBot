import json
import urllib.request
import urllib.error
from pathlib import Path
API = "https://discord.com/api/v10"
GUILD_ID = "684734347177230451"
TEST_USER_ID = "200750717437345792"
FORUM_NAME = "test-questions-claude"
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
READ_MESSAGE_HISTORY = 1 << 16
CREATE_PUBLIC_THREADS = 1 << 35
SEND_MESSAGES_IN_THREADS = 1 << 38
USER_ALLOW = (VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY
              | CREATE_PUBLIC_THREADS | SEND_MESSAGES_IN_THREADS)
def _token() -> str:
    for line in Path("/root/workspace/gaylord/.env").read_text().splitlines():
        line = line.strip()
        if line.startswith("DISCORD_BOT_TOKEN=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DISCORD_BOT_TOKEN introuvable dans .env")
def _req(method: str, path: str, token: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "GstarBot (nostar, 1.0)")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} sur {method} {path} : {e.read().decode()[:500]}")
        raise
def main():
    token = _token()
    me = _req("GET", "/users/@me", token)
    bot_id = me["id"]
    print(f"Bot connecté : {me.get('username')} ({bot_id})")
    channels = _req("GET", f"/guilds/{GUILD_ID}/channels", token)
    category = next(
        (c for c in channels
         if c.get("type") == 4 and "singerie" in (c.get("name") or "").lower()),
        None,
    )
    if not category:
        cats = [c["name"] for c in channels if c.get("type") == 4]
        raise SystemExit(f"Catégorie « singeries » introuvable. Catégories : {cats}")
    print(f"Catégorie trouvée : {category['name']} ({category['id']})")
    existing = next(
        (c for c in channels
         if c.get("type") == 15 and c.get("name") == FORUM_NAME),
        None,
    )
    if existing:
        print(f"⚠️ Le forum « {FORUM_NAME} » existe déjà : {existing['id']} — rien à créer.")
        return
    body = {
        "name": FORUM_NAME,
        "type": 15,
        "parent_id": category["id"],
        "topic": "Salon de test privé (Claude) — features bot questions.",
        "permission_overwrites": [
            {"id": GUILD_ID, "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL)},
            {"id": TEST_USER_ID, "type": 1, "allow": str(USER_ALLOW), "deny": "0"},
            {"id": bot_id, "type": 1, "allow": str(VIEW_CHANNEL | SEND_MESSAGES), "deny": "0"},
        ],
    }
    created = _req("POST", f"/guilds/{GUILD_ID}/channels", token, body)
    print(f"✅ Forum créé : #{created['name']} — ID = {created['id']}")
    print(f"   parent (catégorie) = {created.get('parent_id')}")
if __name__ == "__main__":
    main()