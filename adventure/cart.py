# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number, pagify

from .bank import bank
from .charsheet import Character, Item
from .constants import ANSIBackgroundColours, ANSIBackgroundTextColours, ANSITextColours, Rarities
from .helpers import escape, is_dev, smart_embed

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class TraderModal(discord.ui.Modal):
    def __init__(self, item: Item, cog: commands.Cog, view: Trader, ctx: commands.Context):
        super().__init__(title=_("How many would you like to buy?"))
        self.item = item
        self.cog = cog
        self.ctx = ctx
        self.view = view
        self.amount_input = discord.ui.TextInput(
            label=item.name,
            style=discord.TextStyle.short,
            placeholder=_("Amount"),
            max_length=100,
            min_length=0,
            required=False,
        )
        self.add_item(self.amount_input)

    async def wasting_time(self, interaction: discord.Interaction):
        await smart_embed(None, _("You're wasting my time."), interaction=interaction, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        if datetime.now(timezone.utc) >= self.view.end_time:
            self.view.stop()
            await interaction.response.send_message(
                _("{cart_name} has moved onto the next village.").format(cart_name=self.view.cart_name), ephemeral=True
            )
            return
        number = self.amount_input.value

        if not number:
            await self.wasting_time(interaction)
            return
        try:
            number = int(number)
        except ValueError:
            await self.wasting_time(interaction)
            return
        if number < 0:
            await self.wasting_time(interaction)
            return

        currency_name = await bank.get_currency_name(
            interaction.guild,
        )
        if currency_name.startswith("<"):
            currency_name = "credits"
        spender = interaction.user
        price = self.view.items.get(self.item.name, {}).get("price") * number
        if await bank.can_spend(spender, price):
            await bank.withdraw_credits(spender, price)
            async with self.cog.get_lock(spender):
                try:
                    c = await Character.from_json(self.ctx, self.cog.config, spender, self.cog._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    return

                if c.is_backpack_full(is_dev=is_dev(spender)):
                    await interaction.response.send_message(
                        _("**{author}**, Your backpack is currently full.").format(author=escape(spender.display_name))
                    )
                    return
                item = self.item
                item.owned = number
                await c.add_to_backpack(item, number=number)
                await self.cog.config.user(spender).set(await c.to_json(self.ctx, self.cog.config))
                await interaction.response.send_message(
                    box(
                        _(
                            "{author} bought {p_result} {item_name} for "
                            "{item_price} {currency_name} and put it into their backpack."
                        ).format(
                            author=escape(spender.display_name),
                            p_result=number,
                            item_name=item.ansi,
                            item_price=humanize_number(price),
                            currency_name=currency_name,
                        ),
                        lang="ansi",
                    )
                )
        else:
            await interaction.response.send_message(
                _("**{author}**, you do not have enough {currency_name}.").format(
                    author=escape(spender.display_name), currency_name=currency_name
                )
            )


class TraderButton(discord.ui.Button):
    def __init__(self, item: Item, cog: commands.Cog):
        super().__init__(label=str(item), emoji=item.rarity.emoji)
        self.item = item
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if datetime.now(timezone.utc) >= self.view.end_time:
            self.view.stop()
            await self.view.on_timeout()
            await interaction.response.send_message(
                _("{cart_name} has moved onto the next village.").format(cart_name=self.view.cart_name), ephemeral=True
            )
            return
        modal = TraderModal(self.item, self.cog, view=self.view, ctx=self.view.ctx)
        await interaction.response.send_modal(modal)


class TraderSelect(discord.ui.Select):
    def __init__(self, items: List[Item], cog: commands.Cog):
        self.items = items
        self.cog = cog
        self.select_options = [
            discord.SelectOption(label=str(item), value=str(i), description=item.stat_str(), emoji=item.rarity.emoji)
            for i, item in enumerate(items)
        ]
        super().__init__(
            min_values=1, max_values=1, placeholder=_("What would you like to purchase?"), options=self.select_options
        )

    async def callback(self, interaction: discord.Interaction):
        if datetime.now(timezone.utc) >= self.view.end_time:
            self.view.stop()
            await self.view.on_timeout()
            await interaction.response.send_message(
                _("{cart_name} has moved onto the next village.").format(cart_name=self.view.cart_name), ephemeral=True
            )
            return
        modal = TraderModal(self.items[int(self.values[0])], self.cog, view=self.view, ctx=self.view.ctx)
        await interaction.response.send_modal(modal)


class Trader(discord.ui.View):
    def __init__(self, timeout: float, ctx: commands.Context, cog: commands.Cog):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.items = {}
        self.message = None
        self.stock_str = ""
        self.end_time = datetime.now(timezone.utc) + timedelta(seconds=timeout)
        self.cart_name = _("Hawl's brother")

    async def on_timeout(self):
        if self.message is not None:
            timestamp = f"<t:{int(self.end_time.timestamp())}:R>"
            new_content = _("{cart_name} left {time}.").format(time=timestamp, cart_name=self.cart_name)
            await self.message.edit(content=new_content, view=None)

    async def edit_timestamp(self):
        if self.timeout is None:
            return
        self.end_time = datetime.now(timezone.utc) + timedelta(seconds=self.timeout)
        timestamp = f"<t:{int(self.end_time.timestamp())}:R>"
        text = self.stock_str
        text += _("I am leaving {time}.\nDo you want to buy any of these fine items? Tell me which one below:").format(
            time=timestamp
        )
        await self.message.edit(content=text)

    async def start(self, ctx: commands.Context, bypass: bool = False, stockcount: Optional[int] = None):
        cart = await self.cog.config.cart_name()
        if await self.cog.config.guild(ctx.guild).cart_name():
            cart = await self.cog.config.guild(ctx.guild).cart_name()
        self.cart_name = cart
        cart_header = _("[{cart_name} is bringing the cart around!]").format(cart_name=cart) + "\n\n"
        text = ANSITextColours.blue.as_str(cart_header)
        if ctx.guild.id not in self.cog._last_trade:
            self.cog._last_trade[ctx.guild.id] = 0

        if not bypass:
            if self.cog._last_trade[ctx.guild.id] == 0:
                self.cog._last_trade[ctx.guild.id] = time.time()
            elif self.cog._last_trade[ctx.guild.id] >= time.time() - self.timeout:
                # trader can return after 3 hours have passed since last visit.
                return  # silent return.
        self.cog._last_trade[ctx.guild.id] = time.time()

        room = await self.cog.config.guild(ctx.guild).cartroom()
        if room:
            room = ctx.guild.get_channel(room)
        if room is None or bypass:
            room = ctx
        if stockcount is None:
            stockcount = random.randint(3, 9)
        self.cog._curent_trader_stock[ctx.guild.id] = (stockcount, {})

        stock = await self.generate(stockcount)
        currency_name = await bank.get_currency_name(
            ctx.guild,
        )
        if str(currency_name).startswith("<"):
            currency_name = "credits"
        table = None
        price_colour = ANSIBackgroundTextColours(ANSITextColours.white, ANSIBackgroundColours.orange)
        for index, item in enumerate(stock):
            item = stock[index]
            price = item["price"]
            price_str = f"{humanize_number(price)} {currency_name}"
            price_str = price_colour.as_str(price_str)
            if table is None:
                table = item["item"].table(None)
                stats = table.rows.pop(-1)
                # We need to remove the last item to stick the price info inside the table
                # so that it doesn't appear outside the border
                table.rows.append([price_str])
                table.rows.append(stats)
            else:
                item_name, item_row = item["item"].row(None)
                table.rows.append([item_name])
                table.rows.append([item_row])
                stats = table.rows.pop(-1)
                table.rows.append([price_str])
                table.rows.append(stats)
        text += str(table)
        self.stock_str = text
        timestamp = f"<t:{int(self.end_time.timestamp())}:R>"

        pages = list(pagify(text, delims=["```", "\n"], priority=True, page_length=1900))
        msg_ref = None
        for page in pages:
            msg_ref = await room.send(box(page, lang="ansi"))
        last_page_text = _(
            "I am leaving {time}.\nDo you want to buy any of these fine items? Tell me which one below:"
        ).format(time=timestamp)
        self.message = await room.send(last_page_text, view=self, reference=msg_ref)
        self.cog.bot.dispatch("adventure_cart", ctx)  # dispatch after all messages sent

    async def generate(self, howmany: int = 5):
        output = {}
        howmany = max(min(25, howmany), 1)
        while len(self.items) < howmany:
            rarity_roll = random.random()
            #  rarity_roll = .9
            # 1% legendary
            if rarity_roll >= 0.95:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.legendary)
                # min. 10 stat for legendary, want to be about 50k
                price = random.randint(2500, 5000)
            # 20% epic
            elif rarity_roll >= 0.7:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.epic)
                # min. 5 stat for epic, want to be about 25k
                price = random.randint(1000, 2000)
            # 35% rare
            elif rarity_roll >= 0.35:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.rare)
                # around 3 stat for rare, want to be about 3k
                price = random.randint(500, 1000)
            else:
                item = await self.ctx.cog._genitem(self.ctx, Rarities.normal)
                # 1 stat for normal, want to be <1k
                price = random.randint(100, 500)
            # 35% normal
            price *= item.max_main_stat

            self.items.update({item.name: {"itemname": item.name, "item": item, "price": price, "lvl": item.lvl}})
            # self.add_item(TraderButton(item, self.cog))
        item_list = []
        for item, data in self.items.items():
            item_list.append(data["item"])
        self.add_item(TraderSelect(item_list, self.cog))

        for index, item in enumerate(self.items):
            output.update({index: self.items[item]})
        return output
