from pathlib import Path
import discord
from discord.ext import commands
from constants import (
    GUILD_ID_GSTAR,
    GSTAR_USER_ID,
    HONEYPOT_CHANNEL_ID,
    SECURITY_ALERT_CHANNEL_ID,
)
from extensions.rules import SEPARATOR
from extensions.translate import FLAG_LANGS, FLAG_FOOTER
RED = 0xC0392B
ORANGE = 0xE67E22
BANNER_FILE = Path(__file__).resolve().parent / "assets" / "banner_honeypot.png"
BANNER_NAME = "banner_honeypot.png"
_TITLE_EN = "⛔ Do not post here"
_DESC_EN = ("This channel is an **automated anti-bot trap**. Any message posted here "
            "triggers an **instant, automatic ban**. There is nothing to do here, just move on.")
HONEY_TR = {
    "fr": ("⛔ Ne postez rien ici",
           "Ce salon est un **piège anti-bot automatique**. Tout message posté ici entraîne un "
           "**bannissement automatique et immédiat**. Il n'y a rien à faire ici, passez votre chemin."),
    "de": ("⛔ Hier nichts posten",
           "Dieser Kanal ist eine **automatische Anti-Bot-Falle**. Jede hier gepostete Nachricht führt "
           "zu einem **sofortigen, automatischen Bann**. Hier gibt es nichts zu tun, geh einfach weiter."),
    "it": ("⛔ Non scrivere qui",
           "Questo canale è una **trappola anti-bot automatica**. Qualsiasi messaggio inviato qui comporta "
           "un **ban immediato e automatico**. Non c'è nulla da fare qui, prosegui pure."),
    "es": ("⛔ No publiques aquí",
           "Este canal es una **trampa anti-bots automática**. Cualquier mensaje publicado aquí provoca "
           "un **baneo inmediato y automático**. No hay nada que hacer aquí, sigue adelante."),
    "pl": ("⛔ Nie pisz tutaj",
           "Ten kanał to **automatyczna pułapka na boty**. Każda wysłana tu wiadomość powoduje "
           "**natychmiastowy, automatyczny ban**. Nie ma tu nic do roboty, po prostu idź dalej."),
    "ru": ("⛔ Не пишите здесь",
           "Этот канал это **автоматическая ловушка для ботов**. Любое сообщение здесь приводит к "
           "**мгновенному автоматическому бану**. Здесь нечего делать, просто проходите мимо."),
    "cs": ("⛔ Sem nic nepiš",
           "Tento kanál je **automatická past na boty**. Jakákoli sem zaslaná zpráva vede k "
           "**okamžitému automatickému banu**. Není tu co dělat, jen pokračuj dál."),
    "tr": ("⛔ Buraya yazma",
           "Bu kanal **otomatik bir bot tuzağıdır**. Buraya gönderilen her mesaj **anında otomatik banla** "
           "sonuçlanır. Burada yapacak bir şey yok, yoluna devam et."),
}
def _panel_embed() -> discord.Embed:
    return discord.Embed(title=_TITLE_EN, color=RED, description=_DESC_EN).set_image(url=SEPARATOR).set_footer(text=FLAG_FOOTER)
class HoneyFlagsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"honeyflag:{code}", row=i // 4)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            title, desc = HONEY_TR.get(code, (_TITLE_EN, _DESC_EN))
            embed = discord.Embed(title=title, description=desc, color=RED).set_image(url=SEPARATOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return callback
class UnbanButton(discord.ui.DynamicItem[discord.ui.Button], template=r"honeyunban:(?P<uid>\d+)"):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(discord.ui.Button(
            label="Unban", emoji="♻️", style=discord.ButtonStyle.danger,
            custom_id=f"honeyunban:{user_id}"))
    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["uid"]))
    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        perms = getattr(member, "guild_permissions", None)
        if not (perms and (perms.administrator or perms.ban_members)):
            await interaction.response.send_message(
                "You don't have permission to unban.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        try:
            await guild.unban(discord.Object(id=self.user_id), reason=f"Unban via bouton ({member})")
        except discord.NotFound:
            await interaction.followup.send("This user isn't banned (already unbanned?).", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to unban.", ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(f"Unban failed: {exc!r}", ephemeral=True)
            return
        try:
            msg = interaction.message
            emb = msg.embeds[0] if msg.embeds else None
            if emb is not None:
                emb.add_field(name="✅ Unbanned", value=f"by {member.mention}", inline=False)
            await msg.edit(embed=emb, view=None)
        except Exception:
            pass
        await interaction.followup.send(f"✅ Unbanned <@{self.user_id}>.", ephemeral=True)
BAN_DELETE_SECONDS = 3600
class Honeypot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    async def cog_load(self):
        self.bot.add_view(HoneyFlagsView())
        self.bot.add_dynamic_items(UnbanButton)
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
        return perms.administrator or perms.ban_members or perms.kick_members or perms.manage_guild
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != HONEYPOT_CHANNEL_ID:
            return
        if message.guild is None or message.guild.id != GUILD_ID_GSTAR:
            return
        if message.webhook_id is not None:
            return
        guild = message.guild
        member = message.author if isinstance(message.author, discord.Member) else guild.get_member(message.author.id)
        if self._is_exempt(member):
            return
        reason = "Honeypot : message posté dans le salon piège anti-bot / anti-raid."
        banned = False
        err = None
        try:
            await guild.ban(message.author, reason=reason, delete_message_seconds=BAN_DELETE_SECONDS)
            banned = True
        except discord.Forbidden:
            err = "permissions insuffisantes (hiérarchie de rôles ?)"
        except discord.HTTPException as e:
            err = f"HTTP {getattr(e, 'status', '?')}"
        except Exception as e:
            err = repr(e)
        if not banned:
            try:
                await message.delete()
            except Exception:
                pass
        await self._alert(message, banned, err)
    async def _alert(self, message: discord.Message, banned: bool, err: str | None):
        chan = self.bot.get_channel(SECURITY_ALERT_CHANNEL_ID)
        if chan is None:
            print(f"[honeypot] salon d'alerte introuvable ({SECURITY_ALERT_CHANNEL_ID})", flush=True)
            return
        author = message.author
        title = "🚫 Honeypot : ban" if banned else "⚠️ Honeypot : ban ÉCHOUÉ"
        embed = discord.Embed(
            title=title,
            color=RED if banned else 0xE67E22,
            description=f"{author.mention} (`{author}` · `{author.id}`) a posté dans le salon piège.",
        )
        content = (message.content or "").strip()
        if content:
            embed.add_field(name="Message", value=content[:1000], inline=False)
        if not banned and err:
            embed.add_field(name="Raison de l'échec", value=err, inline=False)
        view = None
        if banned:
            view = discord.ui.View(timeout=None)
            view.add_item(UnbanButton(author.id))
        try:
            await chan.send(embed=embed, view=view)
        except Exception as e:
            print(f"[honeypot] échec d'envoi de l'alerte : {e!r}", flush=True)
    @commands.command(name="honeypot_panel")
    @commands.is_owner()
    async def honeypot_panel(self, ctx: commands.Context):
        chan = self.bot.get_channel(HONEYPOT_CHANNEL_ID) or ctx.channel
        if BANNER_FILE.exists():
            await chan.send(
                embed=discord.Embed(color=ORANGE).set_image(url=f"attachment://{BANNER_NAME}"),
                file=discord.File(BANNER_FILE, filename=BANNER_NAME),
            )
        await chan.send(embed=_panel_embed(), view=HoneyFlagsView())
        await ctx.send(f"Honeypot panel posté dans {chan.mention}.")
async def setup(bot: commands.Bot):
    await bot.add_cog(Honeypot(bot))