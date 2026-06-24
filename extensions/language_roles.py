import discord
from discord.ext import commands
from constants import LANGUAGE_ROLE_IDS
ORANGE = 0xE67E22
LANGUAGE_LABELS = {
    "fr": ("Français", "🇫🇷"),
    "en": ("English", "🇬🇧"),
}
class LanguageRolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for key, role_id in LANGUAGE_ROLE_IDS.items():
            label, emoji = LANGUAGE_LABELS.get(key, (key.upper(), None))
            btn = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"langrole:{role_id}",
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
            await interaction.response.send_message("Action impossible ici.", ephemeral=True)
            return
        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                "Ce rôle est introuvable, préviens un admin.", ephemeral=True)
            return
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Opt-out rôle de langue")
                msg = f"Rôle **{label}** retiré."
            else:
                await member.add_roles(role, reason="Opt-in rôle de langue")
                msg = f"Rôle **{label}** ajouté."
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Je n'ai pas la permission de modifier ce rôle.", ephemeral=True)
        except Exception as e:
            print(f"[language_roles] toggle échec {member.id}/{role_id}: {e!r}", flush=True)
            await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)
def _panel_embed() -> discord.Embed:
    return discord.Embed(
        title="🌐 Langue / Language",
        color=ORANGE,
        description=(
            "**FR :** Le serveur est en français par défaut. Clique sur **English** si tu veux "
            "suivre la communauté anglophone (annonces EN, future section EN).\n\n"
            "**EN :** This server is in French by default. Click **English** to follow the "
            "English-speaking community (EN announcements, upcoming EN section)."
        ),
    )
class LanguageRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def cog_load(self):
        self.bot.add_view(LanguageRolesView())
    @commands.command(name="lang_panel")
    @commands.is_owner()
    async def lang_panel(self, ctx: commands.Context):
        await ctx.send(embed=_panel_embed(), view=LanguageRolesView())
async def setup(bot: commands.Bot):
    await bot.add_cog(LanguageRoles(bot))