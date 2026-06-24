import os
import re
import discord
from discord import app_commands
from discord.ext import commands
from constants import FORUM_FROM_SHARE_CHANNEL_ID
from extensions.gemini_helper import suggest_title
from extensions import site_api
from extensions.forum_helpers import (
    auto_tag_thread, gstar_avatar_url, GENERIC_AVATAR,
    access_buttons_view, split_access_block, access_block_to_markdown,
)
GSTAR_NAME = "Gstar GPT"
WEBHOOK_NAME = "Gstar Partage"
NOSTAR_FORUM_BASE = os.getenv("NOSTAR_FORUM_BASE", "https://preprod.nostar.fr/forum").rstrip("/")
_MSG_LIMIT = 1900
_THREAD_NAME_LIMIT = 100
_SHARE_ID_RE = re.compile(r"(?:/gstar-gpt/share/|[?&]gpt-share=)([A-Za-z0-9_\-]{6,40})")
_PUBLIC_LINK_BASE = os.getenv("NOSTAR_PUBLIC_BASE", "https://www.nostar.fr").rstrip("/")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
def _absolutize(text: str) -> str:
    def repl(m: "re.Match") -> str:
        label, url = m.group(1), m.group(2).strip()
        if url.startswith("/") and not url.startswith("//"):
            return f"[{label}]({_PUBLIC_LINK_BASE}{url})"
        return m.group(0)
    return _MD_LINK_RE.sub(repl, text or "")
def _extract_share_id(link: str):
    m = _SHARE_ID_RE.search(link or "")
    return m.group(1) if m else None
def _split(text: str, limit: int = _MSG_LIMIT) -> list[str]:
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            if cur:
                out.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line) if cur else line
    if cur:
        out.append(cur)
    return out
class ForumFromShare(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def _post_link_embed(self, webhook: discord.Webhook, thread_id: int, avatar: str) -> None:
        try:
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(
                label="Voir le sujet sur Nostar", emoji="📌",
                style=discord.ButtonStyle.link, url=f"{NOSTAR_FORUM_BASE}/{thread_id}",
            ))
            await webhook.send(
                embed=discord.Embed(
                    title="📌 Cette conversation sur Nostar",
                    description=(
                        "Cet échange (et plein d'autres guides Nostar) est à retrouver sur le site.\n"
                        "Clique sur le bouton ci-dessous pour l'ouvrir."
                    ),
                    color=discord.Color.from_rgb(230, 126, 34),
                ),
                view=view, thread=discord.Object(id=thread_id),
                username=GSTAR_NAME, avatar_url=avatar, wait=True,
            )
        except discord.HTTPException as exc:
            print(f"[forum_from_share] embed lien échoué thread {thread_id} : {exc!r}", flush=True)
    async def _get_webhook(self, channel: discord.ForumChannel) -> discord.Webhook:
        for h in await channel.webhooks():
            if h.name == WEBHOOK_NAME and h.token:
                return h
        return await channel.create_webhook(name=WEBHOOK_NAME)
    @commands.hybrid_command(
        name="forumpartage", aliases=["fpartage", "fp"],
        description="Crée un sujet forum à partir d'un lien de partage Gstar GPT.",
    )
    @app_commands.describe(
        lien="Lien de partage Gstar GPT (…/gstar-gpt/share/<id>)",
        utilisateur="Joueur à attribuer aux messages (obligatoire, pour le compteur de posts)",
    )
    @commands.has_permissions(manage_threads=True)
    async def forumpartage(self, ctx: commands.Context, lien: str = None, utilisateur: discord.User = None):
        if not lien:
            await ctx.reply("Usage : `forumpartage <lien de partage> <@utilisateur>`")
            return
        if utilisateur is None:
            await ctx.reply(
                "Tu dois indiquer l'**utilisateur** à qui attribuer les messages : "
                "`forumpartage <lien> <@utilisateur>` (obligatoire pour que son compteur de posts s'additionne)."
            )
            return
        share_id = _extract_share_id(lien)
        if not share_id:
            await ctx.reply("Lien de partage invalide (attendu `…/gstar-gpt/share/<id>`).")
            return
        await ctx.defer()
        data = await site_api.get_share_data(share_id)
        if not data or not data.get("ok") or not data.get("turns"):
            await ctx.reply("Conversation introuvable ou expirée pour ce lien.")
            return
        turns = [t for t in data["turns"] if (t.get("text") or "").strip()]
        if not turns:
            await ctx.reply("Cette conversation est vide.")
            return
        for t in turns:
            t["text"] = _absolutize(t.get("text"))
        first_q = next((t["text"] for t in turns if t.get("role") == "user"), "")
        title = await suggest_title(data.get("title") or first_q, first_q)
        if not title:
            title = (data.get("title") or first_q or "Conversation Gstar GPT")
        title = title.strip()[:_THREAD_NAME_LIMIT] or "Conversation Gstar GPT"
        forum = self.bot.get_channel(FORUM_FROM_SHARE_CHANNEL_ID)
        if not isinstance(forum, discord.ForumChannel):
            await ctx.reply("Salon forum cible introuvable ou mal configuré (`FORUM_FROM_SHARE_CHANNEL_ID`).")
            return
        try:
            webhook = await self._get_webhook(forum)
        except discord.Forbidden:
            await ctx.reply("Il me manque la permission « Gérer les webhooks » sur le salon cible.")
            return
        except discord.HTTPException as exc:
            await ctx.reply(f"Impossible de créer le webhook ({exc}).")
            return
        if utilisateur:
            user_name = utilisateur.display_name
            user_avatar = utilisateur.display_avatar.url
        else:
            user_name = "Joueur"
            user_avatar = GENERIC_AVATAR
        gstar_avatar = gstar_avatar_url(self.bot)
        thread_id = None
        posted_embed = False
        try:
            for t in turns:
                is_user = t.get("role") == "user"
                name, avatar = (user_name, user_avatar) if is_user else (GSTAR_NAME, gstar_avatar)
                raw = t.get("text") or ""
                text, is_access = (raw, False) if is_user else split_access_block(raw)
                for chunk in _split(text):
                    if thread_id is None:
                        msg = await webhook.send(
                            thread_name=title, content=chunk,
                            username=name, avatar_url=avatar, wait=True,
                        )
                        thread_id = msg.channel.id
                        continue
                    if not posted_embed and not is_user:
                        await self._post_link_embed(webhook, thread_id, gstar_avatar)
                        posted_embed = True
                    await webhook.send(
                        content=chunk, username=name, avatar_url=avatar,
                        thread=discord.Object(id=thread_id), wait=True,
                    )
                if is_access and thread_id is not None:
                    try:
                        await webhook.send(
                            view=access_buttons_view(), username=GSTAR_NAME, avatar_url=gstar_avatar,
                            thread=discord.Object(id=thread_id), wait=True,
                        )
                    except discord.HTTPException as exc:
                        print(f"[forum_from_share] boutons d'accès non postés thread {thread_id} : {exc!r}", flush=True)
        except discord.HTTPException as exc:
            await ctx.reply(f"Erreur en publiant le sujet ({exc}).")
            return
        if thread_id is None:
            await ctx.reply("Rien à publier.")
            return
        if not posted_embed:
            await self._post_link_embed(webhook, thread_id, gstar_avatar)
        try:
            await site_api.set_thread_title(thread_id, title)
            for t in turns:
                text = (t.get("text") or "").strip()
                if not text:
                    continue
                if t.get("role") == "user":
                    await site_api.push_forum_turn(
                        thread_id, "user", text, avatar=user_avatar, name=user_name,
                        user_id=(utilisateur.id if utilisateur else 0),
                    )
                else:
                    await site_api.push_forum_turn(
                        thread_id, "gstar", access_block_to_markdown(text), avatar=gstar_avatar,
                    )
        except Exception as exc:
            print(f"[forum_from_share] push site échoué thread {thread_id} : {exc!r}", flush=True)
        thread = self.bot.get_channel(thread_id)
        try:
            if thread is None:
                thread = await self.bot.fetch_channel(thread_id)
        except discord.HTTPException:
            thread = None
        if thread is not None:
            await auto_tag_thread(thread, title, first_q, forum=forum, bot=self.bot)
        cid = (data.get("cid") or "").strip()
        if cid:
            await site_api.register_partage_thread(
                cid, thread_id,
                user_id=(utilisateur.id if utilisateur else 0),
                user_name=user_name, user_avatar=user_avatar,
            )
        link = thread.jump_url if thread is not None else f"(thread {thread_id})"
        await ctx.reply(f"Sujet créé : {link}")
async def setup(bot: commands.Bot):
    await bot.add_cog(ForumFromShare(bot))