import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from extensions import site_api
from constants import (
    GUILD_ID_GSTAR,
    LANGUAGE_ROLE_IDS,
    DISCUSSION_CHANNEL_ID,
    QUESTION_CHANNEL_ID,
    ESTIMATION_CHANNEL_ID,
    COMMERCES_ID,
    ACTIVITES_ID,
    NOSTALE_NEWS_CHANNEL_ID,
    POURCENTS_A4_CHANNEL_ID,
)
ORANGE = 0xE67E22
TRANSLATE_EMOJI = "🌐"
FLAG_FOOTER = "Use the flags to translate"
TRANSLATE_CHANNEL_IDS = {
    DISCUSSION_CHANNEL_ID, QUESTION_CHANNEL_ID, ESTIMATION_CHANNEL_ID,
    COMMERCES_ID, ACTIVITES_ID,
    NOSTALE_NEWS_CHANNEL_ID,
    POURCENTS_A4_CHANNEL_ID,
}
BOT_REACT_CHANNELS = {NOSTALE_NEWS_CHANNEL_ID, POURCENTS_A4_CHANNEL_ID}
LANGS = [
    ("fr", "🇫🇷", "Français"), ("en", "🇬🇧", "English"), ("de", "🇩🇪", "Deutsch"),
    ("it", "🇮🇹", "Italiano"), ("es", "🇪🇸", "Español"), ("pl", "🇵🇱", "Polski"),
    ("ru", "🇷🇺", "Русский"), ("cs", "🇨🇿", "Čeština"), ("tr", "🇹🇷", "Türkçe"),
]
LANG_LABEL = {code: (flag, name) for code, flag, name in LANGS}
FLAG_LANGS = [t for t in LANGS if t[0] != "en"]
LOCALE_TO_CODE = {
    "fr": "fr", "en-US": "en", "en-GB": "en", "de": "de", "it": "it",
    "es-ES": "es", "es-419": "es", "pl": "pl", "ru": "ru", "cs": "cs", "tr": "tr",
}
async def _translate_free(text: str, target_code: str) -> str | None:
    return await site_api.translate(text, target_code)
def _has_text(s: str) -> bool:
    return bool(s) and len(s.strip()) >= 3 and any(c.isalpha() for c in s)
def _strip_md_links(s: str) -> str:
    import re as _re
    s = _re.sub(r"\[[^\]]*\]\((?:[^)]+)\)", "", s or "")
    s = _re.sub(r"https?://\S+", "", s)
    return s.strip()
def _message_text(message: discord.Message) -> str:
    content = (message.content or "").strip()
    rich = next((e for e in message.embeds
                 if getattr(e, "type", None) == "rich" and (e.description or e.title or e.fields)), None)
    if rich is not None and not _has_text(_strip_md_links(content)):
        parts = []
        if rich.title:
            parts.append(rich.title)
        if rich.description:
            parts.append(rich.description)
        for f in rich.fields:
            seg = "\n".join(x for x in (f.name, f.value) if x)
            if seg:
                parts.append(seg)
        return "\n\n".join(parts).strip()
    return content if _has_text(content) else ""
def _member_code(member: discord.Member, default: str = "fr") -> str:
    if member is not None:
        role_ids = {r.id for r in getattr(member, "roles", [])}
        for code, rid in LANGUAGE_ROLE_IDS.items():
            if rid in role_ids:
                return code
    return default
def _result_embed(translated: str, code: str, message: discord.Message | None = None) -> discord.Embed:
    flag, name = LANG_LABEL.get(code, ("🌐", code.upper()))
    desc = translated[:3800]
    if message is not None:
        desc += f"\n\n[🔗 Go to message]({message.jump_url})"
    embed = discord.Embed(description=desc, color=ORANGE)
    if message is not None:
        embed.set_author(name=f"Translation · {message.author.display_name}",
                         icon_url=message.author.display_avatar.url)
    else:
        embed.set_author(name="Translation")
    embed.set_footer(text=FLAG_FOOTER)
    return embed
class FlagsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"trflag:{code}", row=i // 4)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            raw = ""
            if interaction.message and interaction.message.embeds:
                raw = interaction.message.embeds[0].description or ""
            text = raw.split("\n\n[")[0].strip()
            if not text:
                await interaction.followup.send("Nothing to translate.", ephemeral=True)
                return
            translated = await _translate_free(text, code)
            if not translated:
                await interaction.followup.send("Translation unavailable right now.", ephemeral=True)
                return
            await interaction.followup.send(
                embed=_result_embed(translated, code), view=FlagsView(), ephemeral=True)
        return callback
class MultiFlagsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"mflag:{code}", row=i // 4)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            src = interaction.message.embeds if interaction.message else []
            jobs, texts = [], []
            for ei, e in enumerate(src):
                if not (e.title or e.description or e.fields):
                    continue
                if e.title:
                    jobs.append((ei, "t", None)); texts.append(e.title)
                if e.description:
                    jobs.append((ei, "d", None)); texts.append(e.description)
                for fi, f in enumerate(e.fields):
                    jobs.append((ei, "fn", fi)); texts.append(f.name)
                    jobs.append((ei, "fv", fi)); texts.append(f.value)
            if not texts:
                await interaction.followup.send("Nothing to translate.", ephemeral=True)
                return
            res_list = await asyncio.gather(*[_translate_free(t, code) for t in texts])
            res = {jobs[i]: (res_list[i] or texts[i]) for i in range(len(jobs))}
            out = []
            for ei, e in enumerate(src):
                if not (e.title or e.description or e.fields):
                    continue
                ne = discord.Embed(color=e.color)
                if (ei, "t", None) in res:
                    ne.title = res[(ei, "t", None)][:256]
                if (ei, "d", None) in res:
                    ne.description = res[(ei, "d", None)][:4096]
                for fi, f in enumerate(e.fields):
                    ne.add_field(name=res.get((ei, "fn", fi), f.name)[:256],
                                 value=res.get((ei, "fv", fi), f.value)[:1024], inline=f.inline)
                if e.image:
                    ne.set_image(url=e.image.url)
                out.append(ne)
            await interaction.followup.send(embeds=out[:10], ephemeral=True)
        return callback
class Translate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def cog_load(self):
        self.bot.add_view(FlagsView())
        self.bot.add_view(MultiFlagsView())
    def _should_react(self, message: discord.Message) -> bool:
        if message.guild is None or message.guild.id != GUILD_ID_GSTAR:
            return False
        if self.bot.user is not None and message.author.id == self.bot.user.id:
            return False
        ch = message.channel
        in_allow = ch.id in TRANSLATE_CHANNEL_IDS or getattr(ch, "parent_id", None) in TRANSLATE_CHANNEL_IDS
        if not in_allow:
            return False
        in_bot_react = ch.id in BOT_REACT_CHANNELS
        if not in_bot_react and (message.webhook_id is not None or message.author.bot):
            return False
        return bool(_message_text(message))
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self._should_react(message):
            return
        try:
            await message.add_reaction(TRANSLATE_EMOJI)
        except Exception:
            pass
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not self._should_react(after):
            return
        if any(str(r.emoji) == TRANSLATE_EMOJI for r in after.reactions):
            return
        try:
            await after.add_reaction(TRANSLATE_EMOJI)
        except Exception:
            pass
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != TRANSLATE_EMOJI:
            return
        if payload.guild_id != GUILD_ID_GSTAR:
            return
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return
        member = payload.member
        if member is not None:
            try:
                await message.remove_reaction(TRANSLATE_EMOJI, member)
            except Exception:
                pass
        target = member or self.bot.get_user(payload.user_id)
        text = _message_text(message)
        if target is None or not text:
            return
        code = _member_code(member)
        translated = await _translate_free(text, code)
        if not translated:
            await self._dm(target, channel, content="Translation failed, try again in a moment.")
            return
        if translated.strip().lower() == text.strip().lower():
            await self._dm(target, channel,
                           content=f"This message is already in your language ({LANG_LABEL.get(code, ('', code))[0]}).")
            return
        await self._dm(target, channel, embed=_result_embed(translated, code, message), view=FlagsView())
    async def _dm(self, user, channel, *, content=None, embed=None, view=None):
        try:
            await user.send(content=content, embed=embed, view=view)
        except discord.Forbidden:
            try:
                await channel.send(f"{user.mention} open your DMs to receive the translation.",
                                   delete_after=8,
                                   allowed_mentions=discord.AllowedMentions(users=True))
            except Exception:
                pass
        except Exception as e:
            print(f"[translate] MP échec: {e!r}", flush=True)
    async def translate_message(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True)
        text = _message_text(message)
        if not text:
            await interaction.followup.send("This message has no text to translate.", ephemeral=True)
            return
        loc = getattr(interaction.locale, "value", None) or str(interaction.locale or "")
        code = LOCALE_TO_CODE.get(loc, "fr")
        translated = await _translate_free(text, code)
        if not translated:
            await interaction.followup.send(
                "Translation unavailable right now, try again later.", ephemeral=True)
            return
        await interaction.followup.send(
            embed=_result_embed(translated, code, message), view=FlagsView(), ephemeral=True)
async def setup(bot: commands.Bot):
    cog = Translate(bot)
    await bot.add_cog(cog)
    menu = app_commands.ContextMenu(name="Traduire", callback=cog.translate_message)
    try:
        bot.tree.add_command(menu)
    except app_commands.CommandAlreadyRegistered:
        pass