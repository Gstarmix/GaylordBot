import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from constants import GATE_FORUM_IDS
from extensions.gemini_helper import suggest_title
from extensions import site_api
from extensions.forum_helpers import first_post_is_webhook, post_log, auto_tag_thread, access_buttons_view
from extensions.forum_i18n import t, code_for
WATCHED_FORUMS = GATE_FORUM_IDS
COUNTDOWN_SECONDS = 60
TICK_SECONDS = 10
_REFORM_DELAYS = [120, 600, 1800, 86400, 86400, 86400]
_REFORM_PENDING_PATH = Path(__file__).resolve().parent.parent / "forum_reformulation_pending.json"
_AUTOTAG_DELAYS = _REFORM_DELAYS
_AUTOTAG_PENDING_PATH = Path(__file__).resolve().parent.parent / "forum_autotag_pending.json"
_FORUM_DAILY_LIMIT = int(os.environ.get("GSTAR_DAILY_FORUM_LIMIT", "2"))
_DAILY_THREADS_PATH = Path(__file__).resolve().parent.parent / "forum_daily_threads.json"
def _title_errors(question_cog, title: str, applied_tags) -> list:
    errors = question_cog.get_question_error(title, applied_tags) or []
    return [e for e in errors if "tag" not in e.lower()]
class ApplyTitleView(discord.ui.View):
    def __init__(self, thread: discord.Thread, suggested: str, author_id: int):
        super().__init__(timeout=COUNTDOWN_SECONDS + 30)
        self.thread = thread
        self.suggested = suggested
        self.author_id = author_id
        member = thread.guild.get_member(author_id) if getattr(thread, "guild", None) else None
        self.children[0].label = t("usethis_button", code_for(member))
    @discord.ui.button(label="Use this title", style=discord.ButtonStyle.green, emoji="✨")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                t("usethis_notauthor", code_for(interaction.user)), ephemeral=True
            )
            return
        try:
            await self.thread.edit(name=self.suggested)
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"Could not rename the thread ({exc}).", ephemeral=True
            )
            return
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(t("usethis_applied", code_for(interaction.user)), ephemeral=True)
        self.stop()
class QuestionGate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locked: set[int] = set()
        self._tasks: dict[int, asyncio.Task] = {}
        self._timer_msg: dict[int, int] = {}
        self._authors: dict[int, int] = {}
        self._reconciled = False
        self._reconcile_task: asyncio.Task | None = None
        self._reform_pending: dict[str, int] = {}
        self._reform_tasks: dict[int, asyncio.Task] = {}
        self._autotag_pending: dict[str, int] = {}
        self._autotag_tasks: dict[int, asyncio.Task] = {}
        self._daily_threads: dict[str, dict] = self._load_daily_threads()
        self._bg_tasks: set[asyncio.Task] = set()
    async def cog_load(self):
        self._reconcile_task = asyncio.create_task(self._reconcile_on_boot())
        self._reform_pending = self._load_reform_pending()
        for tid_str in list(self._reform_pending.keys()):
            try:
                tid = int(tid_str)
            except (TypeError, ValueError):
                continue
            self._reform_tasks[tid] = asyncio.create_task(self._reformulation_retry_loop(tid))
        self._autotag_pending = self._load_autotag_pending()
        for tid_str in list(self._autotag_pending.keys()):
            try:
                tid = int(tid_str)
            except (TypeError, ValueError):
                continue
            self._autotag_tasks[tid] = asyncio.create_task(self._autotag_retry_loop(tid))
    async def cog_unload(self):
        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()
        for task in list(self._reform_tasks.values()):
            if not task.done():
                task.cancel()
        self._reform_tasks.clear()
        for task in list(self._autotag_tasks.values()):
            if not task.done():
                task.cancel()
        self._autotag_tasks.clear()
        for task in list(self._bg_tasks):
            if not task.done():
                task.cancel()
        self._bg_tasks.clear()
    def _qcog(self):
        return self.bot.get_cog("Question")
    async def _reconcile_on_boot(self):
        await self.bot.wait_until_ready()
        await self._reconcile_submenu()
    @commands.Cog.listener()
    async def on_ready(self):
        await self._reconcile_submenu()
    async def _reconcile_submenu(self):
        if self._reconciled:
            return
        self._reconciled = True
        try:
            ids = await site_api.get_submenu_thread_ids()
        except Exception as exc:
            print(f"[gate] réconciliation: get ids échoué ({exc!r})", flush=True)
            return
        for tid in ids:
            try:
                await self.bot.fetch_channel(tid)
            except discord.NotFound:
                print(f"[gate] réconciliation: thread {tid} supprimé -> notif site", flush=True)
                asyncio.create_task(site_api.notify_thread_deleted(tid))
            except discord.HTTPException:
                pass
    async def _first_message_content(self, thread: discord.Thread) -> str:
        for _ in range(3):
            async for msg in thread.history(limit=1, oldest_first=True):
                return msg.content or ""
            await asyncio.sleep(1)
        return ""
    def _timer_embed(self, remaining: int, code: str = "en") -> discord.Embed:
        if remaining > 0:
            return discord.Embed(
                title=t("tofix_title", code),
                description=t("tofix_desc", code, remaining=remaining),
                color=discord.Color.orange(),
            )
        return discord.Embed(
            title=t("timeup_title", code),
            description=t("timeup_desc", code),
            color=discord.Color.red(),
        )
    def _thread_code(self, thread: discord.Thread) -> str:
        member = None
        if getattr(thread, "guild", None) is not None and thread.owner_id:
            member = thread.guild.get_member(thread.owner_id)
        return code_for(member)
    def _cleanup(self, tid: int):
        self._locked.discard(tid)
        task = self._tasks.pop(tid, None)
        if task and not task.done():
            task.cancel()
        self._timer_msg.pop(tid, None)
        self._authors.pop(tid, None)
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.parent_id not in WATCHED_FORUMS:
            return
        if await first_post_is_webhook(thread):
            return
        question_cog = self._qcog()
        if question_cog is None:
            print("[gate] skip: cog 'Question' introuvable", flush=True)
            return
        original = thread.name or ""
        original_ok = not _title_errors(question_cog, original, thread.applied_tags)
        owner_id = thread.owner_id or 0
        if self._over_daily_thread_limit(owner_id):
            print(f"[gate] limite quotidienne de sujets atteinte pour {owner_id} -> suppression", flush=True)
            self._authors[thread.id] = owner_id
            await self._delete_thread(thread, reason="daily_limit", author_id=owner_id)
            return
        content = await self._first_message_content(thread)
        try:
            nostale = await site_api.check_topic(original, content)
        except Exception as exc:
            print(f"[gate] check_topic erreur ({exc!r}) -> on garde", flush=True)
            nostale = True
        if not nostale:
            print(f"[gate] hors-sujet NosTale -> suppression + MP: {original!r}", flush=True)
            self._authors[thread.id] = thread.owner_id or 0
            await self._delete_thread(thread, reason="offtopic")
            return
        _tag_task = asyncio.create_task(auto_tag_thread(thread, original, content, bot=self.bot))
        self._bg_tasks.add(_tag_task)
        _tag_task.add_done_callback(self._bg_tasks.discard)
        suggested = await suggest_title(original, content, lang=self._thread_code(thread))
        if suggested is None:
            print(f"[gate] reformulation indispo -> retry programmé, fil laissé ouvert: {original!r}", flush=True)
            self._schedule_reformulation_retry(thread.id)
            self._watch_tag_task(thread, _tag_task)
            return
        if not _title_errors(question_cog, suggested, thread.applied_tags):
            if suggested.strip().lower() != original.strip().lower():
                await self._apply_reformulation(thread, original, suggested)
            else:
                await self._confirm_title_already_ok(thread, original)
            await self._post_tags_embed_when_ready(thread, _tag_task)
            return
        if original_ok:
            print(f"[gate] titre déjà conforme: {original!r}", flush=True)
            self._watch_tag_task(thread, _tag_task)
            return
        self._watch_tag_task(thread, _tag_task)
        print(f"[gate] reformulation invalide + titre KO -> verrou + chrono: {original!r}", flush=True)
        self._locked.add(thread.id)
        self._authors[thread.id] = thread.owner_id or 0
        mention = f"<@{self._authors[thread.id]}>"
        try:
            timer = await thread.send(content=mention, embed=self._timer_embed(COUNTDOWN_SECONDS, self._thread_code(thread)))
            self._timer_msg[thread.id] = timer.id
        except discord.HTTPException as exc:
            print(f"[gate] échec envoi chrono: {exc!r}", flush=True)
        self._tasks[thread.id] = asyncio.create_task(self._tick(thread))
    async def _apply_reformulation(self, thread: discord.Thread, original: str, suggested: str) -> bool:
        try:
            await thread.edit(name=suggested)
            owner_id = thread.owner_id or 0
            code = self._thread_code(thread)
            await thread.send(
                content=(f"<@{owner_id}>" if owner_id else None),
                embed=discord.Embed(
                    title=t("rephrased_title", code),
                    description=t("rephrased_desc", code, original=original, suggested=suggested),
                    color=discord.Color.green(),
                ),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            print(f"[gate] titre reformulé auto: {original!r} -> {suggested!r}", flush=True)
            asyncio.create_task(site_api.set_thread_title(thread.id, suggested))
            return True
        except discord.HTTPException as exc:
            print(f"[gate] échec rename auto ({exc!r})", flush=True)
            return False
    async def _post_tags_embed_when_ready(self, thread: discord.Thread, tag_task) -> None:
        try:
            applied = await tag_task
        except Exception:
            applied = None
        if applied is None:
            print(f"[gate] auto-tag indispo -> retry programmé, thread {thread.id}", flush=True)
            self._schedule_autotag_retry(thread.id)
            return
        if not applied:
            return
        await self._send_tags_embed(thread, applied)
    async def _send_tags_embed(self, thread: discord.Thread, applied: list) -> None:
        try:
            code = self._thread_code(thread)
            await thread.send(embed=discord.Embed(
                title=t("tagsadded_title", code),
                description=(
                    t("tagsadded_intro", code)
                    + " + ".join(f"`{tag}`" for tag in applied)
                ),
                color=discord.Color.green(),
            ))
        except discord.HTTPException as exc:
            print(f"[gate] embed tags non posté thread {thread.id} : {exc!r}", flush=True)
    async def _confirm_title_already_ok(self, thread: discord.Thread, original: str):
        owner_id = thread.owner_id or 0
        code = self._thread_code(thread)
        try:
            await thread.send(
                content=(f"<@{owner_id}>" if owner_id else None),
                embed=discord.Embed(
                    title=t("alreadyclear_title", code),
                    description=t("alreadyclear_desc", code),
                    color=discord.Color.green(),
                ),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            print(f"[gate] titre déjà conforme (confirmé): {original!r}", flush=True)
        except discord.HTTPException as exc:
            print(f"[gate] échec confirmation titre ({exc!r})", flush=True)
    def _load_reform_pending(self) -> dict:
        try:
            data = json.loads(_REFORM_PENDING_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    def _save_reform_pending(self) -> None:
        try:
            _REFORM_PENDING_PATH.write_text(json.dumps(self._reform_pending), encoding="utf-8")
        except OSError as exc:
            print(f"[gate] échec sauvegarde reform_pending : {exc!r}", flush=True)
    def _watch_tag_task(self, thread: discord.Thread, tag_task) -> None:
        watcher = asyncio.create_task(self._post_tags_embed_when_ready(thread, tag_task))
        self._bg_tasks.add(watcher)
        watcher.add_done_callback(self._bg_tasks.discard)
    def _load_autotag_pending(self) -> dict:
        try:
            data = json.loads(_AUTOTAG_PENDING_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    def _save_autotag_pending(self) -> None:
        try:
            _AUTOTAG_PENDING_PATH.write_text(json.dumps(self._autotag_pending), encoding="utf-8")
        except OSError as exc:
            print(f"[gate] échec sauvegarde autotag_pending : {exc!r}", flush=True)
    def _schedule_autotag_retry(self, thread_id: int) -> None:
        tid = int(thread_id)
        if tid in self._autotag_tasks:
            return
        self._autotag_pending[str(tid)] = self._autotag_pending.get(str(tid), 0)
        self._save_autotag_pending()
        self._autotag_tasks[tid] = asyncio.create_task(self._autotag_retry_loop(tid))
    def _forget_autotag_pending(self, thread_id: int) -> None:
        self._autotag_tasks.pop(int(thread_id), None)
        if self._autotag_pending.pop(str(int(thread_id)), None) is not None:
            self._save_autotag_pending()
    async def _autotag_retry_loop(self, thread_id: int):
        try:
            while True:
                attempts = self._autotag_pending.get(str(thread_id), 0)
                if attempts >= len(_AUTOTAG_DELAYS):
                    print(f"[gate] auto-tag abandonné après {attempts} tentatives, thread {thread_id}", flush=True)
                    self._forget_autotag_pending(thread_id)
                    return
                await asyncio.sleep(_AUTOTAG_DELAYS[attempts])
                thread = await self._get_thread(thread_id)
                if thread is None:
                    self._forget_autotag_pending(thread_id)
                    return
                content = await self._first_message_content(thread)
                applied = await auto_tag_thread(thread, thread.name or "", content, bot=self.bot)
                if applied is None:
                    self._autotag_pending[str(thread_id)] = attempts + 1
                    self._save_autotag_pending()
                    continue
                if applied:
                    await self._send_tags_embed(thread, applied)
                self._forget_autotag_pending(thread_id)
                return
        except asyncio.CancelledError:
            return
        finally:
            self._autotag_tasks.pop(thread_id, None)
    def _load_daily_threads(self) -> dict:
        try:
            data = json.loads(_DAILY_THREADS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    def _over_daily_thread_limit(self, user_id: int) -> bool:
        if not user_id:
            return False
        today = datetime.now(timezone.utc).date().isoformat()
        rec = self._daily_threads.get(str(user_id))
        if not isinstance(rec, dict) or rec.get("date") != today:
            rec = {"date": today, "count": 0}
        rec["count"] = int(rec.get("count", 0)) + 1
        self._daily_threads[str(user_id)] = rec
        try:
            _DAILY_THREADS_PATH.write_text(json.dumps(self._daily_threads), encoding="utf-8")
        except OSError:
            pass
        return rec["count"] > _FORUM_DAILY_LIMIT
    @commands.hybrid_command(
        name="limite_reset", aliases=["limitereset", "resetlimite"],
        description="Remet à zéro la limite quotidienne de sujets #questions d'un joueur.",
    )
    @app_commands.describe(utilisateur="Joueur dont remettre à zéro le compteur de sujets du jour (ID accepté en préfixe)")
    @commands.has_permissions(manage_guild=True)
    async def limite_reset(self, ctx: commands.Context, utilisateur: discord.User = None):
        if utilisateur is None:
            await ctx.send(
                "Usage : `limite_reset @utilisateur` — remet à zéro son compteur de "
                f"sujets #questions du jour (limite : {_FORUM_DAILY_LIMIT}/jour).",
                ephemeral=True,
            )
            return
        rec = self._daily_threads.pop(str(utilisateur.id), None)
        try:
            _DAILY_THREADS_PATH.write_text(json.dumps(self._daily_threads), encoding="utf-8")
        except OSError:
            pass
        today = datetime.now(timezone.utc).date().isoformat()
        count = int(rec.get("count", 0)) if isinstance(rec, dict) and rec.get("date") == today else 0
        if count:
            await ctx.send(
                f"✅ Compteur de sujets du jour de {utilisateur.mention} remis à zéro "
                f"(il était à {count}, limite {_FORUM_DAILY_LIMIT}/jour). "
                f"Il peut reposter dès maintenant.",
                ephemeral=True,
            )
        else:
            await ctx.send(
                f"{utilisateur.mention} n'avait aucun sujet compté aujourd'hui "
                f"(rien à réinitialiser, limite {_FORUM_DAILY_LIMIT}/jour).",
                ephemeral=True,
            )
    @limite_reset.error
    async def limite_reset_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Commande réservée aux gestionnaires du serveur.", ephemeral=True)
        elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound, commands.BadArgument)):
            await ctx.send("Utilisateur introuvable. Usage : `limite_reset @utilisateur` (ou `limite_reset <id>`).",
                           ephemeral=True)
    def _schedule_reformulation_retry(self, thread_id: int) -> None:
        tid = int(thread_id)
        if tid in self._reform_tasks:
            return
        self._reform_pending[str(tid)] = self._reform_pending.get(str(tid), 0)
        self._save_reform_pending()
        self._reform_tasks[tid] = asyncio.create_task(self._reformulation_retry_loop(tid))
    def _forget_reform_pending(self, thread_id: int) -> None:
        self._reform_tasks.pop(int(thread_id), None)
        if self._reform_pending.pop(str(int(thread_id)), None) is not None:
            self._save_reform_pending()
    async def _get_thread(self, thread_id: int):
        ch = self.bot.get_channel(thread_id)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(thread_id)
            except discord.HTTPException:
                return None
        return ch if isinstance(ch, discord.Thread) else None
    async def _reformulation_retry_loop(self, thread_id: int):
        try:
            while True:
                attempts = self._reform_pending.get(str(thread_id), 0)
                if attempts >= len(_REFORM_DELAYS):
                    print(f"[gate] reformulation abandonnée après {attempts} tentatives, thread {thread_id}", flush=True)
                    self._forget_reform_pending(thread_id)
                    return
                await asyncio.sleep(_REFORM_DELAYS[attempts])
                thread = await self._get_thread(thread_id)
                if thread is None:
                    self._forget_reform_pending(thread_id)
                    return
                original = thread.name or ""
                qcog = self._qcog()
                if qcog is not None and not _title_errors(qcog, original, thread.applied_tags):
                    self._forget_reform_pending(thread_id)
                    return
                content = await self._first_message_content(thread)
                suggested = await suggest_title(original, content, lang=self._thread_code(thread))
                if (suggested and qcog is not None
                        and not _title_errors(qcog, suggested, thread.applied_tags)
                        and suggested.strip().lower() != original.strip().lower()):
                    await self._apply_reformulation(thread, original, suggested)
                    self._forget_reform_pending(thread_id)
                    return
                self._reform_pending[str(thread_id)] = attempts + 1
                self._save_reform_pending()
        except asyncio.CancelledError:
            return
        finally:
            self._reform_tasks.pop(thread_id, None)
    async def _tick(self, thread: discord.Thread):
        remaining = COUNTDOWN_SECONDS
        if thread.id not in self._timer_msg:
            return
        try:
            while remaining > 0:
                await asyncio.sleep(min(TICK_SECONDS, remaining))
                if thread.id not in self._locked:
                    return
                remaining = max(0, remaining - TICK_SECONDS)
                try:
                    m = await thread.fetch_message(self._timer_msg[thread.id])
                    await m.edit(embed=self._timer_embed(remaining, self._thread_code(thread)))
                except discord.HTTPException:
                    pass
            if thread.id in self._locked:
                await self._delete_thread(thread)
        except asyncio.CancelledError:
            return
    async def _delete_thread(self, thread: discord.Thread, reason: str = "timeout", author_id: int | None = None):
        if author_id is None:
            author_id = self._authors.get(thread.id)
        content = await self._first_message_content(thread)
        title = thread.name
        self._cleanup(thread.id)
        if author_id:
            try:
                user = self.bot.get_user(author_id) or await self.bot.fetch_user(author_id)
                if user:
                    member = thread.guild.get_member(author_id) if getattr(thread, "guild", None) else None
                    code = code_for(member)
                    ec = content or t("empty", code)
                    if reason == "offtopic":
                        dm = t("dm_offtopic", code, title=title, content=ec)
                    elif reason == "no_visit":
                        dm = t("dm_no_visit", code, title=title, content=ec)
                    elif reason == "daily_limit":
                        dm = t("dm_daily_limit", code, title=title, content=ec, limit=_FORUM_DAILY_LIMIT)
                    else:
                        dm = t("dm_title_timeout", code, title=title, content=ec)
                    if reason == "daily_limit":
                        await user.send(dm, view=access_buttons_view(include_salon=False))
                    elif reason == "no_visit":
                        await user.send(dm, view=access_buttons_view())
                    else:
                        await user.send(dm)
            except discord.HTTPException:
                pass
        try:
            await thread.delete()
            print(f"[gate] thread {thread.id} supprimé ({reason})", flush=True)
            _reasons = {
                "offtopic": "hors-sujet NosTale", "no_visit": "pas de visite du site",
                "daily_limit": "limite quotidienne de sujets", "timeout": "titre non corrigé à temps",
            }
            await post_log(self.bot, f"🗑️ Sujet **{title}** supprimé ({_reasons.get(reason, reason)}).")
        except discord.HTTPException as exc:
            print(f"[gate] échec suppression thread: {exc!r}", flush=True)
    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        if payload.parent_id not in WATCHED_FORUMS:
            return
        self._cleanup(payload.thread_id)
        asyncio.create_task(site_api.notify_thread_deleted(payload.thread_id))
        print(f"[gate] thread {payload.thread_id} supprimé -> notif site", flush=True)
    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        if after.id not in self._locked:
            return
        question_cog = self._qcog()
        if question_cog is None:
            return
        if _title_errors(question_cog, after.name, after.applied_tags):
            return
        print(f"[gate] titre corrigé -> déverrouillage: {after.name!r}", flush=True)
        timer_mid = self._timer_msg.get(after.id)
        self._cleanup(after.id)
        if timer_mid:
            try:
                m = await after.fetch_message(timer_mid)
                await m.edit(embed=discord.Embed(
                    title="Titre validé ✅",
                    description="Le fil est maintenant ouvert à tous.",
                    color=discord.Color.green(),
                ))
            except discord.HTTPException:
                pass
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        channel = message.channel
        if not isinstance(channel, discord.Thread):
            return
        if channel.id not in self._locked:
            return
        if message.author.bot or message.is_system():
            return
        if message.id == channel.id:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        try:
            await message.author.send(
                f"Tu pourras écrire dans ce fil une fois le titre corrigé : {channel.jump_url}"
            )
        except discord.HTTPException:
            pass
async def setup(bot: commands.Bot):
    await bot.add_cog(QuestionGate(bot))