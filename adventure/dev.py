# -*- coding: utf-8 -*-
import asyncio
import logging
import random
from string import ascii_letters, digits

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_number, pagify

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character, Item
from .constants import DEV_LIST, ORDER, RARITIES
from .helpers import is_dev, smart_embed
from .menus import BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class DevCommands(AdventureMixin):
    """This class will handle dealing with developer only commands"""

    async def no_dev_prompt(self, ctx: commands.Context) -> bool:
        if ctx.author.id in DEV_LIST:
            return True
        confirm_token = "".join(random.choices((*ascii_letters, *digits), k=16))
        await ctx.send(
            "**__You should not be running this command.__** "
            "Any issues that arise from you running this command will not be supported. "
            "If you wish to continue, enter this token as your next message."
            f"\n\n{confirm_token}"
        )
        try:
            message = await ctx.bot.wait_for(
                "message",
                check=lambda m: m.channel.id == ctx.channel.id and m.author.id == ctx.author.id,
                timeout=60,
            )
        except asyncio.TimeoutError:
            await ctx.send(_("Did not get confirmation, cancelling."))
            return False
        else:
            if message.content.strip() == confirm_token:
                return True
            else:
                await ctx.send(_("Did not get a matching confirmation, cancelling."))
                return False

    @commands.command(name="devcooldown")
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def _devcooldown(self, ctx: commands.Context):
        """[Dev] Resets the after-adventure cooldown in this server."""
        if not await self.no_dev_prompt(ctx):
            return
        await self.config.guild(ctx.guild).cooldown.set(0)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def makecart(self, ctx: commands.Context):
        """[Dev] Force a cart to appear."""
        if not await self.no_dev_prompt(ctx):
            return
        await self._trader(ctx, True)

    async def _genitem(self, rarity: str = None, slot: str = None):
        """Generate an item."""
        if rarity == "set":
            items = list(self.TR_GEAR_SET.items())
            items = (
                [
                    i
                    for i in items
                    if i[1]["slot"] == [slot] or (slot == "two handed" and i[1]["slot"] == ["left", "right"])
                ]
                if slot
                else items
            )
            item_name, item_data = random.choice(items)
            return Item.from_json({item_name: item_data}, self.TR_GEAR_SET)

        RARE_INDEX = RARITIES.index("rare")
        EPIC_INDEX = RARITIES.index("epic")
        PREFIX_CHANCE = {"rare": 0.5, "epic": 0.75, "legendary": 0.9, "ascended": 1.0, "set": 0}
        SUFFIX_CHANCE = {"epic": 0.5, "legendary": 0.75, "ascended": 0.5}

        if rarity not in RARITIES:
            rarity = "normal"
        if slot is None:
            slot = random.choice(ORDER)
        name = ""
        stats = {"att": 0, "cha": 0, "int": 0, "dex": 0, "luck": 0}

        def add_stats(word_stats):
            """Add stats in word's dict to local stats dict."""
            for stat in stats.keys():
                if stat in word_stats:
                    stats[stat] += word_stats[stat]

        # only rare and above should have prefix with PREFIX_CHANCE
        if RARITIES.index(rarity) >= RARE_INDEX and random.random() <= PREFIX_CHANCE[rarity]:
            #  log.debug(f"Prefix %: {PREFIX_CHANCE[rarity]}")
            prefix, prefix_stats = random.choice(list(self.PREFIXES.items()))
            name += f"{prefix} "
            add_stats(prefix_stats)

        material, material_stat = random.choice(list(self.MATERIALS[rarity].items()))
        name += f"{material} "
        for stat in stats.keys():
            stats[stat] += material_stat

        equipment, equipment_stats = random.choice(list(self.EQUIPMENT[slot].items()))
        name += f"{equipment}"
        add_stats(equipment_stats)

        # only epic and above should have suffix with SUFFIX_CHANCE
        if RARITIES.index(rarity) >= EPIC_INDEX and random.random() <= SUFFIX_CHANCE[rarity]:
            #  log.debug(f"Suffix %: {SUFFIX_CHANCE[rarity]}")
            suffix, suffix_stats = random.choice(list(self.SUFFIXES.items()))
            of_keyword = "of" if "the" not in suffix_stats else "of the"
            name += f" {of_keyword} {suffix}"
            add_stats(suffix_stats)

        slot_list = [slot] if slot != "two handed" else ["left", "right"]
        return Item(
            name=name,
            slot=slot_list,
            rarity=rarity,
            att=stats["att"],
            int=stats["int"],
            cha=stats["cha"],
            dex=stats["dex"],
            luck=stats["luck"],
            owned=1,
            parts=1,
        )

    @commands.command()
    @commands.is_owner()
    async def genitems(self, ctx: commands.Context, rarity: str, slot: str, num: int = 1):
        """[Dev] Generate random items."""
        if not await self.no_dev_prompt(ctx):
            return
        user = ctx.author
        rarity = rarity.lower()
        slot = slot.lower()
        if rarity not in RARITIES:
            return await smart_embed(
                ctx,
                _("Invalid rarity; choose one of {list}.").format(list=humanize_list(RARITIES)),
            )
        elif slot not in ORDER:
            return await smart_embed(ctx, _("Invalid slot; choose one of {list}.").format(list=humanize_list(ORDER)))
        async with self.get_lock(user):
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            for _loop_counter in range(num):
                await c.add_to_backpack(await self._genitem(rarity, slot))
            await self.config.user(ctx.author).set(await c.to_json(self.config))
        await ctx.invoke(self._backpack)

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def copyuser(self, ctx: commands.Context, user_id: int):
        """[Owner] Copy another members data to yourself.

        Note this overrides your current data.
        """
        user_data = await self.config.user_from_id(user_id).all()
        await self.config.user(ctx.author).set(user_data)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def devrebirth(
        self,
        ctx: commands.Context,
        rebirth_level: int = 1,
        character_level: int = 1,
        users: commands.Greedy[discord.Member] = None,
    ):
        """[Dev] Set multiple users rebirths and level."""
        if not await self.no_dev_prompt(ctx):
            return
        targets = users or [ctx.author]
        if not is_dev(ctx.author):
            if rebirth_level > 100:
                await ctx.send("Rebirth is too high.")
                await ctx.send_help()
                return
            elif character_level > 1000:
                await ctx.send("Level is too high.")
                await ctx.send_help()
                return
        for target in targets:
            async with self.get_lock(target):
                try:
                    c = await Character.from_json(ctx, self.config, target, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                bal = await bank.get_balance(target)
                if bal >= 1000:
                    withdraw = bal - 1000
                    await bank.withdraw_credits(target, withdraw)
                else:
                    withdraw = bal
                    await bank.set_balance(target, 0)
                character_data = await c.rebirth(dev_val=rebirth_level)
                await self.config.user(target).set(character_data)
                await ctx.send(
                    content=box(
                        _("{c}, congratulations on your rebirth.\nYou paid {bal}.").format(
                            c=self.escape(target.display_name), bal=humanize_number(withdraw)
                        ),
                        lang="css",
                    )
                )
            await self._add_rewards(ctx, target, int((character_level) ** 3.5) + 1, 0, False)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def devreset(self, ctx: commands.Context, users: commands.Greedy[discord.Member]):
        """[Dev] Reset the skill cooldown for multiple users."""
        if not await self.no_dev_prompt(ctx):
            return
        targets = users or [ctx.author]
        for target in targets:
            async with self.get_lock(target):
                try:
                    c = await Character.from_json(ctx, self.config, target, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                c.heroclass["ability"] = False
                c.heroclass["cooldown"] = 0
                if "catch_cooldown" in c.heroclass:
                    c.heroclass["catch_cooldown"] = 0
                await self.config.user(target).set(await c.to_json(self.config))
        await ctx.tick()

    @commands.command(name="adventurestats")
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.is_owner()
    async def _adventurestats(self, ctx: commands.Context):
        """[Owner] Show all current adventures."""
        msg = "**Active Adventures**\n"
        embed_list = []

        if len(self._sessions) > 0:
            for server_id, adventure in self._sessions.items():
                stat_range = self._adv_results.get_stat_range(ctx)
                pdef = adventure.monster_modified_stats["pdef"]
                mdef = adventure.monster_modified_stats["mdef"]
                cdef = adventure.monster_modified_stats.get("cdef", 1.0)
                hp = int(
                    adventure.monster_modified_stats["hp"]
                    * self.ATTRIBS[adventure.attribute][0]
                    * adventure.monster_stats
                )
                dipl = int(
                    adventure.monster_modified_stats["dipl"]
                    * self.ATTRIBS[adventure.attribute][1]
                    * adventure.monster_stats
                )
                msg += (
                    f"{self.bot.get_guild(server_id).name} - "
                    f"[{adventure.challenge}]({adventure.message.jump_url})\n"
                    f"[{stat_range['stat_type']}-min:{stat_range['min_stat']}-max:{stat_range['max_stat']}-winratio:{stat_range['win_percent']}] "
                    f"(hp:{hp}-char:{dipl}-pdef:{pdef}-mdef:{mdef}-cdef:{cdef})\n\n"
                )
        else:
            msg += "None."
        for page in pagify(msg, delims=["\n\n"], page_length=1000):
            embed = discord.Embed(description=page)
            embed_list.append(embed)
        await BaseMenu(
            source=SimpleSource(embed_list),
            delete_message_after=True,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)
