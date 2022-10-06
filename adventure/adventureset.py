# -*- coding: utf-8 -*-
import contextlib
import logging
import os
from typing import Union

import discord
from beautifultable import ALIGN_LEFT, BeautifulTable
from redbot.core import commands
from redbot.core.commands import get_dict_converter
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, box, humanize_list, humanize_number

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character
from .constants import ORDER
from .converters import DayConverter, PercentageConverter, parse_timedelta
from .helpers import has_separated_economy, smart_embed

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")

TaxesConverter = get_dict_converter(delims=[" ", ",", ";"])


def check_global_setting_admin():
    """
    Command decorator. If the bank is not global, it checks if the author is
    either a bot admin or has the manage_guild permission.
    """

    async def pred(ctx: commands.Context):
        author = ctx.author
        if not await bank.is_global():
            if not isinstance(ctx.channel, discord.abc.GuildChannel):
                return False
            if await ctx.bot.is_owner(author):
                return True
            if author == ctx.guild.owner:
                return True
            if ctx.channel.permissions_for(author).manage_guild:
                return True
            admin_role_ids = await ctx.bot.get_admin_role_ids(ctx.guild.id)
            for role in author.roles:
                if role.id in admin_role_ids:
                    return True
        else:
            return await ctx.bot.is_owner(author)

    return commands.check(pred)


class AdventureSetCommands(AdventureMixin):
    """This class will handle setting adventures settings."""

    @commands.group()
    @commands.guild_only()
    async def adventureset(self, ctx: commands.Context):
        """Setup various adventure settings."""

    @adventureset.command()
    @check_global_setting_admin()
    async def rebirthcost(self, ctx: commands.Context, percentage: float):
        """[Admin] Set what percentage of the user balance to charge for rebirths.

        Unless the user's balance is under 1k, users that rebirth will be left with the base of 1k credits plus the remaining credit percentage after the rebirth charge.
        """
        if percentage < 0 or percentage > 100:
            return await smart_embed(ctx, _("Percentage has to be between 0 and 100."))
        if not await bank.is_global():
            await self.config.guild(ctx.guild).rebirth_cost.set(percentage)
            await smart_embed(
                ctx,
                _("I will now charge {0:.0%} of the user's balance for a rebirth.").format(percentage / 100),
            )
        else:
            await self.config.rebirth_cost.set(percentage)
            await smart_embed(
                ctx,
                _("I will now charge {0:.0%} of the user's global balance for a rebirth.").format(percentage / 100),
            )

    @adventureset.command()
    @commands.admin_or_permissions(administrator=True)
    async def cartroom(self, ctx: commands.Context, room: discord.TextChannel = None):
        """[Admin] Lock carts to a specific text channel."""
        if room is None:
            await self.config.guild(ctx.guild).cartroom.set(None)
            return await smart_embed(ctx, _("Done, carts will be able to appear in any text channel the bot can see."))

        await self.config.guild(ctx.guild).cartroom.set(room.id)
        await smart_embed(ctx, _("Done, carts will only appear in {room.mention}.").format(room=room))

    @adventureset.group(name="locks")
    @commands.bot_has_permissions(add_reactions=True)
    @commands.admin_or_permissions(administrator=True)
    async def adventureset_locks(self, ctx: commands.Context):
        """[Admin] Reset Adventure locks."""

    @adventureset_locks.command(name="user")
    @commands.is_owner()
    async def adventureset_locks_user(self, ctx: commands.Context, users: commands.Greedy[discord.User]):
        """[Owner] Reset a multiple adventurers lock."""
        for user in users:
            lock = self.get_lock(user)
            with contextlib.suppress(Exception):
                lock.release()
        await ctx.tick()

    @adventureset.command(name="dailybonus")
    @commands.is_owner()
    async def adventureset_daily_bonus(self, ctx: commands.Context, day: DayConverter, percentage: PercentageConverter):
        """[Owner] Set the daily xp and currency bonus.

        **percentage** must be between 0% and 100%.
        """
        day_val, day_text = day
        async with self.config.daily_bonus.all() as daily_bonus_data:
            daily_bonus_data[day_val] = percentage
            self._daily_bonus = daily_bonus_data.copy()
        await smart_embed(
            ctx,
            _("Daily bonus for `{0}` has been set to: {1:.0%}").format(day_text.title(), percentage),
        )

    @commands.guild_only()
    @adventureset_locks.command(name="adventure")
    async def adventureset_locks_adventure(self, ctx: commands.Context):
        """[Admin] Reset the adventure game lock for the server."""
        while ctx.guild.id in self._sessions:
            del self._sessions[ctx.guild.id]
        await ctx.tick()

    @adventureset.command()
    @commands.is_owner()
    async def restrict(self, ctx: commands.Context):
        """[Owner] Set whether or not adventurers are restricted to one adventure at a time."""
        toggle = await self.config.restrict()
        await self.config.restrict.set(not toggle)
        await smart_embed(ctx, _("Adventurers restricted to one adventure at a time: {}").format(not toggle))

    @adventureset.command()
    @commands.is_owner()
    async def easymode(self, ctx: commands.Context):
        """[Owner] Set whether or not Adventure will be in easy mode.

        Easy mode gives less rewards, but monster information is shown.
        """
        toggle = await self.config.easy_mode()
        await self.config.easy_mode.set(not toggle)
        await smart_embed(
            ctx, _("Adventure easy mode is now {}.").format(bold(_("Enabled") if not toggle else _("Disabled")))
        )

    @adventureset.command()
    @commands.is_owner()
    async def sepcurrency(self, ctx: commands.Context):
        """[Owner] Toggle whether the currency should be separated from main bot currency."""
        toggle = await self.config.separate_economy()
        await self.config.separate_economy.set(not toggle)
        self._separate_economy = not toggle
        await smart_embed(
            ctx, _("Adventurer currency is: {}").format(bold(_("Separated") if not toggle else _("Unified")))
        )

    @adventureset.group(name="economy")
    @check_global_setting_admin()
    @commands.guild_only()
    @has_separated_economy()
    async def commands_adventureset_economy(self, ctx: commands.Context):
        """[Admin] Manages the adventure economy."""

    @commands_adventureset_economy.command(name="tax", usage="<gold,tax ...>")
    @commands.is_owner()
    async def commands_adventureset_economy_tax(self, ctx: commands.Context, *, taxes: TaxesConverter):
        """[Owner] Set the tax thresholds.

        **gold** must be positive
        **tax** must be between 0 and 1.

        Example: `[p]adventureset economy tax 10000,0.1 20000,0.2 ...`

        """
        new_taxes = {}
        for k, v in taxes.items():
            if int(k) >= 0 and 0 <= float(v) <= 1:
                new_taxes[k] = float(v)
        new_taxes = {k: v for k, v in sorted(new_taxes.items(), key=lambda item: item[1])}
        await self.config.tax_brackets.set(new_taxes)

        taxes = await self.config.tax_brackets()
        table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
        table.set_style(BeautifulTable.STYLE_RST)
        table.columns.header = ["Tax %", "Tax Threshold"]
        for k, v in taxes.items():
            table.rows.append((f"[{v:.2%}]", humanize_number(int(k))))
        table.rows.sort("Tax %", reverse=True)
        await smart_embed(
            ctx,
            box(
                str(table),
                lang="css",
            ),
        )

    @commands.is_owner()
    @commands_adventureset_economy.command(name="rate")
    async def commands_adventureset_economy_conversion_rate(self, ctx: commands.Context, rate_in: int, rate_out: int):
        """[Owner] Set how much 1 bank credit is worth in adventure.

        **rate_in**: Is how much gold you will get for 1 bank credit. Default is 10
        **rate_out**: Is how much gold is needed to convert to 1 bank credit. Default is 11
        """
        if rate_in < 0 or rate_out < 0:
            return await smart_embed(ctx, _("You are evil ... please DM me your phone number we need to hangout."))
        await self.config.to_conversion_rate.set(rate_in)
        await self.config.from_conversion_rate.set(rate_out)
        await smart_embed(
            ctx,
            _("1 {name} will be worth {rate_in} {a_name}.\n{rate_out} {a_name} will convert into 1 {name}").format(
                name=await bank.get_currency_name(ctx.guild, _forced=True),
                rate_in=humanize_number(rate_in),
                rate_out=humanize_number(rate_out),
                a_name=await bank.get_currency_name(ctx.guild),
            ),
        )

    @commands_adventureset_economy.command(name="maxwithdraw")
    async def commands_adventureset_economy_maxwithdraw(self, ctx: commands.Context, *, amount: int):
        """[Admin] Set how much players are allowed to withdraw."""
        if amount < 0:
            return await smart_embed(ctx, _("You are evil ... please DM me your phone number we need to hangout."))
        if await bank.is_global(_forced=True):
            await self.config.max_allowed_withdraw.set(amount)
        else:
            await self.config.guild(ctx.guild).max_allowed_withdraw.set(amount)
        await smart_embed(
            ctx,
            _(
                "Adventurers will be able to withdraw up to {amount} {name} from their adventure bank and deposit into their bot economy."
            ).format(
                name=await bank.get_currency_name(ctx.guild, _forced=True),
                amount=humanize_number(amount),
            ),
        )

    @commands_adventureset_economy.command(name="withdraw")
    async def commands_adventureset_economy_withdraw(self, ctx: commands.Context):
        """[Admin] Toggle whether users are allowed to withdraw from adventure currency to main currency."""

        if await bank.is_global(_forced=True):
            state = await self.config.disallow_withdraw()
            await self.config.disallow_withdraw.set(not state)
        else:
            state = await self.config.guild(ctx.guild).disallow_withdraw()
            await self.config.guild(ctx.guild).disallow_withdraw.set(not state)

        await smart_embed(
            ctx,
            _("Adventurers are now {state} to withdraw money from adventure currency.").format(
                state=_("allowed") if not state else _("disallowed")
            ),
        )

    @adventureset.command(name="advcooldown", hidden=True)
    @commands.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def advcooldown(self, ctx: commands.Context, *, time_in_seconds: int):
        """[Admin] Changes the cooldown/gather time after an adventure.

        Default is 120 seconds.
        """
        if time_in_seconds < 30:
            return await smart_embed(ctx, _("Cooldown cannot be set to less than 30 seconds."))

        await self.config.guild(ctx.guild).cooldown_timer_manual.set(time_in_seconds)
        await smart_embed(
            ctx,
            _("Adventure cooldown set to {cooldown} seconds.").format(cooldown=time_in_seconds),
        )

    @adventureset.command()
    async def version(self, ctx: commands.Context):
        """Display the version of adventure being used."""
        await ctx.send(box(_("Adventure version: {}").format(self.__version__)))

    @adventureset.command()
    @commands.admin_or_permissions(administrator=True)
    async def god(self, ctx: commands.Context, *, name):
        """[Admin] Set the server's name of the god."""
        await self.config.guild(ctx.guild).god_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @commands.is_owner()
    async def globalgod(self, ctx: commands.Context, *, name):
        """[Owner] Set the default name of the god."""
        await self.config.god_name.set(name)
        await ctx.tick()

    @adventureset.command(aliases=["embed"])
    @commands.admin_or_permissions(administrator=True)
    async def embeds(self, ctx: commands.Context):
        """[Admin] Set whether or not to use embeds for the adventure game."""
        toggle = await self.config.guild(ctx.guild).embed()
        await self.config.guild(ctx.guild).embed.set(not toggle)
        await smart_embed(ctx, _("Embeds: {}").format(not toggle))

    @adventureset.command(aliases=["chests"], enabled=False, hidden=True)
    @commands.is_owner()
    async def cartchests(self, ctx: commands.Context):
        """[Admin] Set whether or not to sell chests in the cart."""
        toggle = await self.config.enable_chests()
        await self.config.enable_chests.set(not toggle)
        await smart_embed(ctx, _("Carts can sell chests: {}").format(not toggle))

    @adventureset.command()
    @commands.admin_or_permissions(administrator=True)
    async def cartname(self, ctx: commands.Context, *, name):
        """[Admin] Set the server's name of the cart."""
        await self.config.guild(ctx.guild).cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @commands.admin_or_permissions(administrator=True)
    async def carttime(self, ctx: commands.Context, *, time: str):
        """
        [Admin] Set the cooldown of the cart.
        Time can be in seconds, minutes, hours, or days.
        Examples: `1h 30m`, `2 days`, `300 seconds`
        """
        time_delta = parse_timedelta(time)
        if time_delta is None:
            return await smart_embed(ctx, _("You must supply a amount and time unit like `120 seconds`."))
        if time_delta.total_seconds() < 600:
            cartname = await self.config.guild(ctx.guild).cart_name()
            if not cartname:
                cartname = await self.config.cart_name()
            return await smart_embed(
                ctx, _("{} doesn't have the energy to return that often. Try 10 minutes or more.").format(cartname)
            )
        await self.config.guild(ctx.guild).cart_timeout.set(int(time_delta.total_seconds()))
        await ctx.tick()

    @adventureset.command(name="clear")
    @commands.is_owner()
    async def clear_user(self, ctx: commands.Context, users: commands.Greedy[discord.User]):
        """[Owner] Lets you clear multiple users character sheets."""
        for user in users:
            await self.config.user(user).clear()
            await smart_embed(ctx, _("{user}'s character sheet has been erased.").format(user=user))

    @adventureset.command(name="remove")
    @commands.is_owner()
    async def remove_item(
        self, ctx: commands.Context, user: Union[discord.Member, discord.User], *, full_item_name: str
    ):
        """[Owner] Lets you remove an item from a user.

        Use the full name of the item including the rarity characters like . or []  or {}.
        """
        async with self.get_lock(user):
            item = None
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            for slot in ORDER:
                if slot == "two handed":
                    continue
                equipped_item = getattr(c, slot)
                if equipped_item and equipped_item.name.lower() == full_item_name.lower():
                    item = equipped_item
            if item:
                with contextlib.suppress(Exception):
                    await c.unequip_item(item)
            else:
                try:
                    item = c.backpack[full_item_name]
                except KeyError:
                    return await smart_embed(
                        ctx, _("{} does not have an item named `{}`.").format(bold(user), full_item_name)
                    )
            with contextlib.suppress(KeyError):
                del c.backpack[item.name]
            await self.config.user(user).set(await c.to_json(self.config))
        await ctx.send(_("{item} removed from {user}.").format(item=box(str(item), lang="css"), user=bold(user)))

    @adventureset.command()
    @commands.is_owner()
    async def globalcartname(self, ctx: commands.Context, *, name):
        """[Owner] Set the default name of the cart."""
        await self.config.cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @commands.is_owner()
    async def theme(self, ctx: commands.Context, *, theme):
        """[Owner] Change the theme for adventure.

        The default theme is `default`.
        """
        if theme == "default":
            await self.config.theme.set("default")
            await smart_embed(ctx, _("Going back to the default theme."))
            await self.initialize()
            return
        if theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        good_files = [
            "as_monsters.json",
            "attribs.json",
            "locations.json",
            "monsters.json",
            "pets.json",
            "raisins.json",
            "threatee.json",
            "tr_set.json",
            "prefixes.json",
            "materials.json",
            "equipment.json",
            "suffixes.json",
            "set_bonuses.json",
        ]
        missing_files = list(set(good_files).difference(os.listdir(cog_data_path(self) / theme)))

        if missing_files:
            await smart_embed(
                ctx,
                _("That theme pack is missing the following files: {}.").format(humanize_list(missing_files)),
            )
            return
        else:
            await self.config.theme.set(theme)
            await ctx.tick()
        await self.initialize()

    @adventureset.command()
    @commands.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def cart(self, ctx: commands.Context, *, channel: discord.TextChannel = None):
        """[Admin] Add or remove a text channel that the Trader cart can appear in.

        If the channel is already in the list, it will be removed.
        Use `[p]adventureset cart` with no arguments to show the channel list.
        """

        channel_list = await self.config.guild(ctx.guild).cart_channels()
        if not channel_list:
            channel_list = []
        if channel is None:
            msg = _("Active Cart Channels:\n")
            if not channel_list:
                msg += _("None.")
            else:
                name_list = []
                for chan_id in channel_list:
                    name_list.append(self.bot.get_channel(chan_id))
                msg += "\n".join(chan.name for chan in name_list)
            return await ctx.send(box(msg))
        elif channel.id in channel_list:
            new_channels = channel_list.remove(channel.id)
            await smart_embed(
                ctx,
                _("The {} channel has been removed from the cart delivery list.").format(channel),
            )
            return await self.config.guild(ctx.guild).cart_channels.set(new_channels)
        else:
            channel_list.append(channel.id)
            await smart_embed(ctx, _("The {} channel has been added to the cart delivery list.").format(channel))
            await self.config.guild(ctx.guild).cart_channels.set(channel_list)

    @commands.guild_only()
    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.guild)
    async def adventuresettings(self, ctx: commands.Context):
        """Display current settings."""
        global_data = await self.config.all()
        guild_data = await self.config.guild(ctx.guild).all()
        is_owner = await self.bot.is_owner(ctx.author)
        theme = global_data["theme"]
        god_name = global_data["god_name"] if not guild_data["god_name"] else guild_data["god_name"]
        cart_trader_name = global_data["cart_name"] if not guild_data["cart_name"] else guild_data["cart_name"]

        cart_channel_ids = guild_data["cart_channels"]
        if cart_channel_ids:
            cart_channels = humanize_list([f"{self.bot.get_channel(x).name}" for x in cart_channel_ids])
        else:
            cart_channels = _("None")

        cart_channel_lock_override_id = guild_data["cartroom"]
        if cart_channel_lock_override_id:
            cclo_channel_obj = self.bot.get_channel(cart_channel_lock_override_id)
            cart_channel_lock_override = f"{cclo_channel_obj.name}"
        else:
            cart_channel_lock_override = _("No channel lock present.")

        cart_timeout = parse_timedelta(f"{guild_data['cart_timeout']} seconds")
        # lootbox_in_carts = _("Allowed") if global_data["enable_chests"] else _("Not allowed")

        if not await bank.is_global():
            rebirth_cost = guild_data["rebirth_cost"]
        else:
            rebirth_cost = global_data["rebirth_cost"]
        rebirth_cost = _("{0:.0%} of bank balance").format(rebirth_cost / 100)

        single_adventure_restrict = _("Restricted") if global_data["restrict"] else _("Unlimited")
        adventure_in_embed = _("Allow embeds") if guild_data["embed"] else _("No embeds")
        time_after_adventure = parse_timedelta(f"{guild_data['cooldown_timer_manual']} seconds")

        separate_economy = global_data["separate_economy"]
        economy_string = _("\n# Economy Settings\n")
        economy_string += _("[Separated Currency]:                   {state}\n").format(
            state=_("Enabled") if separate_economy else _("Disabled")
        )

        if separate_economy:
            main_currency_name = await bank.get_currency_name(ctx.guild, _forced=True)
            adv_currency_name = await bank.get_currency_name(ctx.guild)
            if await bank.is_global(_forced=True):
                withdraw_state = global_data["disallow_withdraw"]
                max_allowed_withdraw = global_data["max_allowed_withdraw"]

            else:
                withdraw_state = guild_data["disallow_withdraw"]
                max_allowed_withdraw = guild_data["max_allowed_withdraw"]
            economy_string += _("[Withdraw to Bank]:                     {state}\n").format(
                state=_("Allowed") if withdraw_state else _("Disallowed")
            )
            if withdraw_state:
                economy_string += _("[Max withdraw allowed]:                 {state}\n").format(
                    state=humanize_number(max_allowed_withdraw)
                )
            to_conversion_rate = global_data["to_conversion_rate"]
            from_conversion_rate = global_data["from_conversion_rate"]

            economy_string += _(
                "[Bank to Adventure conversion rate]:    1 {main_name} will be worth {ratio} {adventure_name}\n"
            ).format(
                main_name=main_currency_name,
                ratio=1 * to_conversion_rate,
                adventure_name=adv_currency_name,
            )
            economy_string += _(
                "[Adventure to bank conversion rate]:    {ratio} {adventure_name} will be worth 1 {main_name}\n"
            ).format(
                main_name=main_currency_name,
                ratio=from_conversion_rate,
                adventure_name=adv_currency_name,
            )
            if is_owner:
                economy_string += _("\n# Tax Settings\n")
                taxes = global_data["tax_brackets"]
                for cur, tax in sorted(taxes.items(), key=lambda x: x[1]):
                    economy_string += _("[{tax:06.2%}]:                               {currency}\n").format(
                        tax=tax, currency=humanize_number(int(cur))
                    )

        daily_bonus = global_data["daily_bonus"]
        daily_bonus_string = "\n# Daily Bonuses\n"
        daily_bonus_string += _("[Monday]:                               {v:.2%}\n").format(v=daily_bonus.get("1", 0))
        daily_bonus_string += _("[Tuesday]:                              {v:.2%}\n").format(v=daily_bonus.get("2", 0))
        daily_bonus_string += _("[Wednesday]:                            {v:.2%}\n").format(v=daily_bonus.get("3", 0))
        daily_bonus_string += _("[Thursday]:                             {v:.2%}\n").format(v=daily_bonus.get("4", 0))
        daily_bonus_string += _("[Friday]:                               {v:.2%}\n").format(v=daily_bonus.get("5", 0))
        daily_bonus_string += _("[Saturday]:                             {v:.2%}\n").format(v=daily_bonus.get("6", 0))
        daily_bonus_string += _("[Sunday]:                               {v:.2%}\n").format(v=daily_bonus.get("7", 0))

        easy_mode = global_data["easy_mode"]
        msg = _("Adventure Settings\n\n")
        msg += _("# Main Settings\n")
        msg += _("[Easy Mode]:                            {state}\n").format(
            state=_("Enabled") if easy_mode else _("Disabled")
        )
        msg += _("[Theme]:                                {theme}\n").format(theme=theme)
        msg += _("[God name]:                             {god_name}\n").format(god_name=god_name)
        msg += _("[Base rebirth cost]:                    {rebirth_cost}\n").format(rebirth_cost=rebirth_cost)
        msg += _("[Adventure message style]:              {adventure_in_embed}\n").format(
            adventure_in_embed=adventure_in_embed
        )
        msg += _("[Multi-adventure restriction]:          {single_adventure_restrict}\n").format(
            single_adventure_restrict=single_adventure_restrict
        )
        msg += _("[Post-adventure cooldown (hh:mm:ss)]:   {time_after_adventure}\n\n").format(
            time_after_adventure=time_after_adventure
        )
        msg += _("# Cart Settings\n")
        msg += _("[Cart trader name]:                     {cart_trader_name}\n").format(
            cart_trader_name=cart_trader_name
        )
        msg += _("[Cart delivery channels]:               {cart_channels}\n").format(cart_channels=cart_channels)
        msg += _("[Cart channel lock override]:           {cart_channel_lock_override}\n").format(
            cart_channel_lock_override=cart_channel_lock_override
        )
        msg += _("[Cart timeout (hh:mm:ss)]:              {cart_timeout}\n").format(cart_timeout=cart_timeout)
        # msg += _("[Lootboxes in carts]:                   {lootbox_in_carts}\n").format(
        #     lootbox_in_carts=lootbox_in_carts
        # )
        msg += economy_string
        msg += daily_bonus_string
        if is_owner:
            with contextlib.suppress(discord.HTTPException):
                await ctx.author.send(box(msg, lang="ini"))
        else:
            await ctx.send(box(msg, lang="ini"))
