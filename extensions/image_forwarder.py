import json
import hashlib
from datetime import datetime, timedelta
from typing import Callable, Awaitable, Literal
from functools import partial
import asyncio
import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import discord.utils
from dateutil import tz
from constants import (
    DELETE_COOLDOWN_HOURS, RAIDS_EMOTES, COMMERCES_ID, SIGNALEMENT_VENTES_ID, GSTAR_USER_ID, ACTIVITES_ID,
    ACTIVITY_CHANNELS, TRADE_CHANNELS, RAIDS_COSMOS_ID, RAIDS_NOSFIRE_ID, LOCKED_CHANNELS_1,
    LOCKED_CHANNELS_2, RAIDS_LIST, RAID_ROLE_MAPPING, ACTIVITY_TYPES,
    ACTIVITY_TAG_MAP, TRADE_TAG_MAP, TRADE_TAG_REV, ACTIVITY_TAG_REV
)
DATA_PATH = "datas/image_forwarder"
FRA = tz.gettz('Europe/Paris')
SANCTION_ROLE_ID = 860485552011477022
NO_VALIDE_EMOJI = "<:no_valide:1125533828602150972>"
INFO_IMAGE_URL = "https://www.zupimages.net/up/24/11/siro.png"
WARN_DELETE_SECONDS = 300
DEDUP_WINDOW_SECONDS = 10
MAX_COMMERCE_TOTAL_TAGS = 5
MAX_COMMERCE_USER_TAGS = 4
class ActionsView(discord.ui.View):
    def __init__(self, thread_to_messages: dict[str, list[int]]) -> None:
        super().__init__(timeout=None)
        self.thread_to_messages = thread_to_messages
    @discord.ui.button(label="UP", style=discord.ButtonStyle.success, custom_id="up_button_v2")
    async def up_announcement(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        thread: discord.Thread = interaction.channel
        author = interaction.user
        if author.id not in {GSTAR_USER_ID, thread.owner_id}:
            await interaction.followup.send("You can only bump your own ads.", ephemeral=True)
            return
        if any(r.id == SANCTION_ROLE_ID for r in author.roles) or (author.voice and author.voice.mute):
            await interaction.followup.send("You can't bump because you are sanctioned.", ephemeral=True)
            return
        cog = interaction.client.get_cog("ImageForwarder")
        if not cog:
            await interaction.followup.send("The module is not loaded.", ephemeral=True)
            return
        try:
            await cog.handle_up_announcement(interaction, thread, author)
        except Exception as e:
            print(f"Erreur lors du up : {e}")
            await interaction.followup.send("Internal error while bumping.", ephemeral=True)
    @discord.ui.button(label="Delete my ad", style=discord.ButtonStyle.danger, custom_id="delete_button_v2")
    async def delete(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        thread: discord.Thread = interaction.channel
        author = interaction.user
        if author.id not in {GSTAR_USER_ID, thread.owner_id}:
            await interaction.followup.send("You can only delete your own ads.", ephemeral=True)
            return
        await interaction.edit_original_response(
            view=DeleteView(interaction, self.thread_to_messages)
        )
class DeleteView(discord.ui.View):
    def __init__(
        self,
        target_interaction: discord.Interaction,
        thread_to_messages: dict[str, list[int]]
    ):
        super().__init__(timeout=None)
        self.target_interaction = target_interaction
        self.thread_to_messages = thread_to_messages
    @discord.ui.button(label="Confirm deletion", style=discord.ButtonStyle.danger, custom_id="confirm_delete")
    async def delete(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(thinking=False)
        try:
            target: discord.Thread = interaction.channel
            await target.edit(archived=True, locked=True)
            if str(target.id) not in self.thread_to_messages:
                return
            repost_channel_id = await get_target_channel_id_and_add_tags(target, None, None, None, None)
            repost_channel = interaction.guild.get_channel(repost_channel_id)
            if not repost_channel:
                raise Exception(f"channel introuvable {repost_channel_id=}")
            for msg_id in self.thread_to_messages[str(target.id)]:
                await repost_channel.get_partial_message(msg_id).delete()
            del self.thread_to_messages[str(target.id)]
        except discord.NotFound:
            pass
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_delete")
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message("Deletion cancelled!", ephemeral=True)
        await self.target_interaction.edit_original_response(
            content="",
            view=ActionsView(self.thread_to_messages)
        )
class CommerceTypeView(discord.ui.View):
    def __init__(self, callback: Callable[[str], Awaitable[None]], author_id: int, thread: discord.Thread):
        super().__init__(timeout=300)
        self.callback = callback
        self.author_id = author_id
        self.thread = thread
        self.interaction_received = False
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not allowed.", ephemeral=True)
            return False
        return True
    @discord.ui.button(label="Buy", style=discord.ButtonStyle.green, custom_id="buy")
    async def buy(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.interaction_received = True
        await interaction.response.defer()
        try:
            new_callback = partial(self.callback, trade_type="Achat")
            await end_view_chain(interaction, new_callback, edit_original_message=True)
        except Exception as e:
            print(f"Erreur bouton Achat : {e}")
            await interaction.followup.send("Internal error.", ephemeral=True)
    @discord.ui.button(label="Sell", style=discord.ButtonStyle.blurple, custom_id="sell")
    async def sell(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.interaction_received = True
        await interaction.response.defer()
        try:
            new_callback = partial(self.callback, trade_type="Vente")
            await end_view_chain(interaction, new_callback, edit_original_message=True)
        except Exception as e:
            print(f"Erreur bouton Vente : {e}")
            await interaction.followup.send("Internal error.", ephemeral=True)
    async def on_timeout(self):
        if not self.interaction_received:
            try:
                print(f"Timeout reached for thread {self.thread.id}")
                thread_title = self.thread.name
                await self.thread.delete()
                await self.thread.owner.send(
                    f"Your thread '{thread_title}' was deleted because you didn't choose Buy or Sell in time."
                )
            except Exception as e:
                print(f"Erreur suppression ou MP : {e}")
class RaidSelectView(discord.ui.View):
    def __init__(self, author_id: int, repost_message, thread: discord.Thread, *, page=0):
        super().__init__(timeout=10)
        self.author_id = author_id
        self.repost_message = repost_message
        self.page = page
        self.thread = thread
        self.interaction_received = False
        self.max_page = len(RAIDS_LIST) // 25 + (1 if len(RAIDS_LIST) % 25 else 0)
        self.add_item(RaidSelect(author_id, self.repost_message, thread, page=page))
        if page > 0:
            self.add_item(PageButton(author_id, -1))
        if page < self.max_page - 1:
            self.add_item(PageButton(author_id, 1))
class RaidSelect(discord.ui.Select[RaidSelectView]):
    def __init__(self, author_id: int, repost_message, thread: discord.Thread, page=0):
        self.author_id = author_id
        self.repost_message = repost_message
        self.thread = thread
        options = [
            discord.SelectOption(label=raid, value=raid, emoji=RAIDS_EMOTES.get(raid))
            for raid in RAIDS_LIST[page * 25 : min((page + 1) * 25, len(RAIDS_LIST))]
        ]
        super().__init__(
            placeholder='Choose raids',
            min_values=1,
            max_values=min(len(options), 25),
            options=options
        )
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not allowed.", ephemeral=True)
            return
        self.view.interaction_received = True
        new_callback = partial(self.repost_message, selected_raids=self.values)
        await end_view_chain(interaction, new_callback, is_raid_search=True)
class PageButton(discord.ui.Button[RaidSelectView]):
    def __init__(self, author_id: int, page_to_add: Literal[-1, 1]):
        label = "◀️ Previous page" if page_to_add == -1 else "Next page ▶️"
        super().__init__(style=discord.ButtonStyle.secondary, label=label)
        self.author_id = author_id
        self.page_to_add = page_to_add
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not allowed.", ephemeral=True)
            return
        view = self.view
        view.clear_items()
        new_view = RaidSelectView(
            self.author_id,
            self.view.repost_message,
            self.view.thread,
            page=view.page + self.page_to_add
        )
        await interaction.response.edit_message(view=new_view)
async def end_view_chain(
    target: discord.Interaction | discord.Thread,
    callback,
    server="cosmos",
    is_raid_search=False,
    edit_original_message=False
):
    try:
        target_channel_id, thread_to_messages = await callback(server=server)
        base_message = f":white_check_mark: Ad posted in <#{target_channel_id}>.\n"
        raid_message = (
            ":warning: Raid roles in <id:customize> .\n"
            ":warning: No reposting for a raid search."
            if is_raid_search
            else ""
        )
        actions_view = ActionsView(thread_to_messages)
        if isinstance(target, discord.Thread):
            await target.send(content=base_message + raid_message, view=actions_view)
        else:
            if edit_original_message:
                await target.edit_original_response(
                    content=base_message + raid_message,
                    view=actions_view
                )
            else:
                await target.response.edit_message(
                    content=base_message + raid_message,
                    view=actions_view
                )
    except Exception as e:
        print(f"Erreur end_view_chain: {e}")
class ImageNavigator(discord.ui.View):
    def __init__(self, images: list, title: str, description: str, color: discord.Color):
        super().__init__(timeout=None)
        self.images = images
        self.current_image = 0
        self.title = title
        self.description = description
        self.color = color
    def update_embed(self, image_index):
        embed = discord.Embed(title=self.title, description=self.description, color=self.color)
        embed.set_image(url=self.images[image_index])
        embed.set_footer(text=f"{image_index + 1} / {len(self.images)}")
        return embed
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.grey, custom_id="previous_image")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_image = (self.current_image - 1) % len(self.images)
        embed = self.update_embed(self.current_image)
        await interaction.response.edit_message(embed=embed, view=self)
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.grey, custom_id="next_image")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_image = (self.current_image + 1) % len(self.images)
        embed = self.update_embed(self.current_image)
        await interaction.response.edit_message(embed=embed, view=self)
class ImageForwarder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_post_time_path = f"{DATA_PATH}/last_post_time.json"
        self.thread_to_messages_path = f"{DATA_PATH}/thread_to_messages.json"
        self.last_post_time, self.thread_to_messages = self.load_datas()
        self.notified_threads = set()
        self.last_notification_time = {}
        self.recent_messages = {}
        self.thread_locks = {}
        self.bot.add_view(ActionsView(self.thread_to_messages))
    def load_datas(self):
        last_post_time = {}
        thread_to_messages: dict[str, list[int]] = {}
        try:
            with open(self.last_post_time_path, "r") as f:
                last_post_time = json.load(f)
        except FileNotFoundError:
            pass
        try:
            with open(self.thread_to_messages_path, "r") as f:
                thread_to_messages = json.load(f)
        except FileNotFoundError:
            pass
        return last_post_time, thread_to_messages
    def save_datas(self):
        with open(self.last_post_time_path, "w") as f:
            json.dump(self.last_post_time, f)
        with open(self.thread_to_messages_path, "w") as f:
            json.dump(self.thread_to_messages, f)
    def generate_message_hash(self, message: discord.Message):
        content = message.content
        embed_data = []
        for embed in message.embeds:
            embed_dict = embed.to_dict()
            embed_dict.pop('timestamp', None)
            embed_dict.pop('footer', None)
            embed_data.append(json.dumps(embed_dict, sort_keys=True))
        combined = content + ''.join(embed_data)
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.id in {COMMERCES_ID, ACTIVITES_ID}:
                    threads = channel.threads
                    for thread in threads:
                        if not thread.archived and not thread.locked:
                            if str(thread.id) not in self.thread_to_messages:
                                if thread.id not in self.notified_threads:
                                    try:
                                        await thread.send(
                                            "**Info:** This thread doesn't have the new version's UP button.\n"
                                            "Thread posting permissions have changed. "
                                            "Please create a new thread using the channel buttons."
                                        )
                                    except Exception as e:
                                        print(f"Impossible d'envoyer un message dans {thread.id} : {e}")
                                    self.notified_threads.add(thread.id)
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        author = message.author
        channel = message.channel
        if author.bot:
            return
        if channel.type == discord.ChannelType.public_thread:
            await self._validate_thread_tags(channel)
        await self._reject_locked_channel_post(message)
        if channel.type == discord.ChannelType.public_thread and channel.parent_id in {COMMERCES_ID, ACTIVITES_ID}:
            await self.handle_post_logic(message)
        await self._dedup_webhook_repost(message)
    async def _warn_then_delete_thread(self, channel: discord.Thread, warning_msg: str):
        await channel.send(warning_msg)
        await asyncio.sleep(WARN_DELETE_SECONDS)
        try:
            await channel.delete()
        except Exception as e:
            raise Exception(f"Erreur lors de la suppression {channel=} : {e}")
    async def _validate_thread_tags(self, channel: discord.Thread):
        if channel.parent_id == ACTIVITES_ID:
            if len(channel.applied_tags) > 1:
                await self._warn_then_delete_thread(channel, (
                    f"{NO_VALIDE_EMOJI} {channel.owner.mention}, "
                    "too many tags in an Activities thread. Deletion in 5 minutes."
                ))
        if channel.parent_id == COMMERCES_ID:
            trade_tags = {'WTS', 'WTB', 'Sell', 'Buy'}
            thread_tags = {tag.name for tag in channel.applied_tags}
            user_tags = thread_tags - trade_tags
            if len(thread_tags) > MAX_COMMERCE_TOTAL_TAGS:
                await self._warn_then_delete_thread(channel, (
                    f"{NO_VALIDE_EMOJI} {channel.owner.mention}, "
                    f"too many tags. Max {MAX_COMMERCE_USER_TAGS} custom. Deletion in 5 minutes."
                ))
            elif len(user_tags) > MAX_COMMERCE_USER_TAGS:
                await self._warn_then_delete_thread(channel, (
                    f"{NO_VALIDE_EMOJI} {channel.owner.mention}, "
                    f"too many custom tags. Max {MAX_COMMERCE_USER_TAGS}. Deletion in 5 minutes."
                ))
    async def _delete_and_inform(self, message: discord.Message, post_channel_id: int, raid_note: bool = False):
        await message.delete()
        extra = " Raid roles in <id:customize>." if raid_note else ""
        inform_message = (
            f"{NO_VALIDE_EMOJI} {message.author.mention}, "
            f"post via <#{post_channel_id}> using **New Post**.{extra}\n"
            f"{INFO_IMAGE_URL}"
        )
        bot_message = await message.channel.send(inform_message)
        await bot_message.delete(delay=WARN_DELETE_SECONDS)
    async def _reject_locked_channel_post(self, message: discord.Message):
        channel_id = message.channel.id
        if channel_id in LOCKED_CHANNELS_1:
            await self._delete_and_inform(message, COMMERCES_ID)
        if channel_id in LOCKED_CHANNELS_2 and channel_id not in {RAIDS_COSMOS_ID, RAIDS_NOSFIRE_ID}:
            await self._delete_and_inform(message, ACTIVITES_ID)
        if channel_id in {RAIDS_COSMOS_ID, RAIDS_NOSFIRE_ID}:
            await self._delete_and_inform(message, ACTIVITES_ID, raid_note=True)
    async def _dedup_webhook_repost(self, message: discord.Message):
        target_channel_ids = LOCKED_CHANNELS_1.union(LOCKED_CHANNELS_2)
        if message.channel.id not in target_channel_ids or message.webhook_id is None:
            return
        msg_hash = self.generate_message_hash(message)
        current_time = datetime.now()
        self.recent_messages = {
            h: t for h, t in self.recent_messages.items()
            if (current_time - t).total_seconds() < DEDUP_WINDOW_SECONDS
        }
        if msg_hash in self.recent_messages:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                print("Permissions insuffisantes pour supprimer.")
        else:
            self.recent_messages[msg_hash] = current_time
    async def repost_message(
        self,
        msg: discord.Message,
        is_initial_post: bool,
        msg_type: str,
        server: str | None = None,
        selected_raids: list[str] | None = None,
        trade_type: str | None = None,
        activity_type: str | None = None
    ) -> tuple[int, dict[str, list[int]]]:
        thread = msg.channel
        guild = msg.guild
        lock = self.thread_locks.setdefault(thread.id, asyncio.Lock())
        async with lock:
            async for first_message in thread.history(oldest_first=True, limit=1):
                break
            else:
                first_message = msg
            target_channel_id = await get_target_channel_id_and_add_tags(
                thread, msg_type, server, trade_type, activity_type
            )
            trade_type = trade_type or get_trade_type({tag.name for tag in thread.applied_tags})
            if not target_channel_id:
                raise Exception(
                    f"Aucun canal pour {msg_type=} {server=} {activity_type=} {trade_type=}"
                )
            target_channel = guild.get_channel(target_channel_id)
            if not target_channel:
                raise Exception(f"Channel {target_channel_id=} introuvable sur {guild.name}")
            if str(thread.id) in self.thread_to_messages and is_initial_post:
                print(f"Message déjà existant pour {thread.id}, annulation.")
                return target_channel_id, self.thread_to_messages
            action = "🆕" if is_initial_post else "♻️"
            message_content = (
                ", ".join([f"<@&{RAID_ROLE_MAPPING[server].get(raid, '')}>" for raid in selected_raids])
                if selected_raids and msg_type == "raid"
                else ""
            )
            embed = discord.Embed(
                title=f"{action} {thread.mention}",
                description=first_message.content,
                color=discord.Color.blue() if is_initial_post else discord.Color.green(),
            )
            images = [
                attachment.url
                for attachment in first_message.attachments
                if 'image' in (attachment.content_type or "")
            ]
            view = None
            if trade_type == "Vente" and images:
                embed.set_image(url=images[0])
                if len(images) > 1:
                    embed.set_footer(text=f"1 / {len(images)}")
                    view = ImageNavigator(
                        images,
                        title=f"{action} {thread.mention}",
                        description=first_message.content,
                        color=embed.color
                    )
            webhooks = await target_channel.webhooks()
            webhook = discord.utils.find(lambda wh: wh.user == guild.me, webhooks)
            if not webhook:
                webhook = await target_channel.create_webhook(name="ImageForwarder")
            kwargs = {
                "content": message_content,
                "username": msg.author.display_name,
                "avatar_url": msg.author.display_avatar.url,
                "embed": embed,
                "wait": True
            }
            if view is not None:
                kwargs["view"] = view
            sent_msg = await webhook.send(**kwargs)
            self.thread_to_messages.setdefault(str(thread.id), []).append(sent_msg.id)
            self.save_datas()
            return target_channel_id, self.thread_to_messages
    async def handle_post_logic(self, message: discord.Message):
        try:
            thread = message.channel
            author = message.author
            if author.bot or thread.type != discord.ChannelType.public_thread or \
               thread.parent_id not in {COMMERCES_ID, ACTIVITES_ID}:
                return
            if author != thread.owner:
                return
            is_initial_post = (message.id == thread.id)
            current_time = datetime.now(tz=FRA)
            last_post_time = datetime.fromtimestamp(self.last_post_time.get(str(thread.id), 0), tz=FRA)
            timer_hours = None
            thread_tags = {tag.name for tag in thread.applied_tags}
            server = get_server(thread_tags)
            activity_type = get_activity_type(thread_tags)
            trade_type = get_trade_type(thread_tags)
            if thread.parent_id == COMMERCES_ID and trade_type:
                timer_hours = TRADE_CHANNELS.get(f"{trade_type}_{server}", {}).get("timer_hours", 24)
            elif thread.parent_id == ACTIVITES_ID and activity_type:
                timer_hours = ACTIVITY_CHANNELS.get(f"{activity_type}_{server}", {}).get("timer_hours")
            if timer_hours is None:
                timer_hours = 24
            if last_post_time + timedelta(hours=timer_hours) > current_time and not is_initial_post:
                user_thread_key = (author.id, thread.id)
                if user_thread_key not in self.last_notification_time or \
                   (datetime.now() - self.last_notification_time[user_thread_key]).total_seconds() > 300:
                    notification_message = (
                        f"🕒 You'll be able to repost on {discord.utils.format_dt(last_post_time + timedelta(hours=timer_hours), 'f')}.\n"
                        ":warning: This message will be deleted in 5 minutes."
                    )
                    bot_message = await thread.send(content=notification_message, reference=message)
                    await bot_message.delete(delay=300)
                    self.last_notification_time[user_thread_key] = datetime.now()
                return
            if activity_type != "Recherche-raid":
                self.last_post_time[str(thread.id)] = int(current_time.timestamp())
                self.save_datas()
            if thread.parent_id == COMMERCES_ID:
                if is_initial_post:
                    await message.reply(
                        "🔽 Choose your trade type.\n"
                        "🔽 If a button doesn't work, recreate your post.",
                        view=CommerceTypeView(
                            partial(self.repost_message, msg=message, is_initial_post=True, msg_type="commerce"),
                            author_id=author.id,
                            thread=thread
                        )
                    )
                else:
                    await self.repost_message(message, False, "commerce")
            if thread.parent_id == ACTIVITES_ID:
                if not activity_type:
                    return
                if is_initial_post:
                    if activity_type == "Recherche-raid":
                        select_view = RaidSelectView(
                            author_id=author.id,
                            repost_message=partial(
                                self.repost_message,
                                msg=message,
                                is_initial_post=True,
                                msg_type="raid"
                            ),
                            thread=thread,
                            page=0
                        )
                        await message.reply(
                            "🔽 Select your raids.\n"
                            "🔽 If the menu doesn't work, recreate your post.",
                            view=select_view
                        )
                    else:
                        await end_view_chain(
                            thread,
                            partial(self.repost_message, msg=message, is_initial_post=True, msg_type="activité", activity_type=activity_type)
                        )
                else:
                    if activity_type == "Recherche-raid":
                        print(f"Recherche-raid détecté, pas de repost {message.id}")
                        return
                    await self.repost_message(message, False, "activité")
        except Exception as e:
            print(f"Erreur handle_post_logic: {e}")
    async def handle_up_announcement(self, interaction: discord.Interaction, thread: discord.Thread, author: discord.Member):
        first_message = None
        async for msg in thread.history(oldest_first=True, limit=1):
            first_message = msg
        if not first_message:
            await interaction.followup.send("Ad not found.", ephemeral=True)
            return
        thread_tags = {tag.name for tag in thread.applied_tags}
        server = get_server(thread_tags)
        activity_type = get_activity_type(thread_tags)
        trade_type = get_trade_type(thread_tags)
        timer_hours = 24
        if thread.parent_id == COMMERCES_ID and trade_type:
            timer_hours = TRADE_CHANNELS.get(f"{trade_type}_{server}", {}).get("timer_hours", 24)
        elif thread.parent_id == ACTIVITES_ID and activity_type:
            timer_hours = ACTIVITY_CHANNELS.get(f"{activity_type}_{server}", {}).get("timer_hours")
        if activity_type == "Recherche-raid":
            await interaction.followup.send("You can't bump a raid search.", ephemeral=True)
            return
        if timer_hours is None:
            timer_hours = 24
        current_time = datetime.now(tz=FRA)
        last_post_time = datetime.fromtimestamp(self.last_post_time.get(str(thread.id), 0), tz=FRA)
        if last_post_time + timedelta(hours=timer_hours) > current_time:
            user_thread_key = (author.id, thread.id)
            if user_thread_key not in self.last_notification_time or \
               (datetime.now() - self.last_notification_time[user_thread_key]).total_seconds() > 0:
                notification_message = (
                    f"🕒 You'll be able to bump on {discord.utils.format_dt(last_post_time + timedelta(hours=timer_hours), 'f')}."
                )
                await interaction.followup.send(notification_message, ephemeral=True)
                self.last_notification_time[user_thread_key] = datetime.now()
            return
        if activity_type != "Recherche-raid":
            self.last_post_time[str(thread.id)] = int(current_time.timestamp())
            self.save_datas()
        try:
            channel_id, _ = await self.repost_message(
                first_message,
                False,
                "commerce" if thread.parent_id == COMMERCES_ID else "activité"
            )
        except Exception as e:
            print(f"Erreur handle_up_announcement -> repost: {e}")
            await interaction.followup.send("Error while bumping.", ephemeral=True)
            return
        await interaction.followup.send(
            f":white_check_mark: Ad reposted in <#{channel_id}>.",
            ephemeral=False
        )
async def add_tag_to_thread(thread: discord.Thread, tag_name: str):
    if not tag_name:
        return
    candidates = {tag_name, TRADE_TAG_REV.get(tag_name), ACTIVITY_TAG_REV.get(tag_name)}
    candidates.discard(None)
    tag_to_add = discord.utils.find(lambda tag: tag.name in candidates, thread.parent.available_tags)
    if not tag_to_add:
        print(f"{tag_name=} ({candidates}) introuvable dans {thread.parent=}")
        return
    await thread.add_tags(tag_to_add)
def get_trade_type(thread_tags: set[str]):
    for t in thread_tags:
        if t in TRADE_TAG_MAP:
            return TRADE_TAG_MAP[t]
    trade_tags = thread_tags & {"Vente", "Achat"}
    if trade_tags:
        return trade_tags.pop()
    return None
def get_server(thread_tags: set[str]):
    server_tags = thread_tags & {"cosmos", "nosfire"}
    if server_tags:
        return server_tags.pop()
    else:
        return "cosmos"
def get_activity_type(thread_tags: set[str]):
    for t in thread_tags:
        if t in ACTIVITY_TAG_MAP:
            return ACTIVITY_TAG_MAP[t]
    activity_tags = thread_tags & ACTIVITY_TYPES
    if activity_tags:
        return activity_tags.pop()
    return None
async def get_target_channel_id_and_add_tags(
    thread: discord.Thread,
    msg_type: str | None,
    server: str | None,
    trade_type: str | None,
    activity_type: str | None
) -> int | None:
    thread_tags = {tag.name for tag in thread.applied_tags}
    target_channel_id = None
    server = server or get_server(thread_tags)
    trade_type = trade_type or get_trade_type(thread_tags)
    activity_type = activity_type or get_activity_type(thread_tags)
    if trade_type:
        msg_type = msg_type or "commerce"
    if activity_type:
        msg_type = msg_type or "activité"
    msg_type = msg_type or "raid"
    if msg_type == "commerce":
        channel_info = TRADE_CHANNELS.get(f"{trade_type}_{server}")
        if channel_info:
            target_channel_id = channel_info["id"]
        await add_tag_to_thread(thread, trade_type)
    if msg_type == "raid":
        target_channel_id = RAIDS_COSMOS_ID if server == "cosmos" else RAIDS_NOSFIRE_ID
    if msg_type == "activité":
        channel_info = ACTIVITY_CHANNELS.get(f"{activity_type}_{server}")
        if channel_info:
            target_channel_id = channel_info["id"]
        await add_tag_to_thread(thread, activity_type)
    return target_channel_id
async def setup(bot: commands.Bot):
    await bot.add_cog(ImageForwarder(bot))