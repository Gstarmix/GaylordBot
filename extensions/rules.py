import asyncio
from pathlib import Path
import discord
from discord.ext import commands
from extensions.translate import FLAG_LANGS, _translate_free, FLAG_FOOTER
BANNER_FILE = Path(__file__).resolve().parent / "assets" / "banner_rules.png"
BANNER_NAME = "banner_rules.png"
SEPARATOR = "https://www.zupimages.net/up/24/24/stl1.png"
COLOR = discord.Color(0xE67E22)
SECTIONS = [
    (None,
     "On top of following a few rules, you must comply with Discord's "
     "[**Guidelines**](https://discord.com/guidelines) and "
     "[**ToS**](https://discord.com/terms)."),
    ("I. General Terms of Use",
     "> ➔ **Respectful Behavior**: Be courteous and respectful toward every member, even when you disagree.\n\n"
     "> ➔ **No Inappropriate Content**: Sharing pornographic, violent or otherwise offensive content is strictly prohibited.\n\n"
     "> ➔ **Right Channel**: Please respect each channel's topic and move off-topic discussions to the appropriate channels.\n\n"),
    ("II. Trading and Exchanges",
     "> ➔ **Selling Virtual Property**: Selling virtual items for real money, or trading them for items from other games, is forbidden.\n\n"
     "> ➔ **Unauthorized Purchases**: Buying in-game gold or items with real money through means not approved by GameForge is forbidden.\n\n"
     "> ➔ **Promoting or Using Illegal Content**: Promoting private servers, hacks, cheats or any other illegal activity is strictly forbidden.\n\n"),
    ("III. Discussion Channel Rules",
     "> ➔ **Relevant Topics**: You may ask questions related to the ongoing discussion or a recent announcement (less than 48 hours old).\n\n"
     "> ➔ **Redirecting Questions**: Questions about NosTale that aren't tied to the ongoing discussion or a recent announcement must be asked in "
     "[**Questions**](https://discord.com/channels/684734347177230451/1055993732505284690).\n\n"
     "> ➔ **Anti-trolling**: Trolling, disruptive or off-topic messages will be deleted. Repeat offenders will be sanctioned and barred from posting.\n\n"),
    ("IV. Disciplinary Measures",
     "> ➔ In case of inappropriate behavior, an initial warning will be given.\n\n"
     "> ➔ Depending on the severity of the offense, sanctions may apply, ranging from a temporary mute to a permanent ban from the server.\n\n"
     "> ➔ In threads, the bot automatically adds the :warning: emoji to flag a message; elsewhere you can add it manually. In both cases the emoji lets you explain your report via direct message.\n\n"),
    ("V. Roles",
     "> ➔ <@&684742675726991436>: Server administrator.\n\n"
     "> ➔ <@&730357227784896564>: Members who boosted the server.\n\n"
     "> ➔ <@&1020023040794427432>: Members of the month most rewarded in [**Questions**](https://discord.com/channels/684734347177230451/1055993732505284690).\n\n"
     "> ➔ <@&1020028607491493939>: Members of the month most rewarded in [**Estimates**](https://discord.com/channels/684734347177230451/1028316725457981440).\n\n"
     "> ➔ <@&711308286556635238>: Funniest members of the month in [**Memes**](https://discord.com/channels/684734347177230451/724265897794994186).\n\n"
     "> ➔ <@&1116784777392042116>: Members of the month who caught the rarest Pokémon in [**Pokétwo-pokéslot**](https://discord.com/channels/684734347177230451/1122921340354179129).\n\n"
     "> ➔ <@&1116784776481869944>: Members of the month who married a character in [**Mudae-rolls-1**](https://discord.com/channels/684734347177230451/1122922261180071976).\n\n"
     "> ➔ <@&684745331602096134>: Server members.\n\n"
     "> ➔ <id:customize>: Pick your **raid roles**, your **language** (required) and your **announcements** (YouTube, Instagram, Nostar, Discord, Steam).\n\n"
     "> ➔ Monthly rankings of the most active members are in [**Monthly rankings**](https://discord.com/channels/684734347177230451/1248412336042283129).\n\n"),
    ("VI. Multilingual server",
     "> ➔ **One single community**: whatever your language, everyone stays in the same channels.\n\n"
     "> ➔ **Translate a message**: click the 🌐 reaction under a message to get its translation by direct message, or **right-click** then **Apps ➜ Translate**.\n\n"
     "> ➔ **Change language**: under a translation, click your language's **flag**.\n\n"
     "> ➔ **Announcements**: you receive our YouTube, Instagram, Nostar, Discord and Steam announcements by default; remove the roles you don't want in <id:customize>.\n\n"
     "> ➔ **Language**: choosing your language in <id:customize> is **required** so the server can speak to you in your language.\n\n"
     "> ➔ 🌐 **Another language?** Click a flag below to read the entire rules in your language.\n\n"),
]
class ReglementFlagsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"reglflag:{code}", row=i // 4)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            async def tr(text):
                if not text:
                    return text
                return (await _translate_free(text, code)) or text
            titles = await asyncio.gather(*[tr(title) for title, _desc in SECTIONS])
            descs = await asyncio.gather(*[tr(desc) for _title, desc in SECTIONS])
            embeds = [discord.Embed(title=tt, description=(dd or "")[:4096], color=COLOR).set_image(url=SEPARATOR)
                      for tt, dd in zip(titles, descs)]
            await interaction.followup.send(embeds=embeds[:10], ephemeral=True)
        return callback
def _reglement_messages():
    banner = discord.Embed(color=COLOR).set_image(url=f"attachment://{BANNER_NAME}")
    msgs = [(banner, None, True)]
    for i, (title, desc) in enumerate(SECTIONS):
        e = discord.Embed(title=title, description=desc, color=COLOR).set_image(url=SEPARATOR)
        view = ReglementFlagsView() if i == len(SECTIONS) - 1 else None
        if view is not None:
            e.set_footer(text=FLAG_FOOTER)
        msgs.append((e, view, False))
    return msgs
class RulesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    async def cog_load(self):
        self.bot.add_view(ReglementFlagsView())
    @commands.command(name="reglement")
    @commands.is_owner()
    async def reglement(self, ctx):
        for embed, view, attach in _reglement_messages():
            kwargs = {"embed": embed}
            if view is not None:
                kwargs["view"] = view
            if attach and BANNER_FILE.exists():
                kwargs["file"] = discord.File(BANNER_FILE, filename=BANNER_NAME)
            await ctx.send(**kwargs)
async def setup(bot):
    await bot.add_cog(RulesCog(bot))