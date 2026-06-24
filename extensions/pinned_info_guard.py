import discord
from discord.ext import commands
from constants import (
    GUILD_ID_GSTAR,
    GSTAR_USER_ID,
    QUESTION_CHANNEL_ID,
    ESTIMATION_CHANNEL_ID,
    COMMERCES_ID,
    ACTIVITES_ID,
)
INFO_FORUM_IDS = {QUESTION_CHANNEL_ID, ESTIMATION_CHANNEL_ID, COMMERCES_ID, ACTIVITES_ID}
PINNED_FLAG = 1 << 1
_DM = ("⛔ That pinned post is a **read-only guide** — please don't reply in it "
       "(your message was removed). To ask something or post your own ad, create a "
       "**new thread** in the channel instead.")
class PinnedInfoGuard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    def _is_exempt(self, member: discord.Member | None) -> bool:
        if member is None:
            return True
        if self.bot.user is not None and member.id == self.bot.user.id:
            return True
        if member.id == GSTAR_USER_ID:
            return True
        if member.guild is not None and member.id == member.guild.owner_id:
            return True
        perms = getattr(member, "guild_permissions", None)
        if perms is None:
            return False
        return perms.administrator or perms.manage_threads or perms.manage_guild
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.guild.id != GUILD_ID_GSTAR:
            return
        if message.author.bot or message.webhook_id is not None:
            return
        ch = message.channel
        if not isinstance(ch, discord.Thread) or ch.parent_id not in INFO_FORUM_IDS:
            return
        if not (getattr(ch.flags, "pinned", False) or (ch.flags.value & PINNED_FLAG)):
            return
        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if self._is_exempt(member):
            return
        try:
            await message.delete()
        except Exception as exc:
            print(f"[pinned_info_guard] suppression échouée : {exc!r}", flush=True)
        try:
            await message.author.send(_DM)
        except Exception:
            pass
async def setup(bot: commands.Bot):
    await bot.add_cog(PinnedInfoGuard(bot))