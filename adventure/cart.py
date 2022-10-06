# -*- coding: utf-8 -*-
import asyncio
import contextlib
import logging
import random
import time

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, box, humanize_number
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character
from .helpers import escape, is_dev, smart_embed

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class AdventureCart(AdventureMixin):
    """
    This class handles the cart logic
    """

    # TODO: Replace this logic with more class based
    # There's no reason to keep this as part of the master class
    # Let's use more objects!

    async def _handle_cart(self, reaction: discord.Reaction, user: discord.Member):
        guild = user.guild
        emojis = ReactionPredicate.NUMBER_EMOJIS
        itemindex = emojis.index(str(reaction.emoji)) - 1
        items = self._current_traders[guild.id]["stock"][itemindex]
        self._current_traders[guild.id]["users"].append(user)
        spender = user
        channel = reaction.message.channel
        currency_name = await bank.get_currency_name(
            guild,
        )
        if currency_name.startswith("<"):
            currency_name = "credits"
        item_data = box(items["item"].formatted_name + " - " + humanize_number(items["price"]), lang="css")
        to_delete = await channel.send(
            _("{user}, how many {item} would you like to buy?").format(user=user.mention, item=item_data)
        )
        ctx = await self.bot.get_context(reaction.message)
        ctx.command = self.makecart
        ctx.author = user
        pred = MessagePredicate.valid_int(ctx)
        try:
            msg = await self.bot.wait_for("message", check=pred, timeout=30)
        except asyncio.TimeoutError:
            self._current_traders[guild.id]["users"].remove(user)
            return
        if pred.result < 1:
            with contextlib.suppress(discord.HTTPException):
                await to_delete.delete()
                await msg.delete()
            await smart_embed(ctx, _("You're wasting my time."))
            self._current_traders[guild.id]["users"].remove(user)
            return
        if await bank.can_spend(spender, int(items["price"]) * pred.result):
            await bank.withdraw_credits(spender, int(items["price"]) * pred.result)
            async with self.get_lock(user):
                try:
                    c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    return
                if c.is_backpack_full(is_dev=is_dev(user)):
                    with contextlib.suppress(discord.HTTPException):
                        await to_delete.delete()
                        await msg.delete()
                    await channel.send(
                        _("{author}, Your backpack is currently full.").format(author=bold(user.display_name))
                    )
                    return
                item = items["item"]
                item.owned = pred.result
                await c.add_to_backpack(item, number=pred.result)
                await self.config.user(user).set(await c.to_json(ctx, self.config))
                with contextlib.suppress(discord.HTTPException):
                    await to_delete.delete()
                    await msg.delete()
                await channel.send(
                    box(
                        _(
                            "{author} bought {p_result} {item_name} for "
                            "{item_price} {currency_name} and put it into their backpack."
                        ).format(
                            author=escape(user.display_name),
                            p_result=pred.result,
                            item_name=item.formatted_name,
                            item_price=humanize_number(items["price"] * pred.result),
                            currency_name=currency_name,
                        ),
                        lang="css",
                    )
                )
                self._current_traders[guild.id]["users"].remove(user)
        else:
            with contextlib.suppress(discord.HTTPException):
                await to_delete.delete()
                await msg.delete()
            await channel.send(
                _("{author}, you do not have enough {currency_name}.").format(
                    author=bold(user.display_name), currency_name=currency_name
                )
            )
            self._current_traders[guild.id]["users"].remove(user)

    async def _trader(self, ctx: commands.Context, bypass=False):
        em_list = ReactionPredicate.NUMBER_EMOJIS

        cart = await self.config.cart_name()
        if await self.config.guild(ctx.guild).cart_name():
            cart = await self.config.guild(ctx.guild).cart_name()
        text = box(_("[{} is bringing the cart around!]").format(cart), lang="css")
        timeout = await self.config.guild(ctx.guild).cart_timeout()
        if ctx.guild.id not in self._last_trade:
            self._last_trade[ctx.guild.id] = 0

        if not bypass:
            if self._last_trade[ctx.guild.id] == 0:
                self._last_trade[ctx.guild.id] = time.time()
            elif self._last_trade[ctx.guild.id] >= time.time() - timeout:
                # trader can return after 3 hours have passed since last visit.
                return  # silent return.
        self._last_trade[ctx.guild.id] = time.time()

        room = await self.config.guild(ctx.guild).cartroom()
        if room:
            room = ctx.guild.get_channel(room)
        if room is None or bypass:
            room = ctx.channel
        if room is None:
            return
        room: discord.TextChannel
        room_perms = room.permissions_for(ctx.me)
        if not all([room_perms.send_messages, room_perms.add_reactions]):
            log.debug(
                "I don't have permissions to send messages or add reactions in {} ({})".format(room.id, room.guild.id)
            )
            return
        self.bot.dispatch("adventure_cart", ctx)  # dispatch after silent return
        stockcount = random.randint(3, 9)
        controls = {em_list[i + 1]: i for i in range(stockcount)}
        self._curent_trader_stock[ctx.guild.id] = (stockcount, controls)

        stock = await self._trader_get_items(ctx, stockcount)
        currency_name = await bank.get_currency_name(
            ctx.guild,
        )
        if str(currency_name).startswith("<"):
            currency_name = "credits"
        for (index, item) in enumerate(stock):
            item = stock[index]
            if len(item["item"].slot) == 2:  # two handed weapons add their bonuses twice
                hand = "two handed"
                att = item["item"].att * 2
                cha = item["item"].cha * 2
                intel = item["item"].int * 2
                luck = item["item"].luck * 2
                dex = item["item"].dex * 2
            else:
                if item["item"].slot[0] == "right" or item["item"].slot[0] == "left":
                    hand = item["item"].slot[0] + _(" handed")
                else:
                    hand = item["item"].slot[0] + _(" slot")
                att = item["item"].att
                cha = item["item"].cha
                intel = item["item"].int
                luck = item["item"].luck
                dex = item["item"].dex
            text += box(
                _(
                    "\n[{i}] Lvl req {lvl} | {item_name} ("
                    "Attack: {str_att}, "
                    "Charisma: {str_cha}, "
                    "Intelligence: {str_int}, "
                    "Dexterity: {str_dex}, "
                    "Luck: {str_luck} "
                    "[{hand}]) for {item_price} {currency_name}."
                ).format(
                    i=str(index + 1),
                    item_name=item["item"].formatted_name,
                    lvl=item["item"].lvl,
                    str_att=str(att),
                    str_int=str(intel),
                    str_cha=str(cha),
                    str_luck=str(luck),
                    str_dex=str(dex),
                    hand=hand,
                    item_price=humanize_number(item["price"]),
                    currency_name=currency_name,
                ),
                lang="css",
            )
        text += _("Do you want to buy any of these fine items? Tell me which one below:")
        msg = await room.send(text)
        start_adding_reactions(msg, controls.keys())
        self._current_traders[ctx.guild.id] = {"msg": msg.id, "stock": stock, "users": []}
        timeout = self._last_trade[ctx.guild.id] + 180 - time.time()
        if timeout <= 0:
            timeout = 0
        timer = await self._cart_countdown(ctx, timeout, _("The cart will leave in: "), room=room)
        self.tasks[msg.id] = timer
        try:
            await asyncio.wait_for(timer, timeout + 5)
        except asyncio.TimeoutError:
            await self._clear_react(msg)
            return
        with contextlib.suppress(discord.HTTPException):
            await msg.delete()

    async def _trader_get_items(self, ctx: commands.Context, howmany: int):
        items = {}
        output = {}
        while len(items) < howmany:
            rarity_roll = random.random()
            #  rarity_roll = .9
            # 1% legendary
            if rarity_roll >= 0.95:
                item = await self._genitem(ctx, "legendary")
                # min. 10 stat for legendary, want to be about 50k
                price = random.randint(2500, 5000)
            # 20% epic
            elif rarity_roll >= 0.7:
                item = await self._genitem(ctx, "epic")
                # min. 5 stat for epic, want to be about 25k
                price = random.randint(1000, 2000)
            # 35% rare
            elif rarity_roll >= 0.35:
                item = await self._genitem(ctx, "rare")
                # around 3 stat for rare, want to be about 3k
                price = random.randint(500, 1000)
            else:
                item = await self._genitem(ctx, "normal")
                # 1 stat for normal, want to be <1k
                price = random.randint(100, 500)
            # 35% normal
            price *= item.max_main_stat

            items.update({item.name: {"itemname": item.name, "item": item, "price": price, "lvl": item.lvl}})

        for (index, item) in enumerate(items):
            output.update({index: items[item]})
        return output
