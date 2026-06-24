import asyncio
import discord
from constants import GSTAR_LOG_CHANNEL_ID, GUILD_ID_GSTAR, QUESTION_CHANNEL_ID, GSTAR_USER_ID
from extensions import site_api
GENERIC_AVATAR = "https://cdn.discordapp.com/embed/avatars/0.png"
SALON_QUESTIONS_URL = f"https://discord.com/channels/{GUILD_ID_GSTAR}/{QUESTION_CHANNEL_ID}"
GSTAR_DM_URL = f"https://discord.com/users/{GSTAR_USER_ID}"
INSTA_URL = "https://www.instagram.com/gaylordaboeka/"
_ACCESS_MARKER = "Écrire à Gstar sur Instagram"
def access_buttons_view(include_salon: bool = True) -> "discord.ui.View":
    view = discord.ui.View(timeout=None)
    if include_salon:
        view.add_item(discord.ui.Button(
            label="Le salon des questions", style=discord.ButtonStyle.link, url=SALON_QUESTIONS_URL))
    view.add_item(discord.ui.Button(
        label="Écrire à Gstar sur Discord", style=discord.ButtonStyle.link, url=GSTAR_DM_URL))
    view.add_item(discord.ui.Button(
        label="Écrire à Gstar sur Instagram", style=discord.ButtonStyle.link, url=INSTA_URL))
    return view
def access_links_markdown() -> str:
    return (
        f"[Le salon des questions]({SALON_QUESTIONS_URL})\n"
        f"[Écrire à Gstar sur Discord]({GSTAR_DM_URL})\n"
        f"[Écrire à Gstar sur Instagram]({INSTA_URL})"
    )
def access_block_to_markdown(text: str) -> str:
    prose, found = split_access_block(text)
    if not found:
        return text
    sep = "\n\n" if prose else ""
    return f"{prose}{sep}{access_links_markdown()}"
def split_access_block(text: str) -> tuple:
    text = text or ""
    if _ACCESS_MARKER not in text:
        return text, False
    cut = len(text)
    for marker in ("[Le salon des questions", "Le salon des questions"):
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)
    prose = text[:cut].rstrip().rstrip(":").rstrip()
    return prose, True
def gstar_avatar_url(bot) -> str:
    try:
        guild = bot.get_guild(GUILD_ID_GSTAR)
        if guild is not None and guild.icon is not None:
            return guild.icon.url
    except Exception:
        pass
    return GENERIC_AVATAR
async def _diag(bot, msg: str) -> None:
    print(f"[auto_tag] {msg}", flush=True)
async def pick_forum_tags(available, title: str = "", content: str = "", bot=None) -> "list | None":
    available = list(available or [])
    if not available:
        await _diag(bot, "aucun tag disponible sur le salon (forum sans tags configurés ?)")
        return []
    names = [t.name for t in available]
    try:
        chosen = await site_api.suggest_tags(title, content, names)
    except Exception as exc:
        await _diag(bot, f"suggestion échouée : {exc!r}")
        return None
    if chosen is None:
        await _diag(bot, "IA indisponible (chaîne de modèles à sec côté site) -> à retenter")
        return None
    await _diag(bot, f"tags dispo={names} -> choisis={chosen}")
    return [t for t in available if t.name in chosen][:5]
async def auto_tag_thread(thread: discord.Thread, title: str = "", content: str = "",
                          forum: "discord.ForumChannel | None" = None, bot=None) -> list:
    try:
        parent = forum or getattr(thread, "parent", None)
        if parent is None or not getattr(parent, "available_tags", None):
            pid = getattr(thread, "parent_id", None)
            guild = getattr(thread, "guild", None)
            await _diag(bot, f"parent sans tags en cache (parent={parent!r}) -> refetch {pid}")
            if pid and guild is not None:
                try:
                    parent = await guild.fetch_channel(pid)
                except discord.HTTPException as exc:
                    await _diag(bot, f"refetch parent {pid} échoué : {exc!r}")
        forum_tags = await pick_forum_tags(getattr(parent, "available_tags", None),
                                           title or thread.name, content, bot=bot)
        if forum_tags is None:
            return None
        if not forum_tags:
            return []
        try:
            await thread.edit(applied_tags=forum_tags)
            names = [t.name for t in forum_tags]
            await _diag(bot, f"thread {thread.id} -> {names} ✅")
            return names
        except discord.HTTPException as exc:
            await _diag(bot, f"application échouée thread {thread.id} : {exc!r} (perm « Gérer les fils » ?)")
    except Exception as exc:
        await _diag(bot, f"ERREUR inattendue thread {getattr(thread, 'id', '?')} : {exc!r}")
    return []
async def post_log(bot, text: str) -> None:
    if not text:
        return
    try:
        channel = bot.get_channel(GSTAR_LOG_CHANNEL_ID) or await bot.fetch_channel(GSTAR_LOG_CHANNEL_ID)
        if channel is not None:
            await channel.send(text[:1900])
    except Exception as exc:
        print(f"[forum_helpers] post_log échec : {exc!r}", flush=True)
async def first_post_is_webhook(thread: discord.Thread) -> bool:
    for _ in range(3):
        try:
            async for msg in thread.history(limit=1, oldest_first=True):
                return msg.webhook_id is not None
        except Exception:
            return False
        await asyncio.sleep(1)
    return False