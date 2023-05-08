# -*- coding: utf-8 -*-
import logging
import re
import time
from typing import Literal, Union

import discord
from beautifultable import ALIGN_LEFT, BeautifulTable
from redbot.core import commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_number

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character, Item
from .constants import ANSITextColours, Rarities
from .converters import RarityConverter, Stats
from .helpers import escape, has_separated_economy, smart_embed
from .menus import BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class EconomyCommands(AdventureMixin):
    """Commands for interacting with Adventure's economy"""

    @commands.group(name="atransfer")
    @has_separated_economy()
    async def commands_atransfer(self, ctx: commands.Context):
        """Transfer currency between players/economies."""

    @commands_atransfer.command(name="deposit")
    @commands.guild_only()
    async def commands_atransfer_deposit(self, ctx: commands.Context, *, amount: int):
        """Convert bank currency to gold."""
        from_conversion_rate = await self.config.to_conversion_rate()
        transferable_amount = amount * from_conversion_rate
        if amount <= 0:
            await smart_embed(
                ctx,
                _("{author.mention} You can't deposit 0 or negative values.").format(author=ctx.author),
            )
            return
        if not await bank.can_spend(ctx.author, amount=amount, _forced=True):
            await smart_embed(
                ctx,
                _("{author.mention} You don't have enough {name}.").format(
                    author=ctx.author, name=await bank.get_currency_name(ctx.guild, _forced=True)
                ),
            )
            return
        try:
            await bank.withdraw_credits(member=ctx.author, amount=amount, _forced=True)
        except ValueError:
            await smart_embed(
                ctx,
                _("{author.mention} You don't have enough {name}.").format(
                    author=ctx.author, name=await bank.get_currency_name(ctx.guild, _forced=True)
                ),
            )
            return
        try:
            await bank.deposit_credits(member=ctx.author, amount=transferable_amount)
        except BalanceTooHigh as exc:
            await bank.set_balance(member=ctx.author, amount=exc.max_balance)
        await smart_embed(
            ctx,
            _("{author.mention} you converted {amount} {currency} to {a_amount} {a_currency}.").format(
                author=ctx.author,
                amount=humanize_number(amount),
                a_amount=humanize_number(transferable_amount),
                a_currency=await bank.get_currency_name(ctx.guild),
                currency=await bank.get_currency_name(ctx.guild, _forced=True),
            ),
        )
        try:
            character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
        else:
            if character.last_currency_check + 600 < time.time() or character.bal > character.last_known_currency:
                character.last_known_currency = await bank.get_balance(ctx.author)
                character.last_currency_check = time.time()
                await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))

    @commands_atransfer.command(name="withdraw", cooldown_after_parsing=True)
    @commands.guild_only()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def commands_atransfer_withdraw(self, ctx: commands.Context, *, amount: int):
        """Convert gold to bank currency."""
        if await bank.is_global(_forced=True):
            global_config = await self.config.all()
            can_withdraw = global_config["disallow_withdraw"]
            max_allowed_withdraw = global_config["max_allowed_withdraw"]
            is_global = True
        else:
            guild_config = await self.config.guild(ctx.guild).all()
            can_withdraw = guild_config["disallow_withdraw"]
            max_allowed_withdraw = guild_config["max_allowed_withdraw"]
            is_global = False
        if not can_withdraw or max_allowed_withdraw < 1:
            if is_global:
                string = _("{author.mention} my owner has disabled this option.")
            else:
                string = _("{author.mention} the admins of this server do not allow you to withdraw here.")
            await smart_embed(
                ctx,
                string.format(author=ctx.author),
            )
            return
        if amount <= 0:
            await smart_embed(
                ctx,
                _("{author.mention} You can't withdraw 0 or negative values.").format(author=ctx.author),
            )
            return
        configs = await self.config.all()
        from_conversion_rate = configs.get("from_conversion_rate")
        transferable_amount = amount // from_conversion_rate
        if not await bank.can_spend(member=ctx.author, amount=amount):
            return await smart_embed(
                ctx,
                _("{author.mention} you don't have enough {name}.").format(
                    author=ctx.author, name=await bank.get_currency_name(ctx.guild)
                ),
            )
        if transferable_amount > max_allowed_withdraw:
            return await smart_embed(
                ctx,
                _("{author.mention} I can't allow you to transfer {amount} to {bank}.").format(
                    author=ctx.author,
                    amount=humanize_number(transferable_amount),
                    bank=await bank.get_bank_name(ctx.guild),
                ),
            )
        try:
            await bank.deposit_credits(member=ctx.author, amount=transferable_amount, _forced=True)
        except BalanceTooHigh as exc:
            await bank.set_balance(ctx.author, exc.max_balance, _forced=True)
        await bank.withdraw_credits(member=ctx.author, amount=amount)
        await smart_embed(
            ctx,
            _("{author.mention} you converted {a_amount} {a_currency} to {amount} {currency}.").format(
                author=ctx.author,
                a_amount=humanize_number(amount),
                amount=humanize_number(transferable_amount),
                a_currency=await bank.get_currency_name(ctx.guild),
                currency=await bank.get_currency_name(ctx.guild, _forced=True),
            ),
        )

    @commands_atransfer.command(name="player", cooldown_after_parsing=True)
    @commands.guild_only()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def commands_atransfer_player(self, ctx: commands.Context, amount: int, *, player: discord.Member):
        """Transfer gold to another player."""
        if amount <= 0:
            await smart_embed(
                ctx,
                _("{author.mention} You can't transfer 0 or negative values.").format(author=ctx.author),
            )
            ctx.command.reset_cooldown(ctx)
            return
        currency = await bank.get_currency_name(ctx.guild)
        if not await bank.can_spend(member=ctx.author, amount=amount):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("{author.mention} you don't have enough {name}.").format(
                    author=ctx.author, name=await bank.get_currency_name(ctx.guild)
                ),
            )
        tax = await self.config.tax_brackets.all()
        highest = 0
        for tax, percent in tax.items():
            tax = int(tax)
            if tax >= amount:
                break
            highest = percent

        try:
            transfered = await bank.transfer_credits(
                from_=ctx.author, to=player, amount=amount, tax=highest
            )  # Customizable Tax
        except (ValueError, BalanceTooHigh) as e:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(str(e))

        await ctx.send(
            _(
                "{user} transferred {num} {currency} to {other_user} "
                "(You have been taxed {tax:.2%}, total transfered: {transfered})"
            ).format(
                user=ctx.author.display_name,
                num=humanize_number(amount),
                currency=currency,
                other_user=player.display_name,
                tax=highest,
                transfered=humanize_number(transfered),
            )
        )

    @commands_atransfer.command(name="give")
    @commands.is_owner()
    async def commands_atransfer_give(self, ctx: commands.Context, amount: int, *players: discord.Member):
        """[Owner] Give gold to adventurers."""
        if amount <= 0:
            await smart_embed(
                ctx,
                _("{author.mention} You can't give 0 or negative values.").format(author=ctx.author),
            )
            return
        players_string = ""
        for player in players:
            try:
                await bank.deposit_credits(member=player, amount=amount)
                players_string += f"{player.display_name}\n"
            except BalanceTooHigh as exc:
                await bank.set_balance(member=player, amount=exc.max_balance)
                players_string += f"{player.display_name}\n"

        await smart_embed(
            ctx,
            _("{author.mention} I've given {amount} {name} to the following adventurers:\n\n{players}").format(
                author=ctx.author,
                amount=humanize_number(amount),
                players=players_string,
                name=await bank.get_currency_name(ctx.guild),
            ),
        )

    @commands.command(name="mysets")
    async def commands_mysets(self, ctx: commands.Context):
        """Show your sets."""

        try:
            character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            return

        sets = await character.get_set_count()
        table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
        table.set_style(BeautifulTable.STYLE_RST)
        table.columns.header = [
            "Name",
            "Unique Pieces",
            "Unique Owned",
        ]
        msgs = []
        for k, v in sets.items():
            if len(str(table)) > 1500:
                table.rows.sort("Name", reverse=False)
                msgs.append(box(str(table) + f"\nPage {len(msgs) + 1}", lang="ansi"))
                table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
                table.set_style(BeautifulTable.STYLE_RST)
                table.columns.header = [
                    "Name",
                    "Unique Pieces",
                    "Unique Owned",
                ]
            table.rows.append(
                (
                    k,
                    f"{v[0]}",
                    f" {v[1]}" if v[1] == v[0] else ANSITextColours.red.as_str(v[1]),
                )
            )
        table.rows.sort("Name", reverse=False)
        msgs.append(box(str(table) + f"\nPage {len(msgs) + 1}", lang="ansi"))
        await BaseMenu(
            source=SimpleSource(msgs),
            delete_message_after=True,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @commands.command(name="apayday", cooldown_after_parsing=True)
    @has_separated_economy()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def commands_apayday(self, ctx: commands.Context):
        """Get some free gold."""
        author = ctx.author
        adventure_credits_name = await bank.get_currency_name(ctx.guild)
        amount = 500  # Make Customizable?
        try:
            await bank.deposit_credits(author, amount)
        except BalanceTooHigh as exc:
            await bank.set_balance(author, exc.max_balance)
            await smart_embed(
                ctx,
                _(
                    "You're struggling to move under the weight of all your {currency}!"
                    "Please spend some more \N{GRIMACING FACE}\n\n"
                    "You currently have {new_balance} {currency}."
                ).format(currency=adventure_credits_name, new_balance=humanize_number(exc.max_balance)),
            )
        else:
            await smart_embed(
                ctx,
                _(
                    "You receive a letter by post from the town's courier! "
                    "{author}, you've gained some interest on your {currency}. "
                    "You've been paid +{amount} {currency}!\n\n"
                    "You currently have {new_balance} {currency}."
                ).format(
                    author=author.mention,
                    currency=adventure_credits_name,
                    amount=humanize_number(amount),  # Make customizable?
                    new_balance=humanize_number(await bank.get_balance(author)),
                ),
            )
        try:
            character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
        else:
            if character.last_currency_check + 600 < time.time() or character.bal > character.last_known_currency:
                character.last_known_currency = await bank.get_balance(ctx.author)
                character.last_currency_check = time.time()
                await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))

    # in economy since it affects the loot economy, might move later
    @commands.group()
    @commands.guild_only()
    @commands.is_owner()
    async def give(self, ctx: commands.Context):
        """[Owner] Commands to add things to players' inventories."""

    @give.command(name="item")
    async def _give_item(
        self, ctx: commands.Context, user: Union[discord.Member, discord.User], item_name: str, *, stats: Stats
    ):
        """[Owner] Adds a custom item to a specified member.

        Item names containing spaces must be enclosed in double quotes. `[p]give item @locastan
        "fine dagger" 1 att 1 charisma rare twohanded` will give a two handed .fine_dagger with 1
        attack and 1 charisma to locastan. if a stat is not specified it will default to 0, order
        does not matter.
        available stats are:
         - `attack` or `att`
         - `charisma` or `diplo`
         - `charisma` or `cha`
         - `intelligence` or `int`
         - `dexterity` or `dex`
         - `luck`
         - `rarity` (one of normal, rare, epic, legendary, set, forged, or event)
         - `degrade` (Set to -1 to never degrade on rebirths)
         - `level` (lvl)
         - `slot` (one of `head`, `neck`, `chest`, `gloves`, `belt`, `legs`, `boots`, `left`, `right`
         `ring`, `charm`, `twohanded`)

        `[p]give item @locastan "fine dagger" 1 att 1 charisma -1 degrade 100 level rare twohanded`
        """
        if item_name.isnumeric():
            return await smart_embed(ctx, _("Item names cannot be numbers."))
        item_name = re.sub(r"[^\w ]", "", item_name)
        if user is None:
            user = ctx.author
        new_item = {item_name: stats}
        item = Item.from_json(ctx, new_item)
        async with self.get_lock(user):
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            await c.add_to_backpack(item)
            await self.config.user(user).set(await c.to_json(ctx, self.config))
        await ctx.send(
            box(
                _("An item named {item} has been created and placed in {author}'s backpack.").format(
                    item=item, author=escape(user.display_name)
                ),
                lang="ansi",
            )
        )

    @give.command(name="loot")
    async def _give_loot(
        self,
        ctx: commands.Context,
        loot_type: RarityConverter,
        users: commands.Greedy[Union[discord.Member, discord.User]] = None,
        number: int = 1,
    ):
        """[Owner] Give treasure chest(s) to all specified users."""

        users = users or [ctx.author]
        loot_types = [
            Rarities.normal,
            Rarities.rare,
            Rarities.epic,
            Rarities.legendary,
            Rarities.ascended,
            Rarities.set,
        ]
        if loot_type not in loot_types:
            return await smart_embed(
                ctx,
                box(
                    ("Valid loot types: {loot_types}: " "ex. `{prefix}give loot normal @locastan` ").format(
                        prefix=ctx.prefix, loot_types=humanize_list([i.ansi for i in loot_types])
                    ),
                    lang="ansi",
                ),
            )
        if loot_type in [Rarities.legendary, Rarities.set, Rarities.ascended] and not await ctx.bot.is_owner(
            ctx.author
        ):
            return await smart_embed(ctx, _("You are not worthy to award legendary loot."))
        for user in users:
            async with self.get_lock(user):
                try:
                    c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                if loot_type is Rarities.rare:
                    c.treasure.rare += number
                elif loot_type is Rarities.epic:
                    c.treasure.epic += number
                elif loot_type is Rarities.legendary:
                    c.treasure.legendary += number
                elif loot_type is Rarities.ascended:
                    c.treasure.ascended += number
                elif loot_type is Rarities.set:
                    c.treasure.set += number
                else:
                    c.treasure.normal += number
                await self.config.user(user).set(await c.to_json(ctx, self.config))
                chests = c.treasure.ansi
                await ctx.send(
                    box(
                        _("{author} now owns {chests} chests.").format(
                            author=escape(user.display_name),
                            chests=chests,
                        ),
                        lang="ansi",
                    )
                )
