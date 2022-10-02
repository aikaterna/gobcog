# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import time

from beautifultable import ALIGN_LEFT, BeautifulTable
from redbot.core import commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import bold, box, humanize_number
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character, Item
from .constants import ORDER, RARITIES
from .helpers import _sell, escape, is_dev, smart_embed
from .menus import BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class LootCommands(AdventureMixin):
    """This class will handle Loot interactions"""

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.user)
    async def loot(self, ctx: commands.Context, box_type: str = None, number: int = 1):
        """This opens one of your precious treasure chests.

        Use the box rarity type with the command: normal, rare, epic, legendary, ascended or set.
        """
        if (not is_dev(ctx.author) and number > 100) or number < 1:
            return await smart_embed(ctx, _("Nice try :smirk:."))
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to open a loot chest but then realised you left them all back at the inn."),
            )
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        msgs = []
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if not box_type:
                return await ctx.send(
                    box(
                        _(
                            "{author} owns {normal} normal, "
                            "{rare} rare, {epic} epic, {leg} legendary, {asc} ascended and {set} set chests."
                        ).format(
                            author=escape(ctx.author.display_name),
                            normal=str(c.treasure[0]),
                            rare=str(c.treasure[1]),
                            epic=str(c.treasure[2]),
                            leg=str(c.treasure[3]),
                            asc=str(c.treasure[4]),
                            set=str(c.treasure[5]),
                        ),
                        lang="css",
                    )
                )
            if c.is_backpack_full(is_dev=is_dev(ctx.author)):
                await ctx.send(
                    _("{author}, your backpack is currently full.").format(author=bold(ctx.author.display_name))
                )
                return
            if box_type == "normal":
                redux = 0
            elif box_type == "rare":
                redux = 1
            elif box_type == "epic":
                redux = 2
            elif box_type == "legendary":
                redux = 3
            elif box_type == "ascended":
                redux = 4
            elif box_type == "set":
                redux = 5
            else:
                return await smart_embed(
                    ctx,
                    _("There is talk of a {} treasure chest but nobody ever saw one.").format(box_type),
                )
            treasure = c.treasure[redux]
            if treasure < 1 or treasure < number:
                await smart_embed(
                    ctx,
                    _("{author}, you do not have enough {box} treasure chests to open.").format(
                        author=bold(ctx.author.display_name), box=box_type
                    ),
                )
            else:
                if number > 1:
                    async with ctx.typing():
                        # atomically save reduced loot count then lock again when saving inside
                        # open chests
                        c.treasure[redux] -= number
                        await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                        items = await self._open_chests(ctx, box_type, number, character=c)
                        msg = _("{}, you've opened the following items:\n\n").format(escape(ctx.author.display_name))
                        msg_len = len(msg)
                        table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
                        table.set_style(BeautifulTable.STYLE_RST)
                        msgs = []
                        total = len(items.values())
                        table.columns.header = [
                            "Name",
                            "Slot",
                            "ATT",
                            "CHA",
                            "INT",
                            "DEX",
                            "LUC",
                            "LVL",
                            "QTY",
                            "DEG",
                            "SET",
                        ]
                        async for index, item in AsyncIter(items.values(), steps=100).enumerate(start=1):
                            if len(str(table)) > 1500:
                                table.rows.sort("LVL", reverse=True)
                                msgs.append(box(msg + str(table) + f"\nPage {len(msgs) + 1}", lang="css"))
                                table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
                                table.set_style(BeautifulTable.STYLE_RST)
                                table.columns.header = [
                                    "Name",
                                    "Slot",
                                    "ATT",
                                    "CHA",
                                    "INT",
                                    "DEX",
                                    "LUC",
                                    "LVL",
                                    "QTY",
                                    "DEG",
                                    "SET",
                                ]
                            table.rows.append(
                                (
                                    str(item),
                                    item.slot[0] if len(item.slot) == 1 else "two handed",
                                    item.att,
                                    item.cha,
                                    item.int,
                                    item.dex,
                                    item.luck,
                                    f"[{r}]" if (r := c.equip_level(item)) is not None and r > c.lvl else f"{r}",
                                    item.owned,
                                    f"[{item.degrade}]"
                                    if item.rarity in ["legendary", "event", "ascended"] and item.degrade >= 0
                                    else "N/A",
                                    item.set or "N/A",
                                )
                            )
                            if index == total:
                                table.rows.sort("LVL", reverse=True)
                                msgs.append(box(msg + str(table) + f"\nPage {len(msgs) + 1}", lang="css"))
                else:
                    # atomically save reduced loot count then lock again when saving inside
                    # open chests
                    c.treasure[redux] -= 1
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    await self._open_chest(ctx, ctx.author, box_type, character=c)  # returns item and msg
        if msgs:
            await BaseMenu(
                source=SimpleSource(msgs),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)

    async def _genitem(self, ctx: commands.Context, rarity: str = None, slot: str = None):
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
            return Item.from_json(ctx, {item_name: item_data})

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
            ctx=ctx,
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
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.guild)
    async def convert(self, ctx: commands.Context, box_rarity: str, amount: int = 1):
        """Convert normal, rare or epic chests.

        Trade 25 normal chests for 1 rare chest.
        Trade 25 rare chests for 1 epic chest.
        Trade 25 epic chests for 1 legendary chest.
        """

        # Thanks to flare#0001 for the idea and writing the first instance of this
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _(
                    "You tried to magically combine some of your loot chests "
                    "but the monster ahead is commanding your attention."
                ),
            )
        normalcost = 25
        rarecost = 25
        epiccost = 25
        rebirth_normal = 2
        rebirth_rare = 8
        rebirth_epic = 10
        if amount < 1:
            return await smart_embed(ctx, _("Nice try :smirk:"))
        if amount > 1:
            plural = "s"
        else:
            plural = ""
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return

            if box_rarity.lower() == "rare" and c.rebirths < rebirth_rare:
                return await smart_embed(
                    ctx,
                    ("{user}, you need to have {rebirth} or more rebirths to convert rare treasure chests.").format(
                        user=bold(ctx.author.display_name), rebirth=rebirth_rare
                    ),
                )
            elif box_rarity.lower() == "epic" and c.rebirths < rebirth_epic:
                return await smart_embed(
                    ctx,
                    ("{user}, you need to have {rebirth} or more rebirths to convert epic treasure chests.").format(
                        user=bold(ctx.author.display_name), rebirth=rebirth_epic
                    ),
                )
            elif c.rebirths < 2:
                return await smart_embed(
                    ctx,
                    _("{c}, you need to 3 rebirths to use this.").format(c=bold(ctx.author.display_name)),
                )

            if box_rarity.lower() == "normal" and c.rebirths >= rebirth_normal:
                if c.treasure[0] >= (normalcost * amount):
                    c.treasure[0] -= normalcost * amount
                    c.treasure[1] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} normal treasure "
                                "chests to {to} rare treasure chest{plur}.\n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic, "
                                "{leg} legendary, {asc} ascended and {set} set treasure chests."
                            ).format(
                                converted=humanize_number(normalcost * amount),
                                to=humanize_number(1 * amount),
                                plur=plural,
                                author=escape(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                                asc=c.treasure[4],
                                set=c.treasure[5],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                else:
                    await smart_embed(
                        ctx,
                        _("{author}, you do not have {amount} normal treasure chests to convert.").format(
                            author=bold(ctx.author.display_name),
                            amount=humanize_number(normalcost * amount),
                        ),
                    )
            elif box_rarity.lower() == "rare" and c.rebirths >= rebirth_rare:
                if c.treasure[1] >= (rarecost * amount):
                    c.treasure[1] -= rarecost * amount
                    c.treasure[2] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} rare treasure "
                                "chests to {to} epic treasure chest{plur}. \n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic, "
                                "{leg} legendary, {asc} ascended and {set} set treasure chests."
                            ).format(
                                converted=humanize_number(rarecost * amount),
                                to=humanize_number(1 * amount),
                                plur=plural,
                                author=escape(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                                asc=c.treasure[4],
                                set=c.treasure[5],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                else:
                    await smart_embed(
                        ctx,
                        _("{author}, you do not have {amount} rare treasure chests to convert.").format(
                            author=ctx.author.mention, amount=humanize_number(rarecost * amount)
                        ),
                    )
            elif box_rarity.lower() == "epic" and c.rebirths >= rebirth_epic:
                if c.treasure[2] >= (epiccost * amount):
                    c.treasure[2] -= epiccost * amount
                    c.treasure[3] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} epic treasure "
                                "chests to {to} legendary treasure chest{plur}. \n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic, "
                                "{leg} legendary, {asc} ascended and {set} set treasure chests."
                            ).format(
                                converted=humanize_number(epiccost * amount),
                                to=humanize_number(1 * amount),
                                plur=plural,
                                author=escape(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                                asc=c.treasure[4],
                                set=c.treasure[5],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                else:
                    await smart_embed(
                        ctx,
                        _("{author}, you do not have {amount} epic treasure chests to convert.").format(
                            author=bold(ctx.author.display_name),
                            amount=humanize_number(epiccost * amount),
                        ),
                    )
            else:
                await smart_embed(
                    ctx,
                    _("{user}, please select between normal, rare, or epic treasure chests to convert.").format(
                        user=bold(ctx.author.display_name)
                    ),
                )

    async def _open_chests(
        self,
        ctx: commands.Context,
        chest_type: str,
        amount: int,
        character: Character,
    ):
        items = {}
        async for _loop_counter in AsyncIter(range(0, max(amount, 0)), steps=100):
            item = await self._roll_chest(chest_type, character)
            item_name = str(item)
            if item_name in items:
                items[item_name].owned += 1
            else:
                items[item_name] = item
            await character.add_to_backpack(item)
        await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
        return items

    async def _open_chest(self, ctx: commands.Context, user, chest_type, character):
        if hasattr(user, "display_name"):
            chest_msg = _("{} is opening a treasure chest. What riches lay inside?").format(escape(user.display_name))
        else:
            chest_msg = _("{user}'s {f} is foraging for treasure. What will it find?").format(
                user=escape(ctx.author.display_name), f=(user[:1] + user[1:])
            )
        open_msg = await ctx.send(box(chest_msg, lang="css"))
        await asyncio.sleep(2)
        item = await self._roll_chest(chest_type, character)
        if chest_type == "pet" and not item:
            await open_msg.edit(
                content=box(
                    _("{c_msg}\nThe {user} found nothing of value.").format(
                        c_msg=chest_msg, user=(user[:1] + user[1:])
                    ),
                    lang="css",
                )
            )
            return None
        slot = item.slot[0]
        old_item = getattr(character, item.slot[0], None)
        old_stats = ""

        if old_item:
            old_slot = old_item.slot[0]
            if len(old_item.slot) > 1:
                old_slot = _("two handed")
                att = old_item.att * 2
                cha = old_item.cha * 2
                intel = old_item.int * 2
                luck = old_item.luck * 2
                dex = old_item.dex * 2
            else:
                att = old_item.att
                cha = old_item.cha
                intel = old_item.int
                luck = old_item.luck
                dex = old_item.dex

            old_stats = (
                _("You currently have {item} [{slot}] equipped | Lvl req {lv} equipped.").format(
                    item=old_item, slot=old_slot, lv=character.equip_level(old_item)
                )
                + f" (ATT: {str(att)}, "
                f"CHA: {str(cha)}, "
                f"INT: {str(intel)}, "
                f"DEX: {str(dex)}, "
                f"LUCK: {str(luck)}) "
            )
        if len(item.slot) > 1:
            slot = _("two handed")
            att = item.att * 2
            cha = item.cha * 2
            intel = item.int * 2
            luck = item.luck * 2
            dex = item.dex * 2
        else:
            att = item.att
            cha = item.cha
            intel = item.int
            luck = item.luck
            dex = item.dex
        if hasattr(user, "display_name"):
            chest_msg2 = (
                _("{user} found {item} [{slot}] | Lvl req {lv}.").format(
                    user=escape(user.display_name),
                    item=str(item),
                    slot=slot,
                    lv=character.equip_level(item),
                )
                + f" (ATT: {str(att)}, "
                f"CHA: {str(cha)}, "
                f"INT: {str(intel)}, "
                f"DEX: {str(dex)}, "
                f"LUCK: {str(luck)}) "
            )

            await open_msg.edit(
                content=box(
                    _(
                        "{c_msg}\n\n{c_msg_2}\n\nDo you want to equip "
                        "this item, put in your backpack, or sell this item?\n\n"
                        "{old_stats}"
                    ).format(c_msg=chest_msg, c_msg_2=chest_msg2, old_stats=old_stats),
                    lang="css",
                )
            )
        else:
            chest_msg2 = (
                _("The {user} found {item} [{slot}] | Lvl req {lv}.").format(
                    user=user, item=str(item), slot=slot, lv=character.equip_level(item)
                )
                + f" (ATT: {str(att)}, "
                f"CHA: {str(cha)}, "
                f"INT: {str(intel)}, "
                f"DEX: {str(dex)}, "
                f"LUCK: {str(luck)}), "
            )
            await open_msg.edit(
                content=box(
                    _(
                        "{c_msg}\n{c_msg_2}\nDo you want to equip "
                        "this item, put in your backpack, or sell this item?\n\n{old_stats}"
                    ).format(c_msg=chest_msg, c_msg_2=chest_msg2, old_stats=old_stats),
                    lang="css",
                )
            )

        start_adding_reactions(open_msg, self._treasure_controls.keys())
        if hasattr(user, "id"):
            pred = ReactionPredicate.with_emojis(tuple(self._treasure_controls.keys()), open_msg, user)
        else:
            pred = ReactionPredicate.with_emojis(tuple(self._treasure_controls.keys()), open_msg, ctx.author)
        try:
            react, user = await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await self._clear_react(open_msg)
            await character.add_to_backpack(item)
            await open_msg.edit(
                content=(
                    box(
                        _("{user} put the {item} into their backpack.").format(
                            user=escape(ctx.author.display_name), item=item
                        ),
                        lang="css",
                    )
                )
            )
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
            return
        await self._clear_react(open_msg)
        if self._treasure_controls[react.emoji] == "sell":
            price = _sell(character, item)
            price = max(price, 0)
            if price > 0:
                try:
                    await bank.deposit_credits(ctx.author, price)
                except BalanceTooHigh as e:
                    await bank.set_balance(ctx.author, e.max_balance)
            currency_name = await bank.get_currency_name(
                ctx.guild,
            )
            if str(currency_name).startswith("<"):
                currency_name = "credits"
            await open_msg.edit(
                content=(
                    box(
                        _("{user} sold the {item} for {price} {currency_name}.").format(
                            user=escape(ctx.author.display_name),
                            item=item,
                            price=humanize_number(price),
                            currency_name=currency_name,
                        ),
                        lang="css",
                    )
                )
            )
            await self._clear_react(open_msg)
            character.last_known_currency = await bank.get_balance(ctx.author)
            character.last_currency_check = time.time()
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
        elif self._treasure_controls[react.emoji] == "equip":
            equiplevel = character.equip_level(item)
            if is_dev(ctx.author):
                equiplevel = 0
            if not character.can_equip(item):
                await character.add_to_backpack(item)
                await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
                return await smart_embed(
                    ctx,
                    f"{bold(ctx.author.display_name)}, you need to be level "
                    f"`{equiplevel}` to equip this item. I've put it in your backpack.",
                )
            if not getattr(character, item.slot[0]):
                equip_msg = box(
                    _("{user} equipped {item} ({slot} slot).").format(
                        user=escape(ctx.author.display_name), item=item, slot=slot
                    ),
                    lang="css",
                )
            else:
                equip_msg = box(
                    _("{user} equipped {item} ({slot} slot) and put {old_item} into their backpack.").format(
                        user=escape(ctx.author.display_name),
                        item=item,
                        slot=slot,
                        old_item=getattr(character, item.slot[0]),
                    ),
                    lang="css",
                )
            await open_msg.edit(content=equip_msg)
            character = await character.equip_item(item, False, is_dev(ctx.author))
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
        else:
            await character.add_to_backpack(item)
            await open_msg.edit(
                content=(
                    box(
                        _("{user} put the {item} into their backpack.").format(
                            user=escape(ctx.author.display_name), item=item
                        ),
                        lang="css",
                    )
                )
            )
            await self._clear_react(open_msg)
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
