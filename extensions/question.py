import json
import logging
import os
from datetime import datetime, timedelta, timezone
import asyncio
import re
from discord.ext import commands
import discord
from constants import *
from extensions.forum_i18n import t, code_for
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
TAG_OPTIONS = [
    discord.SelectOption(label="Stuff | Shell", emoji="🏹"),
    discord.SelectOption(label="SP Card", emoji="🃏"),
    discord.SelectOption(label="Costume | Jewelry", emoji="💎"),
    discord.SelectOption(label="Pet | Partner", emoji="🐶"),
    discord.SelectOption(label="Buff | Debuff", emoji="🌠"),
    discord.SelectOption(label="XP | Quest | TS", emoji="📈"),
    discord.SelectOption(label="Gold | Drop | N$", emoji="💰"),
    discord.SelectOption(label="Raid | Monster", emoji="🏰"),
    discord.SelectOption(label="PvP", emoji="⚔️"),
    discord.SelectOption(label="Event", emoji="🎉"),
    discord.SelectOption(label="Tech | Bug", emoji="🖥️"),
    discord.SelectOption(label="Other", emoji="❓"),
]
DATA_PATH = "extensions/threads.json"
KEYWORDS_PATH = "extensions/nostale_keywords.json"
RULES_URL = f"https://discord.com/channels/{GUILD_ID_GSTAR}/{REGLEMENT_CHANNEL_ID}"
QUESTIONS_URL = f"https://discord.com/channels/{GUILD_ID_GSTAR}/{QUESTION_CHANNEL_ID}"
INTERROGATIVE_WORDS = [
    "qui", "que", "quoi", "qu'", "où", "quand", "pourquoi", "comment", "est-ce", "combien",
    "quel", "quelle", "quels", "quelles", "lequel", "laquelle", "lesquels", "lesquelles", "est",
    "how", "why", "what", "which", "where", "when", "how many", "how much", "can", "should", "is", "are", "do", "does",
    "wie", "warum", "was", "welche", "welcher", "welches", "wo", "wann", "wie viele", "kann man", "soll man", "ist", "wer",
    "come", "perché", "quale", "quali", "dove", "quando", "quanto", "quanti", "si può", "bisogna", "è", "chi", "cosa",
    "cómo", "por qué", "qué", "cuál", "cuáles", "dónde", "cuándo", "cuánto", "se puede", "hay que", "es", "quién",
    "jak", "dlaczego", "co", "który", "która", "które", "gdzie", "kiedy", "ile", "czy można", "czy trzeba", "czy", "kto",
    "как", "почему", "что", "какой", "какая", "какое", "где", "когда", "сколько", "можно ли", "нужно ли", "кто",
    "proč", "kde", "kdy", "kolik", "lze", "je třeba", "kdo", "jaký",
    "nasıl", "neden", "ne", "hangi", "nerede", "ne zaman", "kaç", "kim", "niçin", "niye",
]
INTERROGATIVE_EXPRESSIONS = [
    "-t-", "-on", "-je", "-tu", "-il", "-elle", "-nous", "-vous", "-ils", "-elles"
]
def is_strict_question(sentence):
    interrogative_verbs = [
        "peut", "doit", "va", "faut", "a", "est", "sera", "serait", "était", "aurait", "avait",
        "fera", "ferait", "devrait", "pourrait", "voudrait", "fera-t", "ferait-t", "devrait-t"
    ]
    interrogative_pattern = re.compile(
        rf"^({'|'.join(re.escape(word) for word in INTERROGATIVE_WORDS)})"
        rf"|^({'|'.join(re.escape(verb) + re.escape(exp) for verb in interrogative_verbs for exp in INTERROGATIVE_EXPRESSIONS)})",
        re.IGNORECASE
    )
    end_pattern = re.compile(r".*\?$")
    return bool(interrogative_pattern.match(sentence)) and bool(end_pattern.match(sentence))
def is_discussion_question(sentence):
    start_pattern = re.compile(rf"^({'|'.join(re.escape(word) for word in INTERROGATIVE_WORDS)})", re.IGNORECASE)
    end_pattern = re.compile(r".*\?$")
    return bool(start_pattern.match(sentence)) or bool(end_pattern.match(sentence))
def naive_datetime(dt):
    return dt.replace(tzinfo=None)
async def delete_recent_bot_messages(bot, channel, exclude_message_ids, special_message_ids=[]):
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    time_limit = now - timedelta(seconds=65)
    try:
        async for message in channel.history(limit=100):
            if (
                message.author == bot.user
                and naive_datetime(message.created_at) > naive_datetime(time_limit)
                and message.id not in exclude_message_ids
                and message.id not in special_message_ids
            ):
                try:
                    await message.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    pass
    except Exception:
        pass
class Question(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.threads = {}
        self.embed_messages = {}
        self.delete_messages = {}
        self.last_asked = {}
        self.exception_messages = {}
    def get_question_error(self, title, selected_tags=None):
        errors = []
        words = title.split()
        first_word_original = words[0] if words else ""
        lower_title = title.lower()
        if not first_word_original or not first_word_original[0].isupper():
            errors.append("err_uppercase")
        if not is_strict_question(title):
            if not re.match(rf"^({'|'.join(re.escape(word) for word in INTERROGATIVE_WORDS)})(\s|[-])", title, re.IGNORECASE):
                errors.append("err_interrogative")
            if not title.endswith('?'):
                errors.append("err_question_mark")
        if len(lower_title) < 20:
            errors.append("err_too_short")
        if len(lower_title) > 100:
            errors.append("err_too_long")
        if not selected_tags and not self.thread_has_tags(selected_tags):
            errors.append("err_tag_missing")
        return errors if errors else None
    def thread_has_tags(self, selected_tags):
        if selected_tags:
            return True
        if hasattr(self, "thread") and self.thread and self.thread.applied_tags:
            return True
        return False
    async def handle_timeout(self, thread):
        if self.delete_messages.get(thread.id, False):
            user = thread.owner
            if user is None:
                try:
                    async for message in thread.history(limit=1, oldest_first=True):
                        user = message.author
                        break
                except:
                    return
            title = thread.name
            try:
                async for message in thread.history(limit=1, oldest_first=True):
                    content = message.content
                    image_url = None
                    if message.attachments:
                        image_url = message.attachments[0].url
                    break
            except:
                content = "Contenu non disponible"
                image_url = None
            message_to_send = (
                f"Votre fil '{title}' a été supprimé car vous avez mis plus de 10 minutes à répondre au questionnaire.\n\n"
                f"**Contenu du fil :**\n{content}"
            )
            try:
                if user is not None:
                    await user.send(message_to_send)
                    if image_url:
                        await user.send(image_url)
            except:
                pass
            try:
                await thread.delete()
            except:
                pass
            role = discord.utils.get(thread.guild.roles, id=QUESTION_ROLE_ID)
            if role and user:
                await user.remove_roles(role)
        else:
            try:
                await thread.send("Le temps est écoulé, mais votre question n'a pas été déplacée.")
            except:
                pass
    def create_answer_view(self, thread, message_id, bot, original_message, author):
        return AnswerView(thread, message_id, self.get_question_error, bot, original_message, author)
    async def monitor_thread(self, thread):
        await asyncio.sleep(600)
        if self.delete_messages.get(thread.id, False):
            await self.handle_timeout(thread)
    @commands.Cog.listener()
    async def on_ready(self):
        discussion_channel = self.bot.get_channel(DISCUSSION_CHANNEL_ID)
        await delete_recent_bot_messages(self.bot, discussion_channel, [])
    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        if thread.parent_id in GATE_FORUM_IDS:
            return
        if thread.parent_id != QUESTION_CHANNEL_ID:
            return
        message = None
        attempts = 3
        for _ in range(attempts):
            async for msg in thread.history(limit=1):
                message = msg
                await message.pin()
                message_id = message.id
                break
            if message:
                break
            await asyncio.sleep(1)
        if message is None:
            return
        self.threads[thread.id] = message.author.id
        self.delete_messages[thread.id] = True
        error_types = self.get_question_error(thread.name, thread.applied_tags)
        if not error_types:
            success_embed = send_success_message(thread.name)
            view = self.create_answer_view(thread, message_id, self.bot, None, message.author)
            view.remove_tag_select()
            embed_message = await thread.send(
                content=message.author.mention if message.author else "",
                embed=success_embed,
                view=view
            )
            self.embed_messages[thread.id] = embed_message.id
            self.delete_messages[thread.id] = False
            self.exception_messages.setdefault(thread.id, set()).add(embed_message.id)
        else:
            role = discord.utils.get(thread.guild.roles, id=QUESTION_ROLE_ID)
            if role and message.author and not message.author.bot:
                await message.author.add_roles(role)
            error_embed = send_error_message(thread.name, error_types)
            view = self.create_answer_view(thread, message_id, self.bot, None, message.author)
            error_embed_message = await thread.send(
                content=message.author.mention if message.author else "",
                embed=error_embed,
                view=view
            )
            self.embed_messages[thread.id] = error_embed_message.id
            self.exception_messages.setdefault(thread.id, set()).add(error_embed_message.id)
            view.message_id = error_embed_message.id
            asyncio.create_task(self.monitor_thread(thread))
    def user_has_stopped(self, user_id):
        stop_file = "stop_users.json"
        if os.path.exists(stop_file):
            with open(stop_file, "r") as f:
                stop_users = json.load(f)
            return user_id in stop_users
        return False
    @commands.Cog.listener()
    async def on_message(self, message):
        if isinstance(message.channel, discord.Thread):
            thread = message.channel
            if self.delete_messages.get(thread.id, False):
                exception_message_ids = self.exception_messages.get(thread.id, set())
                if message.id in exception_message_ids:
                    return
                if message.type != discord.MessageType.channel_name_change and not message.is_system():
                    if not message.author.bot:
                        await message.delete()
                        if message.author.id != self.threads.get(thread.id):
                            try:
                                await message.author.send(
                                    f"Vous ne pouvez pas écrire dans ce fil tant que le titre n'est pas corrigé : {thread.jump_url}"
                                )
                            except:
                                pass
                        else:
                            try:
                                await message.author.send(
                                    f"Veuillez cliquer sur le bouton `Modifier le titre` de votre fil pour corriger le titre : {thread.jump_url}"
                                )
                            except:
                                pass
        if message.author.bot:
            return
        if message.channel.id == DISCUSSION_CHANNEL_ID:
            if self.user_has_stopped(message.author.id):
                return
            content = message.content.strip()
            if (is_discussion_question(content) and len(content) >= 10):
                last_asked_time = self.last_asked.get(message.author.id)
                if last_asked_time and (datetime.now() - last_asked_time).total_seconds() < 259200:
                    return
                self.last_asked[message.author.id] = datetime.now()
                view = QuestionDetectedView(message, self.bot)
                code = code_for(message.author)
                embed = discord.Embed(
                    title=t("qd_title", code),
                    description=t("qd_desc", code, rules_url=RULES_URL, questions_url=QUESTIONS_URL),
                    color=discord.Color.blue()
                )
                confirmation_message = await message.reply(embed=embed, view=view)
                view.confirmation_message = confirmation_message
                view.message_id = message.id
    @commands.Cog.listener()
    async def on_thread_update(self, before, after):
        if before.parent_id in GATE_FORUM_IDS:
            return
        if before.parent_id != QUESTION_CHANNEL_ID or before.name == after.name:
            return
        error_types = self.get_question_error(after.name, after.applied_tags)
        try:
            message_id = self.embed_messages.get(after.id)
            embed_message = await after.fetch_message(message_id)
        except discord.NotFound:
            return
        if error_types:
            error_embed = send_error_message(after.name, error_types)
            view = self.create_answer_view(after, message_id, self.bot, None, after.owner)
            await embed_message.edit(content=after.owner.mention, embed=error_embed, view=view)
            self.delete_messages[after.id] = True
            self.exception_messages.setdefault(after.id, set()).add(embed_message.id)
            role = discord.utils.get(after.guild.roles, id=QUESTION_ROLE_ID)
            if role and not after.owner.bot:
                await after.owner.add_roles(role)
        else:
            success_embed = send_success_message(after.name)
            view = self.create_answer_view(after, message_id, self.bot, None, after.owner)
            view.remove_tag_select()
            await embed_message.edit(content=after.owner.mention, embed=success_embed, view=view)
            self.delete_messages[after.id] = False
            self.exception_messages.setdefault(after.id, set()).add(embed_message.id)
            role = discord.utils.get(after.guild.roles, id=QUESTION_ROLE_ID)
            if role and not after.owner.bot:
                await after.owner.remove_roles(role)
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        for view in self.bot.persistent_views:
            if (
                isinstance(view, QuestionDetectedView)
                and view.confirmation_message
                and view.confirmation_message.id == message.id
            ):
                try:
                    await view.message.delete()
                except:
                    pass
                break
async def setup(bot):
    await bot.add_cog(Question(bot))
class StopConfirmView(discord.ui.View):
    def __init__(self, message, bot, question_view):
        super().__init__(timeout=60)
        self.message = message
        self.bot = bot
        self.question_view = question_view
        self.confirmation_message = None
        self.confirmed_or_cancelled = False
        code = code_for(message.author)
        self.children[0].label = t("btn_confirm", code)
        self.children[1].label = t("btn_cancel", code)
    async def record_stop_user(self, user_id):
        stop_file = "stop_users.json"
        if os.path.exists(stop_file):
            with open(stop_file, "r") as f:
                stop_users = json.load(f)
        else:
            stop_users = []
        if user_id not in stop_users:
            stop_users.append(user_id)
            with open(stop_file, "w") as f:
                json.dump(stop_users, f)
    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.message.author:
            await interaction.response.send_message(
                t("only_question_author", code_for(interaction.user)),
                ephemeral=True
            )
            return
        await self.record_stop_user(interaction.user.id)
        special_message = await self.message.channel.send(
            f"{self.message.author.mention} " + t("stop_done", code_for(self.message.author))
        )
        self.confirmed_or_cancelled = True
        self.disable_buttons()
        await delete_recent_bot_messages(
            self.bot,
            self.message.channel,
            [self.confirmation_message.id],
            special_message_ids=[special_message.id]
        )
        if self.confirmation_message:
            try:
                await self.confirmation_message.delete()
            except discord.NotFound:
                pass
    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.message.author:
            await interaction.response.send_message(
                t("only_question_author", code_for(interaction.user)),
                ephemeral=True
            )
            return
        stop_file = "stop_users.json"
        if os.path.exists(stop_file):
            with open(stop_file, "r") as f:
                stop_users = json.load(f)
            if interaction.user.id in stop_users:
                stop_users.remove(interaction.user.id)
                with open(stop_file, "w") as f:
                    json.dump(stop_users, f)
        await interaction.response.send_message(
            t("stop_cancelled", code_for(interaction.user)),
            ephemeral=True
        )
        self.confirmed_or_cancelled = True
        self.disable_buttons()
        await delete_recent_bot_messages(
            self.bot,
            self.message.channel,
            [self.confirmation_message.id]
        )
        if self.confirmation_message:
            try:
                await self.confirmation_message.delete()
            except discord.NotFound:
                pass
    async def on_timeout(self):
        if not self.confirmed_or_cancelled:
            timeout_message = await self.message.channel.send(
                f"{self.message.author.mention} " + t("timeout_not_moved", code_for(self.message.author))
            )
            await delete_recent_bot_messages(self.bot, self.message.channel, [timeout_message.id])
        else:
            await delete_recent_bot_messages(self.bot, self.message.channel, [])
        self.stop()
    def disable_buttons(self):
        for item in self.children:
            item.disabled = True
        self.stop()
class QuestionDetectedView(discord.ui.View):
    def __init__(self, message, bot):
        super().__init__(timeout=60)
        self.message = message
        self.bot = bot
        self.confirmation_message = None
        self.message_id = message.id
        self.confirmation_view = StopConfirmView(self.message, self.bot, self)
        self.stop_requested = False
        self.confirmed_or_cancelled = False
        code = code_for(message.author)
        self.children[0].label = t("btn_yes", code)
        self.children[1].label = t("btn_no", code)
        self.children[2].label = t("btn_stop", code)
    @discord.ui.button(label="Oui", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.message.author:
            await interaction.response.send_message(
                t("only_question_author", code_for(interaction.user)),
                ephemeral=True
            )
            return
        author_code = code_for(self.message.author)
        question_channel = self.bot.get_channel(QUESTION_CHANNEL_ID)
        initial_content = f"Posté par : {self.message.author.id}\n{self.message.content}"
        if not initial_content.strip():
            initial_content = "Contenu par défaut"
        new_thread = None
        thread_message = None
        try:
            webhook = await get_webhook(question_channel)
            webhook_message = await webhook.send(
                content=initial_content,
                username=self.message.author.display_name,
                avatar_url=self.message.author.display_avatar.url,
                wait=True,
                thread_name=self.message.content[:50]
            )
            thread_message = await webhook_message.fetch()
            new_thread = await self.bot.fetch_channel(thread_message.id)
            await new_thread.add_user(self.message.author)
            view = self.bot.get_cog('Question').create_answer_view(
                new_thread,
                thread_message.id,
                self.bot,
                self.message,
                self.message.author
            )
            success_embed = discord.Embed(
                title=t("moved_success_title", author_code),
                description=t("moved_success_desc", author_code),
                color=discord.Color.green()
            )
            await webhook.edit_message(
                thread_message.id,
                content=self.message.author.mention,
                embed=success_embed,
                view=view,
                thread=new_thread
            )
            self.confirmed_or_cancelled = True
            self.stop_requested = True
        except discord.HTTPException as e:
            if e.code == 50006:
                pass
            error_embed = discord.Embed(
                title=t("move_error_title", author_code),
                description=t("move_error_desc", author_code, error=e),
                color=discord.Color.red()
            )
            await question_channel.send(content=self.message.author.mention, embed=error_embed)
            await interaction.response.send_message(t("thread_create_error", code_for(interaction.user)), ephemeral=True)
            return
        if new_thread:
            try:
                await interaction.message.delete()
                await self.message.delete()
            except:
                pass
            special_message = await self.bot.get_channel(DISCUSSION_CHANNEL_ID).send(
                f"{self.message.author.mention} " + t("moved_to_thread", author_code, thread=f"<#{new_thread.id}>")
            )
            async for msg in new_thread.history(limit=10):
                if msg.author == self.bot.user and not msg.is_system() and msg.id != thread_message.id:
                    await msg.delete()
            error_types = self.bot.get_cog('Question').get_question_error(new_thread.name, new_thread.applied_tags)
            if error_types:
                error_embed = send_error_message(new_thread.name, error_types, author_code)
                view = self.bot.get_cog('Question').create_answer_view(
                    new_thread,
                    thread_message.id,
                    self.bot,
                    self.message,
                    self.message.author
                )
                await webhook.edit_message(
                    thread_message.id,
                    content=self.message.author.mention,
                    embed=error_embed,
                    view=view,
                    thread=new_thread
                )
            else:
                success_embed = send_success_message(new_thread.name, author_code)
                await webhook.edit_message(
                    thread_message.id,
                    content=self.message.author.mention,
                    embed=success_embed,
                    thread=new_thread
                )
            self.confirmed_or_cancelled = True
        else:
            await interaction.response.send_message(t("thread_create_error", code_for(interaction.user)), ephemeral=True)
    @discord.ui.button(label="Non", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.message.author:
            await interaction.response.send_message(
                t("only_question_author", code_for(interaction.user)),
                ephemeral=True
            )
            return
        try:
            if self.confirmation_message:
                await self.confirmation_message.delete()
        except:
            pass
        try:
            if interaction.message:
                await interaction.message.delete()
        except:
            pass
        await self.message.channel.send(
            f"{self.message.author.mention} " + t("not_moved", code_for(self.message.author))
        )
        self.confirmed_or_cancelled = True
        self.stop()
    @discord.ui.button(label="STOP", style=discord.ButtonStyle.grey)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.message.author:
            await interaction.response.send_message(
                t("only_question_author", code_for(interaction.user)),
                ephemeral=True
            )
            return
        self.stop_requested = True
        await self.show_confirmation(interaction)
    async def show_confirmation(self, interaction):
        confirm_view = StopConfirmView(self.message, self.bot, self)
        code = code_for(self.message.author)
        confirm_embed = discord.Embed(
            title=t("stop_confirm_title", code),
            description=t("stop_confirm_desc", code),
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=False)
        self.confirmation_message = await interaction.original_response()
        confirm_view.confirmation_message = self.confirmation_message
        self.confirmation_view = confirm_view
    async def on_timeout(self):
        if self.stop_requested:
            return
        try:
            if self.confirmation_message:
                await self.confirmation_message.delete()
        except:
            pass
        if not self.confirmed_or_cancelled:
            timeout_message = await self.message.channel.send(
                f"{self.message.author.mention} " + t("timeout_not_moved", code_for(self.message.author))
            )
            await delete_recent_bot_messages(self.bot, self.message.channel, [timeout_message.id])
        else:
            await delete_recent_bot_messages(self.bot, self.message.channel, [])
        self.stop()
class TitleModal(discord.ui.Modal):
    def __init__(self, thread, message_id, get_question_error, bot, original_message, author, webhook, selected_tags):
        code = code_for(author)
        super().__init__(title=t("modal_title", code))
        self.thread = thread
        self.message_id = message_id
        self.get_question_error = get_question_error
        self.bot = bot
        self.original_message = original_message
        self.author = author
        self.webhook = webhook
        self.selected_tags = selected_tags
        self.add_item(discord.ui.TextInput(
            label=t("modal_input_label", code),
            style=discord.TextStyle.short,
            placeholder=t("modal_input_placeholder", code),
            custom_id="new_title",
            min_length=20,
            max_length=100
        ))
    async def on_submit(self, interaction: discord.Interaction):
        code = code_for(self.author)
        if interaction.user != self.author:
            await interaction.response.send_message(t("only_thread_author", code_for(interaction.user)), ephemeral=True)
            return
        new_title = self.children[0].value
        error_types = self.get_question_error(new_title, self.selected_tags)
        try:
            message = await self.thread.fetch_message(self.message_id)
        except discord.NotFound:
            await interaction.response.send_message(t("msg_not_found", code), ephemeral=True)
            return
        if error_types:
            error_embed = send_error_message(new_title, error_types, code)
            if message.author.id == self.bot.user.id:
                await message.edit(content=self.author.mention, embed=error_embed)
            else:
                await self.webhook.edit_message(
                    self.message_id,
                    content=self.author.mention,
                    embed=error_embed,
                    thread=self.thread
                )
            await interaction.response.send_message(t("title_still_errors", code), ephemeral=True)
        else:
            forum_tags = [tag for tag in self.thread.parent.available_tags if tag.name in self.selected_tags]
            await self.thread.edit(name=new_title, applied_tags=forum_tags)
            success_embed = send_success_message(new_title, code)
            view = self.bot.get_cog('Question').create_answer_view(
                self.thread,
                self.message_id,
                self.bot,
                self.original_message,
                self.author
            )
            view.remove_tag_select()
            if message.author.id == self.bot.user.id:
                await message.edit(content=self.author.mention, embed=success_embed, view=view)
            else:
                await self.webhook.edit_message(
                    self.message_id,
                    content=self.author.mention,
                    embed=success_embed,
                    view=view,
                    thread=self.thread
                )
            await interaction.response.send_message(t("title_updated", code), ephemeral=True)
            self.bot.get_cog('Question').delete_messages[self.thread.id] = False
            role = discord.utils.get(self.thread.guild.roles, id=QUESTION_ROLE_ID)
            if role:
                await self.author.remove_roles(role)
class TagSelect(discord.ui.Select):
    def __init__(self, author_id, selected_tags, message_id, get_question_error, thread, bot):
        self.author_id = author_id
        self.selected_tags = selected_tags
        self.message_id = message_id
        self.get_question_error = get_question_error
        self.thread = thread
        self.bot = bot
        member = thread.guild.get_member(author_id) if getattr(thread, "guild", None) else None
        super().__init__(
            placeholder=t("tag_placeholder", code_for(member)),
            min_values=1,
            max_values=len(TAG_OPTIONS),
            options=TAG_OPTIONS
        )
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(t("no_permission", code_for(interaction.user)), ephemeral=True)
            return
        code = code_for(interaction.user)
        self.selected_tags[:] = self.values
        error_types = self.get_question_error(self.thread.name, self.selected_tags)
        try:
            message = await self.thread.fetch_message(self.message_id)
        except discord.NotFound:
            await interaction.response.send_message(t("msg_not_found", code), ephemeral=True)
            return
        if error_types:
            error_embed = send_error_message(self.thread.name, error_types, code)
            if message.author.id == self.bot.user.id:
                await message.edit(content=message.author.mention, embed=error_embed)
            else:
                webhook = await get_webhook(self.thread.parent)
                await webhook.edit_message(
                    self.message_id,
                    content=message.author.mention,
                    embed=error_embed,
                    thread=self.thread
                )
            await interaction.response.send_message(
                t("tags_updated_errors", code),
                ephemeral=True
            )
        else:
            forum_tags = [tag for tag in self.thread.parent.available_tags if tag.name in self.selected_tags]
            await self.thread.edit(applied_tags=forum_tags)
            success_embed = send_success_message(self.thread.name, code)
            if message.author.id == self.bot.user.id:
                await message.edit(content=message.author.mention, embed=success_embed)
            else:
                webhook = await get_webhook(self.thread.parent)
                await webhook.edit_message(
                    self.message_id,
                    content=message.author.mention,
                    embed=success_embed,
                    thread=self.thread
                )
            await interaction.response.send_message(
                t("tags_updated_ok", code),
                ephemeral=True
            )
            self.bot.get_cog('Question').delete_messages[self.thread.id] = False
class TagSelectView(discord.ui.View):
    def __init__(self, author_id, selected_tags, message_id, get_question_error, thread, bot):
        super().__init__(timeout=None)
        self.add_item(TagSelect(author_id, selected_tags, message_id, get_question_error, thread, bot))
    def remove_tag_select(self):
        for item in self.children:
            if isinstance(item, TagSelect):
                self.remove_item(item)
class AnswerView(discord.ui.View):
    def __init__(self, thread, message_id, get_question_error, bot, original_message, author):
        super().__init__(timeout=None)
        self.thread = thread
        self.message_id = message_id
        self.get_question_error = get_question_error
        self.bot = bot
        self.original_message = original_message
        self.author = author
        self.selected_tags = [tag.name for tag in thread.applied_tags]
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t("btn_modify_title", code_for(author))
        if not self.selected_tags:
            self.add_item(TagSelect(author.id, self.selected_tags, message_id, get_question_error, thread, bot))
    def remove_tag_select(self):
        for item in self.children:
            if isinstance(item, TagSelect):
                self.remove_item(item)
    @discord.ui.button(label="Modifier le titre", style=discord.ButtonStyle.grey)
    async def modify_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message(t("only_thread_author", code_for(interaction.user)), ephemeral=True)
            return
        modal = TitleModal(
            self.thread,
            self.message_id,
            self.get_question_error,
            self.bot,
            self.original_message,
            self.author,
            await get_webhook(self.thread.parent),
            self.selected_tags
        )
        await interaction.response.send_modal(modal)
async def get_webhook(channel):
    webhooks = await channel.webhooks()
    webhook = discord.utils.find(lambda wh: wh.user == channel.guild.me, webhooks)
    if webhook is None:
        webhook = await channel.create_webhook(name="MessageForwarder", reason="Pour reposter les messages")
    return webhook
def send_error_message(title, error_codes, code="en"):
    if error_codes is None:
        error_codes = []
    error_list = "\n- ".join(t(c, code) for c in error_codes)
    if error_codes == ["err_interrogative"]:
        interrogative_list = ", ".join([f"`{word}`" for word in INTERROGATIVE_WORDS + INTERROGATIVE_EXPRESSIONS])
        error_list += "\n\n" + t("valid_interrogatives", code, list=interrogative_list)
    message = (
        t("title_errors_intro", code, title=title) + f"\n- {error_list}\n\n"
        + t("title_errors_outro", code)
    )
    embed = discord.Embed(title=t("error_title_embed", code), description=message, color=discord.Color.red())
    return embed
def send_success_message(title, code="en"):
    embed = discord.Embed(
        title=t("success_title_embed", code),
        description=t("success_desc", code),
        color=discord.Color.green()
    )
    return embed
async def setup(bot):
    await bot.add_cog(Question(bot))