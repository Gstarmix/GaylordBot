import asyncio
from pathlib import Path
import discord
from discord.ext import commands
from extensions.translate import FLAG_LANGS, _translate_free, FLAG_FOOTER
ORANGE = 0xE67E22
SEPARATOR = "https://www.zupimages.net/up/24/24/stl1.png"
XP_CHANNEL_ID = 715194932620689481
CMD_CHANNEL_ID = 704586556446343179
ASSETS = Path(__file__).resolve().parent / "assets"
BANNER_NAME = "banner_xpcommands.png"
INTRO = ("📊 Level-up time estimator",
         f"Use the commands below in <#{CMD_CHANNEL_ID}> to estimate your level-up time "
         "(combat and hero).\n\nThe gifs show how to read your values in game and enter them.")
COMBAT = ("🔱 Combat XP commands",
    f"Run **/exp combat** to estimate your combat level-up time. Use it in <#{CMD_CHANNEL_ID}>.\n\n"
    "**Examples**\n"
    "**1 · Basic** — lvl 80 (15.65%), then after 1h lvl 81 (7.75%):\n"
    "`/exp combat niveau_debut:80.1565 niveau_fin:81.0775`\n"
    "**2 · Since level 1** — same, but show the % from level 1 (add `tout:True`):\n"
    "`/exp combat niveau_debut:80.1565 niveau_fin:81.0775 tout:True`\n"
    "**3 · Custom duration** — lvl 80 (15.65%), then after **4h** lvl 85 (2.05%):\n"
    "`/exp combat niveau_debut:80.1565 niveau_fin:85.0205 heures:4h`\n"
    "**4 · Project a session** — your progress after **6h45** of grinding:\n"
    "`/exp combat niveau_debut:80.1565 niveau_fin:81.0775 heures_max:6h45`\n\n"
    "**Reading the result**\n```\nLevel        %/h    Up     Total\n"
    "80 (15.65%)  93.44  0h54   0h54\n81           79.70  1h15   2h09\n"
    "82           69.27  1h27   3h36\n83           55.81  1h48   5h24\n"
    "84           46.54  2h09   7h32\n```\n→ 0h54 from 80 to 81 · 7h32 total to reach 85.")
HERO = ("🔱 Hero XP commands",
    f"Run **/exp hero** to estimate your hero level-up time. Use it in <#{CMD_CHANNEL_ID}>.\n\n"
    "**Examples**\n"
    "**1 · Basic** — +65 (85.50%), then after 1h +66 (5.25%):\n"
    "`/exp hero niveau_debut:65.8550 niveau_fin:66.0525`\n"
    "**2 · Since level 1** — same, but show the % from level 1 (add `tout:True`):\n"
    "`/exp hero niveau_debut:65.8550 niveau_fin:66.0525 tout:True`\n"
    "**3 · Custom duration** — +65 (85.50%), then after **3h** +66 (47.15%):\n"
    "`/exp hero niveau_debut:65.8550 niveau_fin:66.4715 heures:3h`\n"
    "**4 · Project a session** — your progress after **8h30** of grinding:\n"
    "`/exp hero niveau_debut:65.8550 niveau_fin:66.4715 heures_max:8h30`\n\n"
    "**Reading the result**\n```\nLevel        %/h    Up     Total\n"
    "+65 (85.5%)  20.54  0h42   0h42\n+66          17.86  5h36   6h18\n```\n"
    "→ 0h42 from +65 to +66.")
GUIDE = [INTRO, COMBAT, HERO]
class XpFlagsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"xpflag:{code}", row=i // 4)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            async def tr(text):
                if not text:
                    return text
                return (await _translate_free(text, code)) or text
            titles = await asyncio.gather(*[tr(t) for t, _d in GUIDE])
            descs = await asyncio.gather(*[tr(d) for _t, d in GUIDE])
            embeds = [discord.Embed(title=tt, description=(dd or "")[:4096], color=ORANGE).set_image(url=SEPARATOR)
                      for tt, dd in zip(titles, descs)]
            await interaction.followup.send(embeds=embeds[:10], ephemeral=True)
        return callback
class XpCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def cog_load(self):
        self.bot.add_view(XpFlagsView())
    @commands.command(name="xp_panel")
    @commands.is_owner()
    async def xp_panel(self, ctx: commands.Context):
        chan = self.bot.get_channel(XP_CHANNEL_ID) or ctx.channel
        await chan.send(embed=discord.Embed(color=ORANGE).set_image(url=f"attachment://{BANNER_NAME}"),
                        file=discord.File(ASSETS / BANNER_NAME, filename=BANNER_NAME))
        ti, di = INTRO
        await chan.send(embed=discord.Embed(title=ti, description=di, color=ORANGE).set_image(url=SEPARATOR))
        tc, dc = COMBAT
        await chan.send(embed=discord.Embed(title=tc, description=dc, color=ORANGE).set_image(url="attachment://combat.gif"),
                        file=discord.File(ASSETS / "combat.gif", filename="combat.gif"))
        th, dh = HERO
        await chan.send(embed=discord.Embed(title=th, description=dh, color=ORANGE).set_image(url="attachment://hero.gif").set_footer(text=FLAG_FOOTER),
                        file=discord.File(ASSETS / "hero.gif", filename="hero.gif"), view=XpFlagsView())
        await ctx.send(f"Guide xp-commands posté dans {chan.mention}.")
async def setup(bot: commands.Bot):
    await bot.add_cog(XpCommands(bot))