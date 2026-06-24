import asyncio
import json
import os
import unicodedata
import urllib.parse
from pathlib import Path
import aiohttp
import discord
from discord.ext import commands
from constants import QUESTION_CHANNEL_ID, TEST_QUESTION_CHANNEL_ID
from extensions import forum_tokens, site_api
from extensions.forum_helpers import first_post_is_webhook
from extensions.forum_i18n import t, code_for
WATCHED_PARENT_IDS = {QUESTION_CHANNEL_ID, TEST_QUESTION_CHANNEL_ID}
NOSTAR_FORUM_BASE = os.getenv("NOSTAR_FORUM_BASE", "https://preprod.nostar.fr/forum").rstrip("/")
SITE_BASIC_AUTH = os.getenv("NOSTAR_SITE_BASIC_AUTH", "").strip()
def _basic_auth():
    if ":" in SITE_BASIC_AUTH:
        user, pwd = SITE_BASIC_AUTH.split(":", 1)
        return aiohttp.BasicAuth(user, pwd)
    return None
_STORE_PATH = Path(__file__).resolve().parent.parent / "forum_links.json"
POLL_INTERVAL_SECONDS = 3
POLL_MAX_ATTEMPTS = 10
POLL_REQUEST_TIMEOUT = 15
_SLUG_BANNED_CHAR = ("/", "\\", "?", "%", "*", ":", "|", '"', "'", "<", ">", ".", ",", "+")
def _normalise(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    replacements = {
        "œ": "oe", "æ": "ae", "ʼ": "'", "“": '"', "”": '"', "«": '"', "»": '"',
        "´": "'", "‘": "'", "’": "'", "‐": "-", "–": "-", "—": "-", "−": "-",
        " ": " ", "​": "", "‌": "", "…": "...", "⁄": "/",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return "".join(ch for ch in text if not unicodedata.combining(ch))
def _slug(name: str) -> str:
    name = _normalise(name).strip()
    for char in _SLUG_BANNED_CHAR:
        name = name.replace(char, "")
    name = "-".join(name.split())
    return urllib.parse.quote_plus(name)
def _build_url(thread_id: int, name: str, token: str = "", lang: str = "") -> str:
    base = NOSTAR_FORUM_BASE
    if lang:
        origin, sep, _tail = NOSTAR_FORUM_BASE.rpartition("/forum")
        if sep:
            base = f"{origin}/{lang}/forum"
    url = f"{base}/{thread_id}-{_slug(name)}"
    if token:
        url += f"?t={token}"
    return url
def _link_embed(code: str = "en") -> discord.Embed:
    return discord.Embed(
        title=t("link_title", code),
        description=t("link_desc", code),
        color=discord.Color.from_rgb(230, 126, 34),
    )
def _link_view(url: str, code: str = "en") -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label=t("link_button", code),
        emoji="📌",
        style=discord.ButtonStyle.link,
        url=url,
    ))
    return view
def _author_code(thread: discord.Thread) -> str:
    member = None
    guild = getattr(thread, "guild", None)
    if guild is not None and thread.owner_id:
        member = guild.get_member(thread.owner_id)
    return code_for(member)
class ForumLink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._links: dict[str, int] = self._load_store()
        self._processing: set[int] = set()
    def _load_store(self) -> dict:
        try:
            return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    def _save_store(self) -> None:
        try:
            _STORE_PATH.write_text(json.dumps(self._links, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"[forum_link] échec sauvegarde store : {exc}", flush=True)
    async def _wait_until_mirrored(self, url: str) -> bool:
        timeout = aiohttp.ClientTimeout(total=POLL_REQUEST_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout, auth=_basic_auth()) as session:
                for attempt in range(POLL_MAX_ATTEMPTS):
                    try:
                        async with session.get(f"{url}?_cb={attempt}", allow_redirects=True) as resp:
                            if resp.status == 200:
                                return True
                    except aiohttp.ClientError:
                        pass
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except Exception as exc:
            print(f"[forum_link] sondage échoué : {exc}", flush=True)
        return False
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.parent_id not in WATCHED_PARENT_IDS:
            return
        if thread.id in self._processing or str(thread.id) in self._links:
            return
        if await first_post_is_webhook(thread):
            return
        self._processing.add(thread.id)
        asyncio.create_task(self._post_link_when_ready(thread))
    async def _post_link_when_ready(self, thread: discord.Thread):
        try:
            token = forum_tokens.create(thread.id, thread.owner_id or 0)
            asyncio.create_task(site_api.register_forum_token(token))
            await self._wait_until_mirrored(_build_url(thread.id, thread.name))
            fresh = self.bot.get_channel(thread.id) or thread
            name = fresh.name or thread.name
            code = _author_code(fresh)
            url = _build_url(thread.id, name, token, lang=code)
            try:
                msg = await thread.send(embed=_link_embed(code), view=_link_view(url, code))
            except discord.HTTPException as exc:
                print(f"[forum_link] envoi échoué thread {thread.id} : {exc}", flush=True)
                return
            self._links[str(thread.id)] = msg.id
            self._save_store()
            latest = self.bot.get_channel(thread.id) or fresh
            latest_name = latest.name or name
            if _slug(latest_name) != _slug(name):
                try:
                    await msg.edit(embed=_link_embed(code), view=_link_view(_build_url(thread.id, latest_name, token, lang=code), code))
                    print(f"[forum_link] slug resynchronisé thread {thread.id} (titre={latest_name!r})", flush=True)
                    name = latest_name
                except discord.HTTPException as exc:
                    print(f"[forum_link] resync slug échoué thread {thread.id} : {exc}", flush=True)
            print(f"[forum_link] lien posté thread {thread.id} (titre={name!r})", flush=True)
        finally:
            self._processing.discard(thread.id)
    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        if after.parent_id not in WATCHED_PARENT_IDS:
            return
        if before.name == after.name:
            return
        message_id = self._links.get(str(after.id))
        if not message_id:
            print(f"[forum_link] rename avant post thread {after.id} -> sera posté avec le nouveau titre", flush=True)
            return
        token = forum_tokens.create(after.id, after.owner_id or 0)
        code = _author_code(after)
        url = _build_url(after.id, after.name, token, lang=code)
        try:
            await after.get_partial_message(message_id).edit(embed=_link_embed(code), view=_link_view(url, code))
            print(f"[forum_link] lien ré-édité thread {after.id} (nouveau titre={after.name!r})", flush=True)
        except discord.NotFound:
            self._links.pop(str(after.id), None)
            self._save_store()
        except discord.HTTPException as exc:
            print(f"[forum_link] édition échouée thread {after.id} : {exc}", flush=True)
async def setup(bot: commands.Bot):
    await bot.add_cog(ForumLink(bot))