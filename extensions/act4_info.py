import json
from pathlib import Path
import discord
from discord.ext import commands
from extensions.translate import FLAG_LANGS, FLAG_FOOTER
ORANGE = 0xE67E22
SEPARATOR = "https://www.zupimages.net/up/24/24/stl1.png"
ASSETS = Path(__file__).resolve().parent / "assets"
I18N = json.loads((ASSETS / "act4_info_i18n.json").read_text(encoding="utf-8"))
A4BOT_CHANNEL_ID = 1131254481212940400
PCT_CHANNEL_ID = 955172663410692166
RAIDROLES_IMG = "a4_raidroles.png"
def _embeds(key: str, code: str) -> list[discord.Embed]:
    data = I18N[key].get(code) or I18N[key]["en"]
    if key == "pct":
        title, desc = data
        return [discord.Embed(title=title, description=desc, color=ORANGE).set_image(url=SEPARATOR)]
    return [discord.Embed(title=t, description=d, color=ORANGE).set_image(url=SEPARATOR) for t, d in data]
class _InfoFlagsView(discord.ui.View):
    def __init__(self, key: str, prefix: str):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"{prefix}:{code}", row=i // 4)
            btn.callback = self._make_cb(key, code)
            self.add_item(btn)
    def _make_cb(self, key: str, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_message(embeds=_embeds(key, code)[:10], ephemeral=True)
        return callback
def A4FlagsView():
    return _InfoFlagsView("a4bot", "a4flag")
def PctFlagsView():
    return _InfoFlagsView("pct", "pctflag")
class Act4Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def cog_load(self):
        self.bot.add_view(A4FlagsView())
        self.bot.add_view(PctFlagsView())
    @commands.command(name="a4_panel")
    @commands.is_owner()
    async def a4_panel(self, ctx: commands.Context):
        chan = self.bot.get_channel(A4BOT_CHANNEL_ID) or ctx.channel
        await chan.send(embed=discord.Embed(color=ORANGE).set_image(url="attachment://banner_a4botinfo.png"),
                        file=discord.File(ASSETS / "banner_a4botinfo.png", filename="banner_a4botinfo.png"))
        (t1, d1), (t2, d2) = I18N["a4bot"]["en"]
        await chan.send(embed=discord.Embed(title=t1, description=d1, color=ORANGE).set_image(url=SEPARATOR))
        await chan.send(embed=discord.Embed(title=t2, description=d2, color=ORANGE).set_image(url=SEPARATOR).set_footer(text=FLAG_FOOTER),
                        view=A4FlagsView())
        await ctx.send(f"a4-bot-info posté dans {chan.mention}.")
    @commands.command(name="pct_panel")
    @commands.is_owner()
    async def pct_panel(self, ctx: commands.Context):
        chan = self.bot.get_channel(PCT_CHANNEL_ID) or ctx.channel
        await chan.send(embed=discord.Embed(color=ORANGE).set_image(url="attachment://banner_pcta4.png"),
                        file=discord.File(ASSETS / "banner_pcta4.png", filename="banner_pcta4.png"))
        title, desc = I18N["pct"]["en"]
        await chan.send(embed=discord.Embed(title=title, description=desc, color=ORANGE).set_image(url=SEPARATOR).set_footer(text=FLAG_FOOTER),
                        view=PctFlagsView())
        await ctx.send(f"pourcents-a4 posté dans {chan.mention}.")
async def setup(bot: commands.Bot):
    await bot.add_cog(Act4Info(bot))