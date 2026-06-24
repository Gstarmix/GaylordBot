import asyncio
from pathlib import Path
import discord
from discord.ext import commands
from constants import VERIFIE_ROLE_ID, BIENVENUE_CHANNEL_ID, LANGUAGE_ROLE_IDS
from extensions.translate import FLAG_LANGS, LANGS, _translate_free, FLAG_FOOTER
from extensions.rules import SECTIONS, COLOR, SEPARATOR
ORANGE = 0xE67E22
BANNER_FILE = Path(__file__).resolve().parent / "assets" / "banner_welcome.png"
BANNER_NAME = "banner_welcome.png"
_LANG_NAME = {code: (flag, name) for code, flag, name in LANGS}
def _lang_embed() -> discord.Embed:
    return discord.Embed(
        title="🌍 Choose your language",
        color=COLOR,
        description=(
            "**One last step to unlock the server.** 🔑\n\n"
            "Pick the language you want us to speak to you in: our content is shown to you "
            "in that language, and messages can be translated to it.\n\n"
            "⚠️ **You must choose a language to get access**: without it, you won't see the "
            "rest of the channels.\n\n"
            "👇 **Tap your flag below:**"
        ),
    ).set_image(url=SEPARATOR)
class LanguageSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, name) in enumerate(LANGS):
            btn = discord.ui.Button(emoji=flag, label=name, style=discord.ButtonStyle.secondary,
                                    custom_id=f"gatelang:{code}", row=i // 3)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            member = interaction.user
            guild = interaction.guild
            if guild is None or not isinstance(member, discord.Member):
                await interaction.followup.send("This can't be done here.", ephemeral=True)
                return
            lang_role = guild.get_role(LANGUAGE_ROLE_IDS.get(code, 0))
            verifie = guild.get_role(VERIFIE_ROLE_ID)
            if lang_role is None or verifie is None:
                await interaction.followup.send(
                    "A role is missing, please ping an admin.", ephemeral=True)
                return
            try:
                others = [guild.get_role(rid) for c, rid in LANGUAGE_ROLE_IDS.items() if c != code]
                others = [r for r in others if r is not None and r in member.roles]
                if others:
                    await member.remove_roles(*others, reason="Changement de langue (portail)")
                await member.add_roles(lang_role, verifie, reason="Langue choisie + accès (portail)")
            except discord.Forbidden:
                await interaction.followup.send(
                    "I couldn't set your roles, please ping an admin.", ephemeral=True)
                return
            flag, name = _LANG_NAME.get(code, ("🏳️", code.upper()))
            embed = discord.Embed(
                title="✅ Welcome aboard!",
                color=COLOR,
                description=(
                    f"You're now **verified** and your language is set to **{flag} {name}**.\n\n"
                    "You now have access to the whole server. Enjoy!\n\n"
                    "You can change your language anytime in <id:customize>."
                ),
            ).set_image(url=SEPARATOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
        return callback
class GateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"gateflag:{code}", row=i // 3)
            btn.callback = self._make_flag_cb(code)
            self.add_item(btn)
        accept = discord.ui.Button(label="I accept", emoji="✅",
                                   style=discord.ButtonStyle.success, custom_id="gate:accept", row=3)
        accept.callback = self._accept
        self.add_item(accept)
    def _make_flag_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            async def tr(text):
                if not text:
                    return text
                return (await _translate_free(text, code)) or text
            titles = await asyncio.gather(*[tr(t) for t, _d in SECTIONS])
            descs = await asyncio.gather(*[tr(d) for _t, d in SECTIONS])
            embeds = [discord.Embed(title=tt, description=(dd or "")[:4096], color=COLOR).set_image(url=SEPARATOR)
                      for tt, dd in zip(titles, descs)]
            await interaction.followup.send(embeds=embeds[:10], ephemeral=True)
        return callback
    async def _accept(self, interaction: discord.Interaction):
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("This can't be done here.", ephemeral=True)
            return
        verifie = guild.get_role(VERIFIE_ROLE_ID)
        if verifie is not None and verifie in member.roles:
            await interaction.response.send_message(
                "You already have access ✅. Change your language anytime in <id:customize>.",
                ephemeral=True)
            return
        lang_role_ids = set(LANGUAGE_ROLE_IDS.values())
        member_lang = next((r for r in member.roles if r.id in lang_role_ids), None)
        if member_lang is not None:
            await interaction.response.defer(ephemeral=True)
            try:
                await member.add_roles(verifie, reason="Accès (langue déjà définie)")
            except discord.Forbidden:
                await interaction.followup.send(
                    "I couldn't give you access, please ping an admin.", ephemeral=True)
                return
            await interaction.followup.send(
                f"✅ Welcome aboard! You're now **verified** (language: **{member_lang.name}**). "
                "You have access to the whole server. Change your language anytime in <id:customize>.",
                ephemeral=True)
            return
        await interaction.response.send_message(embed=_lang_embed(), view=LanguageSelectView(), ephemeral=True)
def _panel_embed() -> discord.Embed:
    return discord.Embed(
        title="👋 Welcome to GSTAR",
        color=ORANGE,
        description=(
            "This server is **originally French** 🇫🇷 and now **international** 🌍.\n\n"
            "**To unlock the server, 3 quick steps:**\n\n"
            "➊  Read the rules: tap a **flag** below to read them in your language.\n\n"
            "➋  Click **✅ I accept**.\n\n"
            "➌  **Choose your language** in the popup, then you unlock the server.\n\n"
            "Without choosing a language, you won't have access to the channels. It takes 10 seconds."
        ),
    ).set_image(url=SEPARATOR).set_footer(text=FLAG_FOOTER)
class Gate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def cog_load(self):
        self.bot.add_view(GateView())
        self.bot.add_view(LanguageSelectView())
    @commands.command(name="gate_panel")
    @commands.is_owner()
    async def gate_panel(self, ctx: commands.Context):
        chan = self.bot.get_channel(BIENVENUE_CHANNEL_ID) or ctx.channel
        if BANNER_FILE.exists():
            await chan.send(
                embed=discord.Embed(color=ORANGE).set_image(url=f"attachment://{BANNER_NAME}"),
                file=discord.File(BANNER_FILE, filename=BANNER_NAME),
            )
        await chan.send(embed=_panel_embed(), view=GateView())
        await ctx.send(f"Portail posté dans {chan.mention}.")
async def setup(bot: commands.Bot):
    await bot.add_cog(Gate(bot))