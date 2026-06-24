import os
import discord
from dotenv import load_dotenv
import aiohttp
import datetime
import re
load_dotenv("/root/workspace/gaylord/.env")
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = 875766409475547156
OUTPUT_DIR = "/root/workspace/nostar/preprod/_inbox/acte6_discord/"
MEDIAS_DIR = os.path.join(OUTPUT_DIR, "medias")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "acte6_dump.md")
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
class MyClient(discord.Client):
    async def on_ready(self):
        print(f"{self.user.name} est connecté à Discord !")
        await self.dump_channel_history()
        await self.close()
    def clean_filename(self, filename):
        cleaned_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
        cleaned_name = re.sub(r'_{2,}', '_', cleaned_name).strip('_')
        return cleaned_name
    async def dump_channel_history(self):
        os.makedirs(MEDIAS_DIR, exist_ok=True)
        try:
            channel = await self.fetch_channel(CHANNEL_ID)
        except discord.errors.Forbidden:
            print(f"Erreur de permission : Le bot n'a pas les droits nécessaires pour accéder au salon {CHANNEL_ID}.")
            return
        except discord.errors.NotFound:
            print(f"Erreur : Salon avec l'ID {CHANNEL_ID} introuvable.")
            return
        except Exception as e:
            print(f"Une erreur inattendue est survenue lors de la récupération du salon : {e}")
            return
        if not isinstance(channel, discord.TextChannel):
            print(f"Erreur : Le salon {channel.name} n'est pas un salon textuel.")
            return
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.read_message_history:
            print(f"Erreur : Le bot n'a pas la permission de lire l'historique des messages dans {channel.name}.")
            return
        print(f"Début de l'extraction des messages du salon #{channel.name}...")
        dump_content = []
        total_messages = 0
        total_medias = 0
        async with aiohttp.ClientSession() as session:
            try:
                messages = []
                async for message in channel.history(limit=None, oldest_first=True):
                    messages.append(message)
                total_messages = len(messages)
                for message in messages:
                    author = message.author.display_name
                    timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    content = message.clean_content
                    attachments_info = []
                    embeds_info = []
                    for attachment in message.attachments:
                        cleaned_filename = self.clean_filename(f"{message.id}_{attachment.filename}")
                        filepath = os.path.join(MEDIAS_DIR, cleaned_filename)
                        try:
                            await attachment.save(filepath)
                            total_medias += 1
                            is_image = bool(attachment.content_type and attachment.content_type.startswith("image"))
                            if is_image:
                                attachments_info.append(f"![{attachment.filename}](medias/{cleaned_filename})")
                            else:
                                attachments_info.append(f"[Fichier: {attachment.filename}](medias/{cleaned_filename})")
                        except Exception as e:
                            print(f"Erreur lors du téléchargement de {attachment.filename} pour le message {message.id} : {e}")
                    for embed in message.embeds:
                        embed_text_lines = []
                        if embed.title:
                            embed_text_lines.append(f"**Titre de l'embed:** {embed.title}")
                        if embed.description:
                            embed_text_lines.append(f"**Description de l'embed:** {embed.description}")
                        for field in embed.fields:
                            embed_text_lines.append(f"**{field.name}:** {field.value}")
                        if embed_text_lines:
                            embeds_info.append("\n".join(embed_text_lines))
                    message_entry = f"---\n**Auteur :** {author}\n**Date :** {timestamp}\n"
                    if content:
                        message_entry += f"**Contenu :**\n{content}\n\n"
                    if attachments_info:
                        message_entry += "\n".join(attachments_info) + "\n\n"
                    if embeds_info:
                        message_entry += "**Embeds :**\n" + "\n---\n".join(embeds_info) + "\n\n"
                    dump_content.append(message_entry)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(dump_content))
                print(f"Extraction terminée. Contenu enregistré dans {OUTPUT_FILE}")
                print(f"Total messages traités : {total_messages}")
                print(f"Total médias téléchargés : {total_medias}")
            except discord.errors.Forbidden:
                print(f"Erreur de permission : Le bot n'a pas les droits nécessaires pour accéder au salon {channel.name}.")
            except Exception as e:
                print(f"Une erreur inattendue est survenue lors de l'extraction des messages : {e}")
        print("Déconnexion du bot.")
client = MyClient(intents=intents)
if TOKEN is None:
    print("Erreur : Le token DISCORD_BOT_TOKEN n'est pas configuré dans le fichier .env")
else:
    try:
        client.run(TOKEN)
    except discord.errors.LoginFailure:
        print("Erreur de connexion : Le token fourni est invalide.")
    except Exception as e:
        print(f"Une erreur est survenue lors du démarrage du bot : {e}")