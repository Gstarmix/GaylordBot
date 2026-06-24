import asyncio
import datetime
import discord
from discord.ext import commands
from constants import *
class ThreadCreator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_message_times = {}
        self.thread_names = {
            MUDAE_HELP_CHANNEL_ID: "Mudae Help",
            SUGGESTION_GSTAR_CHANNEL_ID: "Suggestion(s)",
            SUGGESTION_FAFA_CHANNEL_ID: "Suggestion(s)",
            VIDEO_CHANNEL_ID: "Video(s)",
            MEMES_CHANNEL_ID: "Meme(s)",
            VDO_VDM_CHANNEL_ID: "Media",
            RECHERCHE_KELKIN_CHANNEL_ID: "Search",
            MUDAE_IDEAS_CHANNEL_ID: "Mudae Idea(s)",
            SIGNAL_BUG_CHANNEL_ID: "Report(s)"
        }
        self.channel_delays = {
            MUDAE_HELP_CHANNEL_ID: 600,
            SUGGESTION_GSTAR_CHANNEL_ID: 600,
            SUGGESTION_FAFA_CHANNEL_ID: 600,
            VIDEO_CHANNEL_ID: 600,
            VDO_VDM_CHANNEL_ID: 600,
            RECHERCHE_KELKIN_CHANNEL_ID: 600,
            MUDAE_IDEAS_CHANNEL_ID: 600,
            SIGNAL_BUG_CHANNEL_ID: 600
        }
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id in self.thread_names.keys() and not message.author.bot:
            now = datetime.datetime.now()
            if message.author.id not in self.user_message_times:
                self.user_message_times[message.author.id] = {}
            if message.channel.id in self.user_message_times[message.author.id] and message.channel.id in self.channel_delays and (now - self.user_message_times[message.author.id][message.channel.id]).total_seconds() < self.channel_delays[message.channel.id]:
                await message.author.send(f"You must wait {self.channel_delays[message.channel.id] // 60} minutes before sending a new message. If needed, edit your last message.")
                try:
                    await message.delete()
                except discord.NotFound:
                    print("Message déjà supprimé.")
            else:
                self.user_message_times[message.author.id][message.channel.id] = now
                try:
                    thread_name = f"{self.thread_names[message.channel.id]} by {message.author.name}"
                    thread = await message.channel.create_thread(message=message, name=thread_name)
                    await asyncio.sleep(5)
                    await thread.send("React here!")
                except Exception as e:
                    print(f"Erreur lors de la création du fil : {e}")
async def setup(bot):
    await bot.add_cog(ThreadCreator(bot))