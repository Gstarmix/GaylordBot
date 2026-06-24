import os
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
from traceback import TracebackException
from constants import GUILD_ID_GSTAR
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
PREFIX = "!"
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)
ACTIVE_EXTENSIONS = [
    "extensions.thread_creator",
    "extensions.question",
    "extensions.image_forwarder",
    "extensions.question_gate",
    "extensions.forum_link",
    "extensions.gstar_answer",
    "extensions.forum_from_share",
    "extensions.gstar_access",
    "extensions.honeypot",
    "extensions.pinned_info_guard",
    "extensions.xp_commands",
    "extensions.act4_info",
    "extensions.steam_news",
    "extensions.maintenance_news",
    "extensions.announce_roles",
    "extensions.site_link",
    "extensions.memes_rss",
    "extensions.language_roles",
    "extensions.translate",
    "extensions.announce",
    "extensions.rules",
    "extensions.invite",
    "extensions.gate",
]
_GSTAR_GUILD = discord.Object(id=GUILD_ID_GSTAR)
_tree_synced = False
async def _sync_tree() -> int:
    try:
        bot.tree.copy_global_to(guild=_GSTAR_GUILD)
        synced = await bot.tree.sync(guild=_GSTAR_GUILD)
        return len(synced)
    except Exception as e:
        print(f"Erreur de sync des slash commands : {e}", flush=True)
        return -1
@bot.event
async def on_ready():
    global _tree_synced
    print(f'{bot.user.name} has connected to Discord!')
    for ext in ACTIVE_EXTENSIONS:
        if ext in bot.extensions:
            continue
        try:
            await bot.load_extension(ext)
            print(f"{ext} loaded")
        except Exception as e:
            print(f"Erreur de chargement de {ext} : {e}")
    if not _tree_synced:
        _tree_synced = True
        n = await _sync_tree()
        if n >= 0:
            print(f"Slash commands synchronisées sur GSTAR : {n}", flush=True)
@bot.command(name="sync")
@commands.has_permissions(manage_guild=True)
async def sync_cmd(ctx: commands.Context):
    n = await _sync_tree()
    await ctx.reply(f"Slash commands re-synchronisées : {n}" if n >= 0 else "Échec de la synchro (voir logs).")
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "Tu n'as pas la permission pour cette commande."
    elif isinstance(error, app_commands.CheckFailure):
        msg = "Tu ne peux pas utiliser cette commande ici."
    else:
        msg = "Une erreur est survenue avec cette commande."
        print(f"[slash] erreur sur {getattr(interaction.command, 'name', '?')} : {error!r}", flush=True)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.NotOwner):
        return
    print(f"channel: {ctx.channel.id}, msg: {ctx.message.clean_content}")
    print(f'Exception ignorée dans {ctx.command} :')
    for line in TracebackException(type(error), error, error.__traceback__).format(chain=True):
        print(f"{line}", end="")
import sys as _sys
if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".dev_instance")) \
        and os.getenv("GAYLORD_BOT_RUN") != "1":
    print("⛔ Instance DEV non démarrée : lancer ce bot (même token que la prod) "
          "déconnecterait son bot LIVE et le miroir logolas (messages plus écrits en DB).\n"
          "   Pour tester quand même : GAYLORD_BOT_RUN=1 python3 -u main.py", flush=True)
    _sys.exit(0)
bot.run(TOKEN)