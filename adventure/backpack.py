# -*- coding: utf-8 -*-
import asyncio
import contextlib
import logging
import random
import time
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import bold, box, humanize_list, humanize_number, pagify
from redbot.core.utils.menus import menu, start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character, Item
from .constants import ORDER, RARITIES
from .converters import (
    BackpackFilterParser,
    EquipableItemConverter,
    ItemConverter,
    ItemsConverter,
    RarityConverter,
    SlotConverter,
)
from .helpers import _sell, escape, is_dev, smart_embed
from .menus import BackpackMenu, BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class BackPackCommands(AdventureMixin):
    """This class will handle interacting with adventures backpack"""

    @commands.group(name="backpack", autohelp=False)
    @commands.bot_has_permissions(add_reactions=True)
    async def _backpack(
        self,
        ctx: commands.Context,
        show_diff: Optional[bool] = False,
        rarity: Optional[RarityConverter] = None,
        *,
        slot: Optional[SlotConverter] = None,
    ):
        """This shows the contents of your backpack.

        Give it a rarity and/or slot to filter what backpack items to show.

        Selling:     `[p]backpack sell item_name`
        Trading:     `[p]backpack trade @user price item_name`
        Equip:       `[p]backpack equip item_name`
        Sell All:    `[p]backpack sellall rarity slot`
        Disassemble: `[p]backpack disassemble item_name`

        Note: An item **degrade** level is how many rebirths it will last, before it is broken down.
        """
        assert isinstance(rarity, str) or rarity is None
        assert isinstance(slot, str) or slot is None
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        if not ctx.invoked_subcommand:
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if rarity:
                rarity = rarity.lower()
                if rarity not in RARITIES:
                    return await smart_embed(
                        ctx,
                        _("{} is not a valid rarity, select one of {}").format(rarity, humanize_list(RARITIES)),
                    )
            if slot:
                slot = slot.lower()
                if slot not in ORDER:
                    return await smart_embed(
                        ctx,
                        _("{} is not a valid slot, select one of {}").format(slot, humanize_list(ORDER)),
                    )

            msgs = await c.get_backpack(rarity=rarity, slot=slot, show_delta=show_diff)
            if not msgs:
                return await smart_embed(
                    ctx,
                    _("You have no items in your backpack."),
                )
            await BackpackMenu(
                source=SimpleSource(msgs),
                help_command=self._backpack,
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)

    @_backpack.command(name="equip")
    async def backpack_equip(self, ctx: commands.Context, *, equip_item: EquipableItemConverter):
        """Equip an item from your backpack."""
        assert isinstance(equip_item, Item)
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to equip an item but the monster ahead of you commands your attention."),
            )
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            equiplevel = c.equip_level(equip_item)
            if is_dev(ctx.author):  # FIXME:
                equiplevel = 0

            if not c.can_equip(equip_item):
                return await smart_embed(
                    ctx,
                    _("You need to be level `{level}` to equip this item.").format(level=equiplevel),
                )

            equip = c.backpack.get(equip_item.name)
            if equip:
                slot = equip.slot[0]
                if len(equip.slot) > 1:
                    slot = "two handed"
                if not getattr(c, equip.slot[0]):
                    equip_msg = box(
                        _("{author} equipped {item} ({slot} slot).").format(
                            author=escape(ctx.author.display_name), item=str(equip), slot=slot
                        ),
                        lang="css",
                    )
                else:
                    equip_msg = box(
                        _("{author} equipped {item} ({slot} slot) and put {put} into their backpack.").format(
                            author=escape(ctx.author.display_name),
                            item=str(equip),
                            slot=slot,
                            put=getattr(c, equip.slot[0]),
                        ),
                        lang="css",
                    )
                await ctx.send(equip_msg)
                c = await c.equip_item(equip, True, is_dev(ctx.author))  # FIXME:
                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))

    @_backpack.command(name="eset", cooldown_after_parsing=True)
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def backpack_eset(self, ctx: commands.Context, *, set_name: str):
        """Equip all parts of a set that you own."""
        if self.in_adventure(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("You tried to magically equip multiple items at once, but the monster ahead nearly killed you."),
            )
        set_list = humanize_list(sorted([f"`{i}`" for i in self.SET_BONUSES.keys()], key=str.lower))
        if set_name is None:
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("Use this command with one of the following set names: \n{sets}").format(sets=set_list),
            )
        async with self.get_lock(ctx.author):
            try:
                character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                ctx.command.reset_cooldown(ctx)
                return

            pieces = await character.get_set_count(return_items=True, set_name=set_name.title())
            if not pieces:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(
                    ctx,
                    _("You have no pieces of `{set_name}` that you can equip.").format(set_name=set_name),
                )
            for piece in pieces:
                character = await character.equip_item(piece, from_backpack=True)
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
            await smart_embed(
                ctx,
                _("I've equipped all pieces of `{set_name}` that you are able to equip.").format(set_name=set_name),
            )

    @_backpack.command(name="disassemble")
    async def backpack_disassemble(self, ctx: commands.Context, *, backpack_items: ItemsConverter):
        """
        Disassemble items from your backpack.

        This will provide a chance for a chest,
        or the item might break while you are handling it...
        """
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to disassemble an item but the monster ahead of you commands your attention."),
            )

        async with self.get_lock(ctx.author):
            if len(backpack_items[1]) > 2:
                msg = await ctx.send(
                    "Are you sure you want to disassemble {count} unique items and their duplicates?".format(
                        count=humanize_number(len(backpack_items[1]))
                    )
                )
                start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(msg, ctx.author)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                except asyncio.TimeoutError:
                    await self._clear_react(msg)
                    return

                if not pred.result:
                    await ctx.send("Not disassembling those items.")
                    return

            try:
                character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            failed = 0
            success = 0
            op = backpack_items[0]
            disassembled = set()
            async for item in AsyncIter(backpack_items[1], steps=100):
                try:
                    item = character.backpack[item.name]
                except KeyError:
                    continue
                if item.name in disassembled:
                    continue
                if item.rarity in ["forged"]:
                    continue
                index = min(RARITIES.index(item.rarity), 4)
                if op == "single":
                    if character.heroclass["name"] != "Tinkerer":
                        roll = random.randint(0, 5)
                        chests = 1
                    else:
                        roll = random.randint(0, 3)
                        chests = random.randint(1, 2)
                    if roll != 0:
                        item.owned -= 1
                        if item.owned <= 0:
                            del character.backpack[item.name]
                        await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
                        return await smart_embed(
                            ctx,
                            _("Your attempt at disassembling `{}` failed and it has been destroyed.").format(item.name),
                        )
                    else:
                        item.owned -= 1
                        if item.owned <= 0:
                            del character.backpack[item.name]
                        character.treasure[index] += chests
                        await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
                        return await smart_embed(
                            ctx,
                            _("Your attempt at disassembling `{}` was successful and you have received {} {}.").format(
                                item.name, chests, _("chests") if chests > 1 else _("chest")
                            ),
                        )
                elif op == "all":
                    disassembled.add(item.name)
                    owned = item.owned
                    async for _loop_counter in AsyncIter(range(0, owned), steps=100):
                        if character.heroclass["name"] != "Tinkerer":
                            roll = random.randint(0, 5)
                            chests = 1
                        else:
                            roll = random.randint(0, 3)
                            chests = random.randint(1, 2)
                        if roll != 0:
                            item.owned -= 1
                            if item.owned <= 0 and item.name in character.backpack:
                                del character.backpack[item.name]
                            failed += 1
                        else:
                            item.owned -= 1
                            if item.owned <= 0 and item.name in character.backpack:
                                del character.backpack[item.name]
                            character.treasure[index] += chests
                            success += 1
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
            return await smart_embed(
                ctx,
                _("You attempted to disassemble multiple items: {succ} were successful and {fail} failed.").format(
                    succ=humanize_number(success), fail=humanize_number(failed)
                ),
            )

    @_backpack.command(name="sellall")
    async def backpack_sellall(
        self,
        ctx: commands.Context,
        rarity: Optional[RarityConverter] = None,
        *,
        slot: Optional[SlotConverter] = None,
    ):
        """Sell all items in your backpack. Optionally specify rarity or slot."""
        assert isinstance(rarity, str) or rarity is None
        assert isinstance(slot, str) or slot is None
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to go sell your items but the monster ahead is not allowing you to leave."),
            )
        if rarity:
            rarity = rarity.lower()
            if rarity not in RARITIES:
                return await smart_embed(
                    ctx,
                    _("{} is not a valid rarity, select one of {}").format(rarity, humanize_list(RARITIES)),
                )
            if rarity.lower() in ["forged"]:
                return await smart_embed(ctx, _("You cannot sell `{rarity}` rarity items.").format(rarity=rarity))
        if slot:
            slot = slot.lower()
            if slot not in ORDER:
                return await smart_embed(
                    ctx,
                    _("{} is not a valid slot, select one of {}").format(slot, humanize_list(ORDER)),
                )

        async with self.get_lock(ctx.author):
            if rarity and slot:
                msg = await ctx.send(
                    "Are you sure you want to sell all {rarity} {slot} items in your inventory?".format(
                        rarity=rarity, slot=slot
                    )
                )
            elif rarity or slot:
                msg = await ctx.send(
                    "Are you sure you want to sell all{rarity}{slot} items in your inventory?".format(
                        rarity=f" {rarity}" if rarity else "", slot=f" {slot}" if slot else ""
                    )
                )
            else:
                msg = await ctx.send(_("Are you sure you want to sell **ALL ITEMS** in your inventory?"))

            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await self._clear_react(msg)
                return

            if not pred.result:
                await ctx.send("Not selling those items.")
                return

            msg = ""
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            total_price = 0
            async with ctx.typing():
                items = [i for n, i in c.backpack.items() if i.rarity not in ["forged"]]
                count = 0
                async for item in AsyncIter(items, steps=100):
                    if rarity and item.rarity != rarity:
                        continue
                    if slot:
                        if len(item.slot) == 1 and slot != item.slot[0]:
                            continue
                        elif len(item.slot) == 2 and slot != "two handed":
                            continue
                    item_price = 0
                    old_owned = item.owned
                    async for _loop_counter in AsyncIter(range(0, old_owned), steps=100):
                        item.owned -= 1
                        item_price += _sell(c, item)
                        if item.owned <= 0:
                            del c.backpack[item.name]
                    item_price = max(item_price, 0)
                    msg += _("{old_item} sold for {price}.\n").format(
                        old_item=str(old_owned) + " " + str(item),
                        price=humanize_number(item_price),
                    )
                    total_price += item_price
                if total_price > 0:
                    try:
                        await bank.deposit_credits(ctx.author, total_price)
                    except BalanceTooHigh as e:
                        await bank.set_balance(ctx.author, e.max_balance)
                c.last_known_currency = await bank.get_balance(ctx.author)
                c.last_currency_check = time.time()
                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
        msg_list = []
        new_msg = _("{author} sold all their{rarity} items for {price}.\n\n{items}").format(
            author=escape(ctx.author.display_name),
            rarity=f" {rarity}" if rarity else "",
            price=humanize_number(total_price),
            items=msg,
        )
        for page in pagify(new_msg, shorten_by=10, page_length=1900):
            msg_list.append(box(page, lang="css"))
        await BaseMenu(
            source=SimpleSource(msg_list),
            delete_message_after=True,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @_backpack.command(name="sell", cooldown_after_parsing=True)
    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    async def backpack_sell(self, ctx: commands.Context, *, item: ItemConverter):
        """Sell an item from your backpack."""

        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to go sell your items but the monster ahead is not allowing you to leave."),
            )
        if item.rarity in ["forged"]:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                box(
                    _("\n{author}, your {device} is refusing to be sold and bit your finger for trying.").format(
                        author=escape(ctx.author.display_name), device=str(item)
                    ),
                    lang="css",
                )
            )

        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                ctx.command.reset_cooldown(ctx)
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            price_shown = _sell(c, item)
            messages = [
                _("{author}, do you want to sell this item for {price} each? {item}").format(
                    author=bold(ctx.author.display_name),
                    item=box(str(item), lang="css"),
                    price=humanize_number(price_shown),
                )
            ]
            try:
                item = c.backpack[item.name]
            except KeyError:
                return

            async def _backpack_sell_menu(
                ctx: commands.Context,
                pages: list,
                controls: dict,
                message: discord.Message,
                page: int,
                timeout: float,
                emoji: str,
            ):
                if message:
                    with contextlib.suppress(discord.HTTPException):
                        await message.delete()
                    await self._backpack_sell_button_action(ctx, emoji, page, item, price_shown, c)
                    return None

            back_pack_sell_controls = {
                "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}": _backpack_sell_menu,
                "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}": _backpack_sell_menu,
                "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}": _backpack_sell_menu,
                "\N{CROSS MARK}": _backpack_sell_menu,
            }

            await menu(ctx, messages, back_pack_sell_controls, timeout=60)

    async def _backpack_sell_button_action(self, ctx, emoji, page, item, price_shown, character):
        currency_name = await bank.get_currency_name(
            ctx.guild,
        )
        msg = ""
        if emoji == "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}":  # user reacted with one to sell.
            ctx.command.reset_cooldown(ctx)
            # sell one of the item
            price = 0
            item.owned -= 1
            price += price_shown
            msg += _("{author} sold one {item} for {price} {currency_name}.\n").format(
                author=bold(ctx.author.display_name),
                item=box(item, lang="css"),
                price=humanize_number(price),
                currency_name=currency_name,
            )
            if item.owned <= 0:
                del character.backpack[item.name]
            price = max(price, 0)
            if price > 0:
                try:
                    await bank.deposit_credits(ctx.author, price)
                except BalanceTooHigh as e:
                    await bank.set_balance(ctx.author, e.max_balance)
        elif emoji == "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}":  # user wants to sell all owned.
            ctx.command.reset_cooldown(ctx)
            price = 0
            old_owned = item.owned
            count = 0
            async for _loop_counter in AsyncIter(range(0, item.owned), steps=50):
                item.owned -= 1
                price += price_shown
                if item.owned <= 0:
                    del character.backpack[item.name]
                count += 1
            msg += _("{author} sold all their {old_item} for {price} {currency_name}.\n").format(
                author=bold(ctx.author.display_name),
                old_item=box(str(item) + " - " + str(old_owned), lang="css"),
                price=humanize_number(price),
                currency_name=currency_name,
            )
            price = max(price, 0)
            if price > 0:
                try:
                    await bank.deposit_credits(ctx.author, price)
                except BalanceTooHigh as e:
                    await bank.set_balance(ctx.author, e.max_balance)
        elif (
            emoji == "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}"
        ):  # user wants to sell all but one.
            if item.owned == 1:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(ctx, _("You already only own one of those items."))
            price = 0
            old_owned = item.owned
            count = 0
            async for _loop_counter in AsyncIter(range(1, item.owned), steps=50):
                item.owned -= 1
                price += price_shown
            count += 1
            if price != 0:
                msg += _("{author} sold all but one of their {old_item} for {price} {currency_name}.\n").format(
                    author=bold(ctx.author.display_name),
                    old_item=box(str(item) + " - " + str(old_owned - 1), lang="css"),
                    price=humanize_number(price),
                    currency_name=currency_name,
                )
                price = max(price, 0)
                if price > 0:
                    try:
                        await bank.deposit_credits(ctx.author, price)
                    except BalanceTooHigh as e:
                        await bank.set_balance(ctx.author, e.max_balance)
        else:  # user doesn't want to sell those items.
            await ctx.send(_("Not selling those items."))

        if msg:
            character.last_known_currency = await bank.get_balance(ctx.author)
            character.last_currency_check = time.time()
            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
            pages = [page for page in pagify(msg, delims=["\n"], page_length=1900)]
            await BaseMenu(
                source=SimpleSource(pages),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)

    @_backpack.command(name="trade")
    async def backpack_trade(
        self,
        ctx: commands.Context,
        buyer: discord.Member,
        asking: Optional[int] = 1000,
        *,
        item: ItemConverter,
    ):
        """Trade an item from your backpack to another user."""
        if ctx.author == buyer:
            return await smart_embed(
                ctx,
                _("You take the item and pass it from one hand to the other. Congratulations, you traded yourself."),
            )
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to trade an item to a party member but the monster ahead commands your attention."),
            )
        if self.in_adventure(user=buyer):
            return await smart_embed(
                ctx,
                _("{buyer} is currently in an adventure... you were unable to reach them via pigeon.").format(
                    buyer=bold(buyer.display_name)
                ),
            )
        if asking < 0:
            return await ctx.send(_("You can't *sell* for less than 0..."))
        try:
            c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            return
        try:
            buy_user = await Character.from_json(ctx, self.config, buyer, self._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            return

        if buy_user.is_backpack_full(is_dev=is_dev(buyer)):
            await ctx.send(_("{author}'s backpack is currently full.").format(author=bold(buyer.display_name)))
            return

        if not any([x for x in c.backpack if item.name.lower() == x.lower()]):
            return await smart_embed(
                ctx,
                _("{author}, you have to specify an item from your backpack to trade.").format(
                    author=bold(ctx.author.display_name)
                ),
            )
        lookup = list(x for n, x in c.backpack.items() if str(item) == str(x))
        if len(lookup) > 1:
            await smart_embed(
                ctx,
                _(
                    "{author}, I found multiple items ({items}) "
                    "matching that name in your backpack.\nPlease be more specific."
                ).format(
                    author=bold(ctx.author.display_name),
                    items=humanize_list([x.name for x in lookup]),
                ),
            )
            return
        if any([x for x in lookup if x.rarity == "forged"]):
            device = [x for x in lookup if x.rarity == "forged"]
            return await ctx.send(
                box(
                    _("\n{author}, your {device} does not want to leave you.").format(
                        author=escape(ctx.author.display_name), device=str(device[0])
                    ),
                    lang="css",
                )
            )
        elif any([x for x in lookup if x.rarity == "set"]):
            return await ctx.send(
                box(
                    _("\n{character}, you cannot trade Set items as they are bound to your soul.").format(
                        character=escape(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        else:
            item = lookup[0]
            hand = item.slot[0] if len(item.slot) < 2 else "two handed"
            currency_name = await bank.get_currency_name(
                ctx.guild,
            )
            if str(currency_name).startswith("<"):
                currency_name = "credits"
            trade_talk = box(
                _(
                    "{author} wants to sell {item}. "
                    "(ATT: {att_item} | "
                    "CHA: {cha_item} | "
                    "INT: {int_item} | "
                    "DEX: {dex_item} | "
                    "LUCK: {luck_item}) "
                    "[{hand}])\n{buyer}, "
                    "do you want to buy this item for {asking} {currency_name}?"
                ).format(
                    author=escape(ctx.author.display_name),
                    item=item,
                    att_item=str(item.att),
                    cha_item=str(item.cha),
                    int_item=str(item.int),
                    dex_item=str(item.dex),
                    luck_item=str(item.luck),
                    hand=hand,
                    buyer=escape(buyer.display_name),
                    asking=str(asking),
                    currency_name=currency_name,
                ),
                lang="css",
            )
            async with self.get_lock(ctx.author):
                trade_msg = await ctx.send(f"{buyer.mention}\n{trade_talk}")
                start_adding_reactions(trade_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(trade_msg, buyer)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                except asyncio.TimeoutError:
                    await self._clear_react(trade_msg)
                    return
                if pred.result:  # buyer reacted with Yes.
                    with contextlib.suppress(discord.errors.NotFound):
                        if await bank.can_spend(buyer, asking):
                            if buy_user.rebirths + 1 < c.rebirths:
                                return await smart_embed(
                                    ctx,
                                    _(
                                        "You can only trade with people that are the same "
                                        "rebirth level, one rebirth level less than you, "
                                        "or a higher rebirth level than yours."
                                    ),
                                )
                            try:
                                await bank.transfer_credits(buyer, ctx.author, asking)
                            except BalanceTooHigh as e:
                                await bank.withdraw_credits(buyer, asking)
                                await bank.set_balance(ctx.author, e.max_balance)
                            c.backpack[item.name].owned -= 1
                            newly_owned = c.backpack[item.name].owned
                            if c.backpack[item.name].owned <= 0:
                                del c.backpack[item.name]
                            async with self.get_lock(buyer):
                                if item.name in buy_user.backpack:
                                    buy_user.backpack[item.name].owned += 1
                                else:
                                    item.owned = 1
                                    buy_user.backpack[item.name] = item
                                await self.config.user(buyer).set(await buy_user.to_json(ctx, self.config))
                                item.owned = newly_owned
                                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))

                            await trade_msg.edit(
                                content=(
                                    box(
                                        _("\n{author} traded {item} to {buyer} for {asking} {currency_name}.").format(
                                            author=escape(ctx.author.display_name),
                                            item=item,
                                            buyer=escape(buyer.display_name),
                                            asking=asking,
                                            currency_name=currency_name,
                                        ),
                                        lang="css",
                                    )
                                )
                            )
                            await self._clear_react(trade_msg)
                        else:
                            await trade_msg.edit(
                                content=_("{buyer}, you do not have enough {currency_name}.").format(
                                    buyer=bold(buyer.display_name),
                                    currency_name=currency_name,
                                )
                            )
                else:
                    with contextlib.suppress(discord.HTTPException):
                        await trade_msg.delete()

    @commands.command(name="ebackpack")
    @commands.bot_has_permissions(add_reactions=True)
    async def commands_equipable_backpack(
        self,
        ctx: commands.Context,
        show_diff: Optional[bool] = False,
        rarity: Optional[RarityConverter] = None,
        *,
        slot: Optional[SlotConverter] = None,
    ):
        """This shows the contents of your backpack that can be equipped.

        Give it a rarity and/or slot to filter what backpack items to show.

        Note: An item **degrade** level is how many rebirths it will last, before it is broken down.
        """
        assert isinstance(rarity, str) or rarity is None
        assert isinstance(slot, str) or slot is None
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        if not ctx.invoked_subcommand:
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if rarity:
                rarity = rarity.lower()
                if rarity not in RARITIES:
                    return await smart_embed(
                        ctx,
                        _("{} is not a valid rarity, select one of {}").format(rarity, humanize_list(RARITIES)),
                    )
            if slot:
                slot = slot.lower()
                if slot not in ORDER:
                    return await smart_embed(
                        ctx,
                        _("{} is not a valid slot, select one of {}").format(slot, humanize_list(ORDER)),
                    )

            backpack_pages = await c.get_backpack(rarity=rarity, slot=slot, show_delta=show_diff, equippable=True)
            if backpack_pages:
                await BackpackMenu(
                    source=SimpleSource(backpack_pages),
                    help_command=self.commands_equipable_backpack,
                    delete_message_after=True,
                    clear_reactions_after=True,
                    timeout=60,
                ).start(ctx=ctx)
            else:
                return await smart_embed(
                    ctx,
                    _("You have no equippable items that match this query."),
                )

    @commands.group(name="cbackpack")
    @commands.bot_has_permissions(add_reactions=True)
    async def commands_cbackpack(
        self,
        ctx: commands.Context,
    ):
        """Complex backpack management tools.

        Please read the usage instructions [here](https://github.com/aikaterna/gobcog/blob/master/docs/cbackpack.md)
        """

    @commands_cbackpack.command(name="show")
    async def commands_cbackpack_show(
        self,
        ctx: commands.Context,
        *,
        query: BackpackFilterParser,
    ):
        """This shows the contents of your backpack.

        Please read the usage instructions [here](https://github.com/aikaterna/gobcog/blob/master/docs/cbackpack.md)
        """
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        try:
            c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            return
        backpack_pages = await c.get_argparse_backpack(query)
        if backpack_pages:
            await BackpackMenu(
                source=SimpleSource(backpack_pages),
                help_command=self.commands_cbackpack,
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)
        else:
            return await smart_embed(
                ctx,
                _("You have no items that match this query."),
            )

    @commands_cbackpack.command(name="disassemble")
    async def commands_cbackpack_disassemble(self, ctx: commands.Context, *, query: BackpackFilterParser):
        """
        Disassemble items from your backpack.

        This will provide a chance for a chest,
        or the item might break while you are handling it...

        Please read the usage instructions [here](https://github.com/aikaterna/gobcog/blob/master/docs/cbackpack.md)
        """
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to disassemble an item but the monster ahead of you commands your attention."),
            )
        query.pop("degrade", None)  # Disallow selling by degrade levels
        async with self.get_lock(ctx.author):
            try:
                character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            slots = await character.get_argparse_backpack_items(query, rarity_exclude=["forged"])
            if (total_items := sum(len(i) for s, i in slots)) > 2:

                msg = await ctx.send(
                    "Are you sure you want to disassemble {count} unique items and their duplicates?".format(
                        count=humanize_number(total_items)
                    )
                )
                start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(msg, ctx.author)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                except asyncio.TimeoutError:
                    await self._clear_react(msg)
                    return

                if not pred.result:
                    await ctx.send("Not disassembling those items.")
                    return
        failed = 0
        success = 0
        disassembled = set()

        async for slot_name, slot_group in AsyncIter(slots, steps=100):
            async for item_name, item in AsyncIter(slot_group, steps=100):
                try:
                    item = character.backpack[item.name]
                except KeyError:
                    continue
                if item.name in disassembled:
                    continue
                if item.rarity in ["forged"]:
                    failed += 1
                    continue
                index = min(RARITIES.index(item.rarity), 4)
                disassembled.add(item.name)
                owned = item.owned
                async for _loop_counter in AsyncIter(range(0, owned), steps=100):
                    if character.heroclass["name"] != "Tinkerer":
                        roll = random.randint(0, 5)
                        chests = 1
                    else:
                        roll = random.randint(0, 3)
                        chests = random.randint(1, 2)
                    if roll != 0:
                        item.owned -= 1
                        if item.owned <= 0 and item.name in character.backpack:
                            del character.backpack[item.name]
                        failed += 1
                    else:
                        item.owned -= 1
                        if item.owned <= 0 and item.name in character.backpack:
                            del character.backpack[item.name]
                        character.treasure[index] += chests
                        success += 1
        if (not failed) and (not success):
            return await smart_embed(
                ctx,
                _("No items matched your query.").format(),
            )
        else:

            await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
            return await smart_embed(
                ctx,
                _("You attempted to disassemble multiple items: {succ} were successful and {fail} failed.").format(
                    succ=humanize_number(success), fail=humanize_number(failed)
                ),
            )

    @commands_cbackpack.command(name="sell", cooldown_after_parsing=True)
    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    async def commands_cbackpack_sell(self, ctx: commands.Context, *, query: BackpackFilterParser):
        """Sell items from your backpack.

        Forged items cannot be sold using this command.

        Please read the usage instructions [here](https://github.com/aikaterna/gobcog/blob/master/docs/cbackpack.md)
        """

        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to go sell your items but the monster ahead is not allowing you to leave."),
            )
        query.pop("degrade", None)  # Disallow selling by degrade levels
        async with self.get_lock(ctx.author):
            try:
                character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            slots = await character.get_argparse_backpack_items(query, rarity_exclude=["forged"])
            if (total_items := sum(len(i) for s, i in slots)) > 2:
                msg = await ctx.send(
                    "Are you sure you want to sell {count} items in your inventory that match this query?".format(
                        count=humanize_number(total_items)
                    )
                )
                start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(msg, ctx.author)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                except asyncio.TimeoutError:
                    await self._clear_react(msg)
                    return

                if not pred.result:
                    await ctx.send("Not selling those items.")
                    return
            total_price = 0
            msg = ""
            async with ctx.typing():
                async for slot_name, slot_group in AsyncIter(slots, steps=100):
                    async for item_name, item in AsyncIter(slot_group, steps=100):
                        old_owned = item.owned
                        item_price = 0
                        async for _loop_counter in AsyncIter(range(0, old_owned), steps=100):
                            item.owned -= 1
                            item_price += _sell(character, item)
                            if item.owned <= 0 and item.name in character.backpack:
                                del character.backpack[item.name]
                        item_price = max(item_price, 0)
                        msg += _("{old_item} sold for {price}.\n").format(
                            old_item=str(old_owned) + " " + str(item),
                            price=humanize_number(item_price),
                        )
                        total_price += item_price
                if total_price > 0:
                    try:
                        await bank.deposit_credits(ctx.author, total_price)
                    except BalanceTooHigh as e:
                        await bank.set_balance(ctx.author, e.max_balance)
                character.last_known_currency = await bank.get_balance(ctx.author)
                character.last_currency_check = time.time()
                await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
            if total_price == 0:
                return await smart_embed(
                    ctx,
                    _("No items matched your query.").format(),
                )
            if msg:
                msg_list = []
                new_msg = _("{author} sold {number} items and their duplicates for {price}.\n\n{items}").format(
                    author=escape(ctx.author.display_name),
                    number=humanize_number(total_items),
                    price=humanize_number(total_price),
                    items=msg,
                )
                for page in pagify(new_msg, shorten_by=10, page_length=1900):
                    msg_list.append(box(page, lang="css"))
                await BaseMenu(
                    source=SimpleSource(msg_list),
                    delete_message_after=True,
                    clear_reactions_after=True,
                    timeout=60,
                ).start(ctx=ctx)
