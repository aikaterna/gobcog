# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import time
from typing import Optional, Union

import discord
from redbot.core import commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import bold, box, humanize_list, humanize_number

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character, Item
from .constants import Rarities, Slot
from .converters import RarityConverter
from .helpers import LootView, _sell, escape, is_dev, smart_embed
from .menus import BackpackMenu, BackpackSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class LootCommands(AdventureMixin):
    """This class will handle Loot interactions"""

    @commands.hybrid_command(name="loot")
    @commands.bot_has_permissions(add_reactions=True)
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.user)
    async def loot(
        self,
        ctx: commands.Context,
        box_type: Optional[RarityConverter] = None,
        number: int = 1,
    ):
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
        async with ctx.typing():
            async with self.get_lock(ctx.author):
                msgs = []
                try:
                    c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    return
                if box_type is None:
                    chests = c.treasure.ansi
                    return await ctx.send(
                        box(
                            _("{author} owns {chests} chests.").format(
                                author=escape(ctx.author.display_name),
                                chests=chests,
                            ),
                            lang="ansi",
                        )
                    )
                if c.is_backpack_full(is_dev=is_dev(ctx.author)):
                    await ctx.send(
                        _("{author}, your backpack is currently full.").format(author=bold(ctx.author.display_name))
                    )
                    return
                if not box_type.is_chest:
                    return await smart_embed(
                        ctx,
                        _("There is talk of a {} treasure chest but nobody ever saw one.").format(box_type.get_name()),
                    )
                redux = box_type.value
                treasure = c.treasure[redux]
                if treasure < 1 or treasure < number:
                    await smart_embed(
                        ctx,
                        _("{author}, you do not have enough {box} treasure chests to open.").format(
                            author=bold(ctx.author.display_name), box=box_type
                        ),
                    )
                    return
                else:
                    if number > 1:
                        # atomically save reduced loot count then lock again when saving inside
                        # open chests
                        c.treasure[redux] -= number
                        await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                        items = await self._open_chests(ctx, box_type, number, character=c)
                        msg = _("{}, you've opened the following items:\n\n").format(escape(ctx.author.display_name))
                        rows = []
                        async for index, item in AsyncIter(items.values(), steps=100).enumerate(start=1):
                            rows.append(item)
                        tables = await c.make_backpack_tables(rows, msg)
                        for t in tables:
                            msgs.append(t)
                    else:
                        # atomically save reduced loot count then lock again when saving inside
                        # open chests
                        c.treasure[redux] -= 1
                        await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                        await self._open_chest(ctx, ctx.author, box_type, character=c)
                        # returns item and msg
        if msgs:
            await BackpackMenu(
                source=BackpackSource(msgs),
                cog=self,
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
                help_command=self.loot,
            ).start(ctx=ctx)

    async def _genitem(self, ctx: commands.Context, rarity: Optional[Rarities] = None, slot: Optional[Slot] = None):
        """Generate an item."""
        if rarity is Rarities.set:
            items = list(self.TR_GEAR_SET.items())
            items = (
                [
                    i
                    for i in items
                    if i[1]["slot"] == [slot.value] or (slot is Slot.two_handed and len(i[1]["slot"]) > 1)
                ]
                if slot
                else items
            )
            item_name, item_data = random.choice(items)
            return Item.from_json(ctx, {item_name: item_data})

        if rarity is None:
            rarity = Rarities.normal
        if slot is None:
            slot = random.choice([i for i in Slot])
        name = ""
        stats = {"att": 0, "cha": 0, "int": 0, "dex": 0, "luck": 0}

        def add_stats(word_stats):
            """Add stats in word's dict to local stats dict."""
            for stat in stats.keys():
                if stat in word_stats:
                    stats[stat] += word_stats[stat]

        # only rare and above should have prefix with PREFIX_CHANCE
        prefix_chance = rarity.prefix_chance()
        if prefix_chance is not None and random.random() <= prefix_chance:
            #  log.debug(f"Prefix %: {PREFIX_CHANCE[rarity]}")
            prefix, prefix_stats = random.choice(list(self.PREFIXES.items()))
            name += f"{prefix} "
            add_stats(prefix_stats)

        material, material_stat = random.choice(list(self.MATERIALS[rarity.name].items()))
        name += f"{material} "
        for stat in stats.keys():
            stats[stat] += material_stat

        equipment, equipment_stats = random.choice(list(self.EQUIPMENT[slot.value].items()))
        name += f"{equipment}"
        add_stats(equipment_stats)

        suffix_chance = rarity.suffix_chance()
        # only epic and above should have suffix with SUFFIX_CHANCE
        if suffix_chance is not None and random.random() <= suffix_chance:
            #  log.debug(f"Suffix %: {SUFFIX_CHANCE[rarity]}")
            suffix, suffix_stats = random.choice(list(self.SUFFIXES.items()))
            of_keyword = "of" if "the" not in suffix_stats else "of the"
            name += f" {of_keyword} {suffix}"
            add_stats(suffix_stats)

        # slot_list = [slot] if slot != "two handed" else ["left", "right"]
        return Item(
            ctx=ctx,
            name=name,
            slot=slot.to_json(),
            rarity=rarity.name,
            att=stats["att"],
            int=stats["int"],
            cha=stats["cha"],
            dex=stats["dex"],
            luck=stats["luck"],
            owned=1,
            parts=1,
        )

    @commands.hybrid_command(name="convert")
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.guild)
    async def convert(
        self,
        ctx: commands.Context,
        box_rarity: RarityConverter,
        amount: int = 1,
    ):
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
        costs = {
            Rarities.normal: 25,
            Rarities.rare: 25,
            Rarities.epic: 25,
        }
        if box_rarity not in costs.keys():
            await smart_embed(
                ctx,
                _("{user}, please select between {boxes} treasure chests to convert.").format(
                    user=bold(ctx.author.display_name),
                    boxes=humanize_list([i.get_name() for i in costs.keys()]),
                ),
            )
            return

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

            if box_rarity is Rarities.rare and c.rebirths < rebirth_rare:
                return await smart_embed(
                    ctx,
                    ("{user}, you need to have {rebirth} or more rebirths to convert rare treasure chests.").format(
                        user=bold(ctx.author.display_name), rebirth=rebirth_rare
                    ),
                )
            elif box_rarity is Rarities.epic and c.rebirths < rebirth_epic:
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
            msg = ""
            success_msg = _(
                "Successfully converted {converted} treasure "
                "chests to {to} treasure chest{plur}.\n{author} "
                "now owns {chests} treasure chests."
            )
            failed_msg = _("{author}, you do not have {amount} treasure chests to convert.")
            if box_rarity is Rarities.normal and c.rebirths >= rebirth_normal:
                rarity = Rarities.normal
                to_rarity = Rarities.rare
                converted = rarity.rarity_colour.as_str(f"{humanize_number(costs[rarity] * amount)} {rarity}")
                if c.treasure.normal >= (costs[rarity] * amount):
                    c.treasure.normal -= costs[rarity] * amount
                    c.treasure.rare += 1 * amount
                    to = to_rarity.rarity_colour.as_str(f"{humanize_number(1 * amount)} {to_rarity}")
                    msg = success_msg.format(
                        converted=converted,
                        to=to,
                        plur=plural,
                        author=escape(ctx.author.display_name),
                        chests=c.treasure.ansi,
                    )
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                else:
                    msg = failed_msg.format(author=escape(ctx.author.display_name), amount=converted)
            elif box_rarity is Rarities.rare and c.rebirths >= rebirth_rare:
                rarity = Rarities.rare
                to_rarity = Rarities.epic
                converted = rarity.rarity_colour.as_str(f"{humanize_number(costs[rarity] * amount)} {rarity}")
                if c.treasure.rare >= (costs[rarity] * amount):
                    c.treasure.rare -= costs[rarity] * amount
                    c.treasure.epic += 1 * amount
                    to = to_rarity.rarity_colour.as_str(f"{humanize_number(1 * amount)} {to_rarity}")
                    msg = success_msg.format(
                        converted=converted,
                        to=to,
                        plur=plural,
                        author=escape(ctx.author.display_name),
                        chests=c.treasure.ansi,
                    )
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                else:
                    msg = failed_msg.format(author=escape(ctx.author.display_name), amount=converted)
            elif box_rarity is Rarities.epic and c.rebirths >= rebirth_epic:
                rarity = Rarities.epic
                to_rarity = Rarities.legendary
                converted = rarity.rarity_colour.as_str(f"{humanize_number(costs[rarity] * amount)} {rarity}")
                if c.treasure.epic >= (costs[rarity] * amount):
                    c.treasure.epic -= costs[rarity] * amount
                    c.treasure.legendary += 1 * amount
                    to = to_rarity.rarity_colour.as_str(f"{humanize_number(1 * amount)} {to_rarity}")
                    msg = success_msg.format(
                        converted=converted,
                        to=to,
                        plur=plural,
                        author=escape(ctx.author.display_name),
                        chests=c.treasure.ansi,
                    )
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                else:
                    msg = failed_msg.format(author=escape(ctx.author.display_name), amount=converted)
            await ctx.send(box(msg, lang="ansi"))

    async def _open_chests(
        self,
        ctx: commands.Context,
        chest_type: Rarities,
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

    async def _open_chest(self, ctx: commands.Context, user: discord.User, chest_type: Rarities, character: Character):
        pet = character.heroclass.get("pet", {}).get("name", "No Pet?")
        if chest_type is not Rarities.pet:
            chest_msg = _("{} is opening a treasure chest. What riches lay inside?").format(escape(user.display_name))
        else:
            chest_msg = _("{user}'s {pet} is foraging for treasure. What will it find?").format(
                user=escape(ctx.author.display_name), pet=pet
            )
        open_msg = await ctx.send(box(chest_msg, lang="ansi"))
        await asyncio.sleep(2)
        item = await self._roll_chest(chest_type, character)
        if chest_type == "pet" and not item:
            await open_msg.edit(
                content=box(
                    _("{c_msg}\nThe {user} found nothing of value.").format(c_msg=chest_msg, user=pet),
                    lang="ansi",
                )
            )
            return None
        table = item.table(character)
        slot = item.slot
        old_item = getattr(character, item.slot.char_slot, None)
        old_stats = ""

        if old_item:
            old_item_name, old_item_row = old_item.row(character)
            table.rows.append([_("Currently Equipped\n") + old_item_name])
            table.rows.append(old_item_row)
        view = LootView(60, ctx.author)

        old_stats = str(table)
        if chest_type is not Rarities.pet:
            chest_msg2 = _("{user} found {item}.\n").format(user=escape(user.display_name), item=item.ansi)
        else:
            chest_msg2 = _("{user}'s' {pet} found {item}.\n").format(
                user=escape(user.display_name),
                pet=pet,
                item=item.ansi,
            )
        await open_msg.edit(
            content=box(
                _(
                    "{c_msg}\n\n{c_msg_2}\n\nDo you want to equip "
                    "this item, put in your backpack, or sell this item?\n\n"
                    "{old_stats}"
                ).format(c_msg=chest_msg, c_msg_2=chest_msg2, old_stats=old_stats),
                lang="ansi",
            ),
            view=view,
        )
        await view.wait()
        if view.result.value == 0:
            await self._clear_react(open_msg)
            await character.add_to_backpack(item)
            await open_msg.edit(
                content=(
                    box(
                        _("{user} put the {item} into their backpack.\n{item_stats}").format(
                            user=escape(ctx.author.display_name), item=item.as_ansi(), item_stats=item.table(character)
                        ),
                        lang="ansi",
                    )
                ),
                view=None,
            )
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
            return
        await self._clear_react(open_msg)
        if view.result.value == 2:
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
                            item=item.as_ansi(),
                            price=humanize_number(price),
                            currency_name=currency_name,
                        ),
                        lang="ansi",
                    )
                ),
                view=None,
            )
            await self._clear_react(open_msg)
            character.last_known_currency = await bank.get_balance(ctx.author)
            character.last_currency_check = time.time()
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
        elif view.result.value == 1:
            equiplevel = character.equip_level(item)
            if is_dev(ctx.author):
                equiplevel = 0
            if not character.can_equip(item):
                await character.add_to_backpack(item)
                await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
                return await smart_embed(
                    ctx=ctx,
                    message=_(
                        "{user}, you need to be level "
                        "`{equiplevel}` to equip this item. I've put it in your backpack."
                    ).format(user=bold(ctx.author.display_name), equiplevel=equiplevel),
                )
            if not getattr(character, item.slot.char_slot):
                equip_msg = _("{user} equipped {item} ({slot} slot).").format(
                    user=escape(ctx.author.display_name), item=item.as_ansi(), slot=slot
                )
            else:
                equip_msg = _("{user} equipped {item} ({slot} slot) and put {old_item} into their backpack.").format(
                    user=escape(ctx.author.display_name),
                    item=item,
                    slot=slot,
                    old_item=getattr(character, item.slot.char_slot).as_ansi(),
                )
            equip_msg += f".\n{item.table(character)}"
            await open_msg.edit(content=box(equip_msg, lang="ansi"), view=None)
            character = await character.equip_item(item, False, is_dev(ctx.author))
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
