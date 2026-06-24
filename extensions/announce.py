import discord
from discord import app_commands
from discord.ext import commands, tasks
from constants import (GSTAR_USER_ID, ANNOUNCE_ROLE_IDS, ANNOUNCE_CHANNEL_IDS,
                       TEST_GAYLORD_CHANNEL_ID)
from extensions import site_api
from extensions.translate import FlagsView, FLAG_FOOTER
ORANGE = 0xE67E22
POLL_SECONDS = 30
ANNOUNCE_TYPES = {
    "youtube": ("YouTube", "📺", 0xFF0000),
    "instagram": ("Instagram", "📸", 0xE1306C),
    "nostar": ("Nostar", "🌐", 0xE67E22),
    "discord": ("Discord", "💬", 0x5865F2),
}
class AnnonceModal(discord.ui.Modal):
    def __init__(self, cog: "Announce", key: str, test: bool):
        label = ANNOUNCE_TYPES.get(key, (key,))[0]
        super().__init__(title=f"Annonce {label}" + (" (test)" if test else ""))
        self.cog, self.key, self.test = cog, key, test
        self.message = discord.ui.TextInput(
            label="Message", style=discord.TextStyle.paragraph,
            placeholder="Le texte de l'annonce (plusieurs lignes OK)", max_length=4000, required=True)
        self.lien = discord.ui.TextInput(
            label="Lien (optionnel)", style=discord.TextStyle.short,
            placeholder="https://...", required=False)
        self.add_item(self.message)
        self.add_item(self.lien)
    async def on_submit(self, interaction: discord.Interaction):
        ok = await self.cog._post_announce(
            self.key, str(self.message.value), str(self.lien.value) or None, test=self.test)
        if not ok:
            await interaction.response.send_message(
                "Salon/rôle d'annonce introuvable, préviens un admin.", ephemeral=True)
            return
        cid = self.cog._channel_id_for(self.key, self.test)
        await interaction.response.send_message(
            f"Annonce publiée dans <#{cid}>" + (" (test)." if self.test else " (rôle pingé)."),
            ephemeral=True)
class Announce(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def cog_load(self):
        if not self.poll_loop.is_running():
            self.poll_loop.start()
    def cog_unload(self):
        self.poll_loop.cancel()
    def _channel_id_for(self, key: str, test: bool) -> int | None:
        return TEST_GAYLORD_CHANNEL_ID if test else ANNOUNCE_CHANNEL_IDS.get(key)
    async def _post_announce(self, key: str, message: str, lien: str | None,
                             test: bool = False) -> bool:
        if key not in ANNOUNCE_TYPES or key not in ANNOUNCE_ROLE_IDS:
            return False
        label, emoji, color = ANNOUNCE_TYPES[key]
        role_id = ANNOUNCE_ROLE_IDS[key]
        channel = self.bot.get_channel(self._channel_id_for(key, test))
        if channel is None:
            return False
        desc = (message or "").strip()
        if lien:
            desc += f"\n\n{lien.strip()}"
        embed = discord.Embed(title=f"{emoji} {label}", description=desc, color=color)
        embed.set_footer(text=FLAG_FOOTER)
        await channel.send(
            content=f"<@&{role_id}>",
            embed=embed,
            view=FlagsView(),
            allowed_mentions=discord.AllowedMentions(roles=[discord.Object(id=role_id)]),
        )
        return True
    @app_commands.command(name="annonce",
                          description="Publier une annonce et pinger le rôle correspondant")
    @app_commands.describe(type="Type d'annonce (ping le rôle + salon dédié)",
                           test="Publier dans 🧪・test-gaylord au lieu du vrai salon")
    @app_commands.choices(type=[
        app_commands.Choice(name=label, value=key)
        for key, (label, _emoji, _color) in ANNOUNCE_TYPES.items()
    ])
    async def annonce(self, interaction: discord.Interaction,
                      type: app_commands.Choice[str], test: bool = False):
        if interaction.user.id != GSTAR_USER_ID:
            await interaction.response.send_message("Commande réservée à l'owner.", ephemeral=True)
            return
        await interaction.response.send_modal(AnnonceModal(self, type.value, test))
    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_loop(self):
        items = await site_api.fetch_pending_annonces()
        done = []
        for it in items:
            try:
                if await self._post_announce(it.get("type"), it.get("message"),
                                             it.get("lien"), test=bool(it.get("test"))):
                    done.append(it.get("id"))
                else:
                    done.append(it.get("id"))
            except Exception as e:
                print(f"[announce] post web échec: {e!r}", flush=True)
        if done:
            await site_api.ack_annonces(done)
    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
async def setup(bot: commands.Bot):
    await bot.add_cog(Announce(bot))