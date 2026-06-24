import json
import os
import asyncio
import discord
from discord.ext import commands, tasks
from constants import (
    GUILD_ID_GSTAR,
    DISCUSSION_CHANNEL_ID,
    ANNOUNCE_ROLE_IDS,
    ANNOUNCE_ROLE_LABELS,
)
from extensions.translate import FlagsView
ORANGE = 0xE67E22
REMINDER_INTERVAL_HOURS = 24 * 7
STATE_PATH = "announce_roles_state.json"
def _announce_role_ids():
    return list(ANNOUNCE_ROLE_IDS.values())
class AnnounceRolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for key, role_id in ANNOUNCE_ROLE_IDS.items():
            label, emoji = ANNOUNCE_ROLE_LABELS.get(key, (key.capitalize(), None))
            btn = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"annrole:{role_id}",
            )
            btn.callback = self._make_callback(role_id, label)
            self.add_item(btn)
    def _make_callback(self, role_id: int, label: str):
        async def callback(interaction: discord.Interaction):
            await self._toggle(interaction, role_id, label)
        return callback
    async def _toggle(self, interaction: discord.Interaction, role_id: int, label: str):
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("This can't be done here.", ephemeral=True)
            return
        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                "This role can't be found, please ping an admin.", ephemeral=True)
            return
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Opt-out rôle d'annonce")
                msg = f"Done, you won't receive **{label}** announcements anymore. Click again to re-enable."
            else:
                await member.add_roles(role, reason="Opt-in rôle d'annonce")
                msg = f"Done, you'll receive **{label}** announcements again."
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to change this role.", ephemeral=True)
        except Exception as e:
            print(f"[announce_roles] toggle échec {member.id}/{role_id}: {e!r}", flush=True)
            await interaction.response.send_message("An error occurred.", ephemeral=True)
def _panel_embed() -> discord.Embed:
    lines = []
    for key in ANNOUNCE_ROLE_IDS:
        label, emoji = ANNOUNCE_ROLE_LABELS.get(key, (key, ""))
        lines.append(f"{emoji} **{label}**")
    return discord.Embed(
        title="🔔 Announcement roles",
        color=ORANGE,
        description=(
            "By default, you get **all** our announcements. If a type doesn't interest you, "
            "click its button to **opt out** (click again to opt back in). "
            "You stay in control of what you're notified about:\n\n" + "\n".join(lines)
        ),
    )
class AnnounceRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()
        self._skip_first_reminder = True
    def _load_state(self) -> dict:
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    def _save_state(self):
        try:
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f)
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            print(f"[announce_roles] save_state échec: {e!r}", flush=True)
    async def cog_load(self):
        self.bot.add_view(AnnounceRolesView())
        if not self.reminder_loop.is_running():
            self.reminder_loop.start()
    def cog_unload(self):
        self.reminder_loop.cancel()
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild is None or member.guild.id != GUILD_ID_GSTAR or member.bot:
            return
        roles = [member.guild.get_role(r) for r in _announce_role_ids()]
        roles = [r for r in roles if r is not None]
        if not roles:
            return
        try:
            await member.add_roles(*roles, reason="Attribution par défaut des rôles d'annonces")
        except Exception as e:
            print(f"[announce_roles] join add_roles échec {member.id}: {e!r}", flush=True)
    @commands.command(name="roles_panel")
    @commands.is_owner()
    async def roles_panel(self, ctx: commands.Context):
        await ctx.send(embed=_panel_embed(), view=AnnounceRolesView())
    @commands.command(name="backfill_annonces")
    @commands.is_owner()
    async def backfill_annonces(self, ctx: commands.Context):
        guild = ctx.guild
        roles = [guild.get_role(r) for r in _announce_role_ids()]
        roles = [r for r in roles if r is not None]
        if not roles:
            await ctx.send("No announcement role found.")
            return
        await ctx.send("Announcement roles backfill started...")
        changed = 0
        seen = 0
        try:
            async for member in guild.fetch_members(limit=None):
                if member.bot:
                    continue
                missing = [r for r in roles if r not in member.roles]
                if missing:
                    try:
                        await member.add_roles(*missing, reason="Backfill rôles d'annonces")
                        changed += 1
                    except Exception as e:
                        print(f"[announce_roles] backfill échec {member.id}: {e!r}", flush=True)
                seen += 1
                if seen % 20 == 0:
                    await asyncio.sleep(2)
        except Exception as e:
            await ctx.send(f"Backfill interrupted ({e!r}). {changed} members updated before stopping.")
            return
        await ctx.send(f"Backfill done: {changed} member(s) updated out of {seen} scanned.")
    async def _post_reminder(self):
        chan = self.bot.get_channel(DISCUSSION_CHANNEL_ID)
        if chan is None:
            return
        old_id = self.state.get("last_reminder_msg_id")
        if old_id:
            try:
                old = await chan.fetch_message(int(old_id))
                await old.delete()
            except Exception:
                pass
        labels = ", ".join(f"**{ANNOUNCE_ROLE_LABELS.get(k, (k.capitalize(),))[0]}**"
                           for k in ANNOUNCE_ROLE_IDS)
        embed = discord.Embed(
            title="🔔 Manage your announcement notifications",
            color=ORANGE,
            description=(
                f"By default you get our {labels} announcements. You can opt out of the ones "
                "you don't care about (and opt back in anytime) from the announcement roles panel."
            ),
        )
        try:
            msg = await chan.send(embed=embed, view=FlagsView())
            self.state["last_reminder_msg_id"] = msg.id
            self._save_state()
        except Exception as e:
            print(f"[announce_roles] reminder échec: {e!r}", flush=True)
    @commands.command(name="roles_reminder")
    @commands.is_owner()
    async def roles_reminder(self, ctx: commands.Context):
        await self._post_reminder()
    @tasks.loop(hours=REMINDER_INTERVAL_HOURS)
    async def reminder_loop(self):
        if self._skip_first_reminder:
            self._skip_first_reminder = False
            return
        await self._post_reminder()
    @reminder_loop.before_loop
    async def _before_reminder(self):
        await self.bot.wait_until_ready()
async def setup(bot: commands.Bot):
    await bot.add_cog(AnnounceRoles(bot))