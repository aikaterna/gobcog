# -*- coding: utf-8 -*-
import asyncio
import logging

from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, box
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .abc import AdventureMixin
from .charsheet import Character, Item
from .helpers import escape, smart_embed
from .menus import BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class LoadoutCommands(AdventureMixin):
    """This class will handle setting and using loadouts"""

    @commands.group(aliases=["loadouts"])
    async def loadout(self, ctx: commands.Context):
        """Set up gear sets or loadouts."""

    @loadout.command(name="save", aliases=["update"])
    async def save_loadout(self, ctx: commands.Context, name: str):
        """Save your current equipment as a loadout."""
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        name = name.lower()
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if name in c.loadouts:
                msg = await ctx.send("Are you sure you want to update your existing loadout: `{}`?".format(name))
                start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(msg, ctx.author)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                except asyncio.TimeoutError:
                    await self._clear_react(msg)
                    return

                if not pred.result:
                    await ctx.send("I will not updated loadout: `{}`.".format(name))
                    return
            loadout = await Character.save_loadout(c)
            c.loadouts[name] = loadout
            await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
            await smart_embed(
                ctx,
                _("{author}, your current equipment has been saved to {name}.").format(
                    author=bold(ctx.author.display_name), name=name
                ),
            )

    @loadout.command(name="delete", aliases=["del", "rem", "remove"])
    async def remove_loadout(self, ctx: commands.Context, name: str):
        """Delete a saved loadout."""
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        async with self.get_lock(ctx.author):
            name = name.lower()
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if name not in c.loadouts:
                await smart_embed(
                    ctx,
                    _("{author}, you don't have a loadout named {name}.").format(
                        author=bold(ctx.author.display_name), name=name
                    ),
                )
            else:
                del c.loadouts[name]
                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                await smart_embed(
                    ctx,
                    _("{author}, loadout {name} has been deleted.").format(
                        author=bold(ctx.author.display_name), name=name
                    ),
                )

    @loadout.command(name="show")
    @commands.bot_has_permissions(add_reactions=True)
    async def show_loadout(self, ctx: commands.Context, name: str = None):
        """Show saved loadouts."""
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        try:
            c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            return
        if not c.loadouts:
            return await smart_embed(
                ctx,
                _("{author}, you don't have any loadouts saved.").format(author=bold(ctx.author.display_name)),
            )
        if name is not None and name.lower() not in c.loadouts:
            return await smart_embed(
                ctx,
                _("{author}, you don't have a loadout named {name}.").format(
                    author=bold(ctx.author.display_name), name=name
                ),
            )
        else:
            msg_list = []
            index = 0
            count = 0
            for (l_name, loadout) in c.loadouts.items():
                if name and name.lower() == l_name:
                    index = count
                items = [Item.from_json(ctx, raw_item) for raw_item in loadout.values() if raw_item]

                title = _("{name} Loadout for {author}").format(name=l_name, author=escape(ctx.author.display_name))
                stats = await c.make_backpack_tables(items, title=title, include_total=True)
                msg_list.extend([str(table) for table in stats])
                count += 1
            if msg_list:
                await BaseMenu(
                    source=SimpleSource(msg_list),
                    delete_message_after=True,
                    clear_reactions_after=True,
                    timeout=60,
                ).start(ctx=ctx, page=index)

    @loadout.command(name="equip", aliases=["load"], cooldown_after_parsing=True)
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def equip_loadout(self, ctx: commands.Context, name: str):
        """Equip a saved loadout."""
        if self.in_adventure(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("You tried to magically equip multiple items at once, but the monster ahead nearly killed you."),
            )
        if not await self.allow_in_dm(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        name = name.lower()
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                ctx.command.reset_cooldown(ctx)
                return
            if name not in c.loadouts:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(
                    ctx,
                    _("{author}, you don't have a loadout named {name}.").format(
                        author=bold(ctx.author.display_name), name=name
                    ),
                )
            else:
                c = await c.equip_loadout(name)
                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                try:
                    c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    ctx.command.reset_cooldown(ctx)
                    return
                current_stats = box(
                    _(
                        "{author}'s new stats: "
                        "Attack: {stat_att} [{skill_att}], "
                        "Intelligence: {stat_int} [{skill_int}], "
                        "Diplomacy: {stat_cha} [{skill_cha}], "
                        "Dexterity: {stat_dex}, "
                        "Luck: {stat_luck}."
                    ).format(
                        author=escape(ctx.author.display_name),
                        stat_att=c.get_stat_value("att")[0],
                        skill_att=c.skill["att"],
                        stat_int=c.get_stat_value("int")[0],
                        skill_int=c.skill["int"],
                        stat_cha=c.get_stat_value("cha")[0],
                        skill_cha=c.skill["cha"],
                        stat_dex=c.get_stat_value("dex")[0],
                        stat_luck=c.get_stat_value("luck")[0],
                    ),
                    lang="ansi",
                )
                await ctx.send(current_stats)
