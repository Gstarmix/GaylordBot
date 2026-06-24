import asyncio
import os
import aiohttp
SITE_BASE = os.getenv("NOSTAR_SITE_INTERNAL_BASE", "http://127.0.0.1:5001").rstrip("/")
BOT_TOKEN = os.getenv("GSTAR_BOT_TOKEN", "")
SITE_BASIC_AUTH = os.getenv("NOSTAR_SITE_BASIC_AUTH", "").strip()
REQUEST_TIMEOUT = 15
def _basic_auth():
    if ":" in SITE_BASIC_AUTH:
        user, pwd = SITE_BASIC_AUTH.split(":", 1)
        return aiohttp.BasicAuth(user, pwd)
    return None
async def invalidate_forum_cache(channel_id: int, delay: float = 0.0) -> None:
    if delay:
        await asyncio.sleep(delay)
    url = f"{SITE_BASE}/forum/_invalidate/{channel_id}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                await resp.read()
                print(f"[site_api] invalidate forum {channel_id} -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[site_api] invalidate forum {channel_id} échec : {exc!r}", flush=True)
async def push_forum_turn(channel_id: int, role: str, md: str,
                          avatar: str = "", name: str = "", user_id: int = 0) -> None:
    md = (md or "").strip()
    if not md:
        return
    url = f"{SITE_BASE}/forum/_gstar_answer/{int(channel_id)}"
    payload = {"md": md, "role": role}
    if avatar:
        payload["avatar"] = avatar
    if name:
        payload["name"] = name
    if user_id:
        payload["user_id"] = int(user_id)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json=payload,
                auth=_basic_auth(),
            ) as resp:
                await resp.read()
                print(f"[site_api] forum_turn {channel_id} role={role} -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[site_api] forum_turn {channel_id} échec : {exc!r}", flush=True)
async def set_thread_title(channel_id: int, title: str) -> None:
    title = (title or "").strip()
    if not title:
        return
    url = f"{SITE_BASE}/forum/_thread_title/{int(channel_id)}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json={"title": title},
                auth=_basic_auth(),
            ) as resp:
                await resp.read()
                print(f"[site_api] thread_title {channel_id} -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[site_api] thread_title {channel_id} échec : {exc!r}", flush=True)
async def steam_news_recent() -> list:
    url = f"{SITE_BASE}/gstar-gpt/steam-news"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return (data.get("items") or []) if data.get("ok") else []
    except Exception as exc:
        print(f"[site_api] steam_news_recent échec : {exc!r}", flush=True)
        return []
async def steam_news_item(gid: str, lang: str) -> "dict | None":
    url = f"{SITE_BASE}/gstar-gpt/steam-news?gid={gid}&lang={lang}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("item") if data.get("ok") else None
    except Exception as exc:
        print(f"[site_api] steam_news_item échec : {exc!r}", flush=True)
        return None
async def push_pinned_info(channel_id: int, title: str, md: str) -> None:
    title = (title or "").strip()
    md = (md or "").strip()
    if not title or not md:
        return
    url = f"{SITE_BASE}/forum/_pinned_info/{int(channel_id)}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json={"title": title, "md": md},
                auth=_basic_auth(),
            ) as resp:
                await resp.read()
                print(f"[site_api] pinned_info {channel_id} -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[site_api] pinned_info {channel_id} échec : {exc!r}", flush=True)
async def suggest_title(title: str, content: str = "", lang: str = "") -> str | None:
    title = (title or "").strip()
    if not title:
        return None
    url = f"{SITE_BASE}/gstar-gpt/suggest-title"
    payload = {"title": title, "content": content or ""}
    if lang:
        payload["lang"] = lang
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json=payload,
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                t = (data.get("title") or "").strip()
                return t if (data.get("ok") and t) else None
    except Exception as exc:
        print(f"[site_api] suggest-title échec : {exc!r}", flush=True)
        return None
async def suggest_tags(title: str, content: str, tags: list) -> "list | None":
    tags = [str(t) for t in (tags or []) if str(t).strip()]
    if not tags:
        return []
    url = f"{SITE_BASE}/gstar-gpt/suggest-tags"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json={"title": title or "", "content": content or "", "tags": tags},
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("ok"):
                    return None
                return [t for t in (data.get("tags") or []) if t in tags]
    except Exception as exc:
        print(f"[site_api] suggest-tags échec : {exc!r}", flush=True)
        return None
async def check_topic(title: str, content: str = "") -> bool:
    url = f"{SITE_BASE}/gstar-gpt/topic-check"
    payload = {"title": title or "", "content": content or ""}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json=payload,
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    print(f"[site_api] topic-check HTTP {resp.status} -> garde (conservateur)", flush=True)
                    return True
                data = await resp.json()
                nostale = bool(data.get("nostale", True))
                print(f"[site_api] topic-check nostale={nostale} tier={data.get('tier')}", flush=True)
                return nostale
    except Exception as exc:
        print(f"[site_api] topic-check échec : {exc!r} -> garde (conservateur)", flush=True)
        return True
async def notify_thread_deleted(thread_id: int) -> None:
    url = f"{SITE_BASE}/forum/_thread_deleted/{int(thread_id)}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                await resp.read()
                print(f"[site_api] thread_deleted {thread_id} -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[site_api] thread_deleted {thread_id} échec : {exc!r}", flush=True)
async def get_submenu_thread_ids() -> list:
    url = f"{SITE_BASE}/forum/_thread_ids"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    print(f"[site_api] thread_ids HTTP {resp.status}", flush=True)
                    return []
                data = await resp.json()
                ids = data.get("ids") or []
                return [int(x) for x in ids]
    except Exception as exc:
        print(f"[site_api] thread_ids échec : {exc!r}", flush=True)
        return []
async def register_forum_token(token: str) -> None:
    token = (token or "").strip()
    if not token:
        return
    url = f"{SITE_BASE}/forum/_register_token"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json={"token": token},
                auth=_basic_auth(),
            ) as resp:
                await resp.read()
    except Exception as exc:
        print(f"[site_api] register_token échec : {exc!r}", flush=True)
async def set_gstar_avatar(url: str) -> None:
    url = (url or "").strip()
    if not url:
        return
    api = f"{SITE_BASE}/forum/_gstar_avatar"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                api,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json={"url": url},
                auth=_basic_auth(),
            ) as resp:
                await resp.read()
                print(f"[site_api] gstar_avatar -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[site_api] gstar_avatar échec : {exc!r}", flush=True)
async def register_access_token(token: str, budget: int, days: int | None,
                                discord_id: int, discord_name: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    url = f"{SITE_BASE}/forum/_register_access"
    payload = {"token": token, "budget": int(budget),
               "discord_id": str(discord_id), "discord_name": discord_name or ""}
    if days:
        payload["days"] = int(days)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json=payload,
                auth=_basic_auth(),
            ) as resp:
                data = await resp.json()
                return bool(data.get("ok"))
    except Exception as exc:
        print(f"[site_api] register_access échec : {exc!r}", flush=True)
        return False
async def grant_from_share(share: str, budget: int | None, days: int | None,
                           granted_by: str) -> dict | None:
    share = (share or "").strip()
    if not share:
        return {"ok": False, "error": "not_found"}
    url = f"{SITE_BASE}/gstar-gpt/grant-from-share"
    payload = {"share": share, "granted_by": granted_by or ""}
    if budget is not None:
        payload["budget"] = int(budget)
    if days:
        payload["days"] = int(days)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json=payload,
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception as exc:
        print(f"[site_api] grant_from_share échec : {exc!r}", flush=True)
        return None
async def grant_internet_from_share(share: str, days: int | None,
                                    revoke: bool, granted_by: str) -> dict | None:
    share = (share or "").strip()
    if not share:
        return {"ok": False, "error": "not_found"}
    url = f"{SITE_BASE}/gstar-gpt/grant-internet-from-share"
    payload = {"share": share, "granted_by": granted_by or ""}
    if revoke:
        payload["revoke"] = True
    if days:
        payload["days"] = int(days)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json=payload,
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception as exc:
        print(f"[site_api] grant_internet_from_share échec : {exc!r}", flush=True)
        return None
async def mint_internet_share(days: int | None, granted_by: str) -> dict | None:
    url = f"{SITE_BASE}/gstar-gpt/mint-internet-share"
    payload = {"granted_by": granted_by or ""}
    if days:
        payload["days"] = int(days)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json=payload,
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception as exc:
        print(f"[site_api] mint_internet_share échec : {exc!r}", flush=True)
        return None
async def list_access_tokens() -> list | None:
    url = f"{SITE_BASE}/forum/_access_list"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("items") if data.get("ok") else None
    except Exception as exc:
        print(f"[site_api] access_list échec : {exc!r}", flush=True)
        return None
async def revoke_access(discord_id: int) -> int | None:
    url = f"{SITE_BASE}/forum/_revoke_access"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json={"discord_id": str(discord_id)},
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return int(data.get("removed", 0)) if data.get("ok") else None
    except Exception as exc:
        print(f"[site_api] revoke_access échec : {exc!r}", flush=True)
        return None
async def get_models_status() -> dict | None:
    url = f"{SITE_BASE}/gstar-gpt/models-status"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data if data.get("ok") else None
    except Exception as exc:
        print(f"[site_api] models-status échec : {exc!r}", flush=True)
        return None
async def fetch_pending_logs() -> list:
    url = f"{SITE_BASE}/gstar-gpt/logs-pending"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("logs") or []
    except Exception:
        return []
async def fetch_chat_logs() -> list:
    url = f"{SITE_BASE}/gstar-gpt/chat-logs-pending"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("logs") or []
    except Exception:
        return []
async def get_share_data(share_id: str) -> dict | None:
    url = f"{SITE_BASE}/gstar-gpt/share-data/{share_id}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    print(f"[site_api] share-data {share_id} HTTP {resp.status}", flush=True)
                    return None
                return await resp.json()
    except Exception as exc:
        print(f"[site_api] share-data {share_id} échec : {exc!r}", flush=True)
        return None
async def register_partage_thread(cid: str, thread_id: int, user_id: int = 0,
                                  user_name: str = "", user_avatar: str = "") -> None:
    if not cid:
        return
    url = f"{SITE_BASE}/gstar-gpt/partage-register"
    payload = {"cid": cid, "thread_id": int(thread_id), "user_id": int(user_id) if user_id else 0,
               "user_name": user_name or "", "user_avatar": user_avatar or ""}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                                    json=payload, auth=_basic_auth()) as resp:
                await resp.read()
                print(f"[site_api] partage-register cid={cid[:8]} thread={thread_id} -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[site_api] partage-register échec : {exc!r}", flush=True)
async def fetch_partage_pending() -> list:
    url = f"{SITE_BASE}/gstar-gpt/partage-pending"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return []
                return (await resp.json()).get("items") or []
    except Exception:
        return []
async def ack_partage(ids: list) -> None:
    if not ids:
        return
    url = f"{SITE_BASE}/gstar-gpt/partage-pending/ack"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                                    json={"ids": ids}, auth=_basic_auth()) as resp:
                await resp.read()
    except Exception as exc:
        print(f"[site_api] ack_partage échec : {exc!r}", flush=True)
async def get_site_status() -> dict | None:
    url = f"{SITE_BASE}/gstar-gpt/site-status"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data if data.get("ok") else None
    except Exception as exc:
        print(f"[site_api] get_site_status échec : {exc!r}", flush=True)
        return None
async def translate(text: str, target: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    url = f"{SITE_BASE}/gstar-gpt/translate"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(
                url,
                headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                json={"text": text, "target": target},
                auth=_basic_auth(),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("translated") if data.get("ok") else None
    except Exception as exc:
        print(f"[site_api] translate échec : {exc!r}", flush=True)
        return None
async def fetch_pending_annonces() -> list:
    url = f"{SITE_BASE}/gstar-gpt/annonces-pending"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.get(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN}, auth=_basic_auth()) as resp:
                if resp.status != 200:
                    return []
                return (await resp.json()).get("items") or []
    except Exception:
        return []
async def ack_annonces(ids: list) -> None:
    if not ids:
        return
    url = f"{SITE_BASE}/gstar-gpt/annonces-pending/ack"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
            async with session.post(url, headers={"X-Gstar-Bot-Token": BOT_TOKEN, "Content-Type": "application/json"},
                                    json={"ids": ids}, auth=_basic_auth()) as resp:
                await resp.read()
    except Exception as exc:
        print(f"[site_api] ack_annonces échec : {exc!r}", flush=True)