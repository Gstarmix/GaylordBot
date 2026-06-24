import discord
from discord.ext import commands
from constants import ACCUEIL_CHANNEL_ID, LIEN_INVITATION_CHANNEL_ID
from extensions.translate import FlagsView, FLAG_FOOTER
ORANGE = 0xE67E22
class Invite(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @commands.command(name="invite_panel")
    @commands.is_owner()
    async def invite_panel(self, ctx: commands.Context):
        target = self.bot.get_channel(ACCUEIL_CHANNEL_ID) or ctx.channel
        try:
            inv = await target.create_invite(
                max_age=0, max_uses=0, unique=False,
                reason="Lien d'invitation permanent (cog invite)")
        except Exception as e:
            await ctx.send(f"Impossible de créer l'invitation : {e}")
            return
        chan = self.bot.get_channel(LIEN_INVITATION_CHANNEL_ID) or ctx.channel
        embed = discord.Embed(
            title="📬 Invite tes amis sur GSTAR",
            description=(
                "Partage ce lien permanent pour faire venir du monde :\n"
                f"**{inv.url}**\n\n"
                "Plus on est de singes, mieux c'est ! 🐒"
            ),
            color=ORANGE,
        )
        embed.set_footer(text=FLAG_FOOTER)
        await chan.send(embed=embed, view=FlagsView())
        await ctx.send(f"Lien d'invitation posté dans {chan.mention} : <{inv.url}>")
async def setup(bot: commands.Bot):
    await bot.add_cog(Invite(bot))