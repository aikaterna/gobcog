# -*- coding: utf-8 -*-
import contextlib
import logging
import random
import time
from datetime import datetime
from typing import Optional, Union

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, box, humanize_number

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character
from .constants import Treasure
from .helpers import ConfirmView, escape, is_dev, smart_embed

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class Negaverse(AdventureMixin):
    """This class will handle negaverse interactions"""

    @commands.hybrid_command(name="negaverse", aliases=["nv"], cooldown_after_parsing=True)
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    @commands.guild_only()
    async def _negaverse_command(self, ctx: commands.Context, offering: int):
        """This will send you to fight a nega-member!"""
        await self._negaverse(ctx, offering)

    async def _negaverse(
        self,
        ctx: commands.Context,
        offering: Optional[int] = None,
        roll: int = -1,
        nega: Optional[discord.Member] = None,
    ):
        """This will send you to fight a nega-member!"""
        if self.in_adventure(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("You tried to teleport to another dimension but the monster ahead did not give you a chance."),
                ephemeral=True,
            )

        bal = await bank.get_balance(ctx.author)
        currency_name = await bank.get_currency_name(
            ctx.guild,
        )
        if offering is None:
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _(
                    "{author}, you need to specify how many "
                    "{currency_name} you are willing to offer to the gods for your success."
                ).format(author=escape(ctx.author.display_name), currency_name=currency_name),
                ephemeral=True,
            )
        if offering <= 500 or bal <= 500:
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(ctx, _("The gods refuse your pitiful offering."), ephemeral=True)
        await ctx.defer()
        if offering > bal:
            offering = int(bal)
        admin_roll = -1
        nega_set = False
        if (roll >= 0 or nega) and await self.bot.is_owner(ctx.author):
            if not is_dev(ctx.author):
                if not await self.no_dev_prompt(ctx):
                    ctx.command.reset_cooldown(ctx)
                    return
            nega_set = True
            admin_roll = roll
        offering_value = 0
        winning_state = False
        loss_state = False
        xp_won_final = 0
        lock = self.get_lock(ctx.author)
        await lock.acquire()
        view = ConfirmView(timeout=60, author=ctx.author)
        try:
            nv_msg = await ctx.send(
                _(
                    "{author}, this will cost you at least {offer} {currency_name}.\n"
                    "You currently have {bal}. Do you want to proceed?"
                ).format(
                    author=bold(ctx.author.display_name),
                    offer=humanize_number(offering),
                    currency_name=currency_name,
                    bal=humanize_number(bal),
                ),
                view=view,
            )
            await view.wait()
            if not view.confirmed:
                with contextlib.suppress(discord.HTTPException):
                    ctx.command.reset_cooldown(ctx)
                    await nv_msg.edit(
                        content=_("**{}** decides against visiting the negaverse... for now.").format(
                            escape(ctx.author.display_name)
                        ),
                        view=None,
                    )
                    lock.release()
                    return await self._clear_react(nv_msg)

            percentage_offered = (offering / bal) * 100
            min_roll = int(percentage_offered / 10)
            entry_roll = max(random.randint(max(1, min_roll), 20), 0) if admin_roll == -1 else admin_roll
            if entry_roll == 1:
                tax_mod = random.randint(4, 8)
                tax = round(bal / tax_mod)
                if tax > offering:
                    loss = tax
                else:
                    loss = offering
                offering_value += loss
                loss_state = True
                await bank.withdraw_credits(ctx.author, loss)
                entry_msg = _(
                    "A swirling void slowly grows and you watch in horror as it rushes to "
                    "wash over you, leaving you cold... and your coin pouch significantly lighter. "
                    "The portal to the negaverse remains closed."
                )
                lock.release()
                return await nv_msg.edit(content=entry_msg, view=None)
            else:
                entry_msg = _(
                    "Shadowy hands reach out to take your offering from you and a swirling "
                    "black void slowly grows and engulfs you, transporting you to the negaverse."
                )
                await nv_msg.edit(content=entry_msg, view=None)
                await self._clear_react(nv_msg)
                await bank.withdraw_credits(ctx.author, offering)
            if nega_set:
                nega_member = nega
                negachar = _("The Almighty Nega-{c}").format(c=nega_member.display_name)
            else:
                nega_member = random.choice(ctx.message.guild.members)
                negachar = _("Nega-{c}").format(c=nega_member.display_name)

            nega_msg = await ctx.send(
                _("{author} enters the negaverse and meets {negachar}.").format(
                    author=bold(ctx.author.display_name), negachar=bold(negachar)
                )
            )

            try:
                character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                lock.release()
                ctx.command.reset_cooldown(ctx)
                return
            roll = random.randint(max(1, min_roll * 2), 50) if admin_roll == -1 else admin_roll
            if is_dev(nega_member):
                roll = -2
            versus = random.randint(10, 60)
            xp_mod = random.randint(1, 10)
            daymult = self._daily_bonus.get(str(datetime.today().isoweekday()), 0)
            xp_won = int((offering / xp_mod))
            xp_to_max = int((character.maxlevel + 1) ** 3.5)
            ten_percent = xp_to_max * 0.1
            xp_won = ten_percent if xp_won > ten_percent else xp_won
            xp_won = int(xp_won * (min(max(random.randint(0, character.rebirths), 1), 50) / 100 + 1))
            xp_won = int(xp_won * (character.gear_set_bonus.get("xpmult", 1) + daymult))
            if roll == -2:
                looted = ""
                curr_balance = character.bal
                await bank.set_balance(ctx.author, 0)
                offering_value += curr_balance
                loss_string = _("all of their")
                loss_state = True
                items = await character.looted(
                    how_many=max(int(10 - roll) // 2, 1), exclude={"event", "normal", "rare", "epic"}
                )
                if items:
                    item_string = "\n".join([f"{v} x{i}" for v, i in items])
                    looted = box(f"{item_string}", lang="ansi")
                    await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
                loss_msg = _(", losing {loss} {currency_name} as {negachar} rifled through their belongings.").format(
                    loss=loss_string, currency_name=currency_name, negachar=bold(negachar)
                )
                if looted:
                    loss_msg += _(" {negachar} also stole the following items:\n\n{items}").format(
                        items=looted, negachar=bold(negachar)
                    )
                await nega_msg.edit(
                    content=_("{content}\n{author} fumbled and died to {negachar}'s savagery{loss_msg}").format(
                        content=nega_msg.content,
                        author=bold(ctx.author.display_name),
                        negachar=bold(negachar),
                        loss_msg=loss_msg,
                    ),
                    view=None,
                )
                ctx.command.reset_cooldown(ctx)
            elif roll < 10:
                loss = round(bal // 3)
                looted = ""
                curr_balance = character.bal
                try:
                    await bank.withdraw_credits(ctx.author, loss)
                    offering_value += loss
                    loss_string = humanize_number(loss)
                except ValueError:
                    await bank.set_balance(ctx.author, 0)
                    offering_value += curr_balance
                    loss_string = _("all of their")
                loss_state = True
                if character.bal < loss:
                    items = await character.looted(
                        how_many=max(int(10 - roll) // 2, 1), exclude={"event", "normal", "rare", "epic"}
                    )
                    if items:
                        item_string = "\n".join([f"{v} {i}" for v, i in items])
                        looted = box(f"{item_string}", lang="ansi")
                        await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
                loss_msg = _(", losing {loss} {currency_name} as {negachar} rifled through their belongings.").format(
                    loss=loss_string, currency_name=currency_name, negachar=bold(negachar)
                )
                if looted:
                    loss_msg += _(" {negachar} also stole the following items:\n\n{items}").format(
                        items=looted, negachar=bold(negachar)
                    )
                await nega_msg.edit(
                    content=_("{content}\n{author} fumbled and died to {negachar}'s savagery{loss_msg}").format(
                        content=nega_msg.content,
                        author=bold(ctx.author.display_name),
                        negachar=bold(negachar),
                        loss_msg=loss_msg,
                    ),
                    view=None,
                )
                ctx.command.reset_cooldown(ctx)
            elif roll == 50 and versus < 50:
                await nega_msg.edit(
                    content=_(
                        "{content}\n{author} decapitated {negachar}. "
                        "You gain {xp_gain} xp and take "
                        "{offering} {currency_name} back from the shadowy corpse."
                    ).format(
                        content=nega_msg.content,
                        author=bold(ctx.author.display_name),
                        negachar=bold(negachar),
                        xp_gain=humanize_number(xp_won),
                        offering=humanize_number(offering),
                        currency_name=currency_name,
                    ),
                    view=None,
                )
                with contextlib.suppress(Exception):
                    lock.release()
                msg = await self._add_rewards(ctx, ctx.author, xp_won, offering, Treasure())
                xp_won_final += xp_won
                offering_value += offering
                winning_state = True
                if msg:
                    await smart_embed(ctx, msg, success=True)
            elif roll > versus:
                await nega_msg.edit(
                    content=_(
                        "{content}\n{author} "
                        "{dice}({roll}) bravely defeated {negachar} {dice}({versus}). "
                        "You gain {xp_gain} xp."
                    ).format(
                        dice=self.emojis.dice,
                        content=nega_msg.content,
                        author=bold(ctx.author.display_name),
                        roll=roll,
                        negachar=bold(negachar),
                        versus=versus,
                        xp_gain=humanize_number(xp_won),
                    ),
                    view=None,
                )
                with contextlib.suppress(Exception):
                    lock.release()
                msg = await self._add_rewards(ctx, ctx.author, xp_won, 0, Treasure())
                xp_won_final += xp_won
                offering_value += offering
                winning_state = True
                if msg:
                    await smart_embed(ctx, msg, success=True)
            elif roll == versus:
                ctx.command.reset_cooldown(ctx)
                await nega_msg.edit(
                    content=_("{content}\n{author} {dice}({roll}) almost killed {negachar} {dice}({versus}).").format(
                        dice=self.emojis.dice,
                        content=nega_msg.content,
                        author=bold(ctx.author.display_name),
                        roll=roll,
                        negachar=bold(negachar),
                        versus=versus,
                    ),
                    view=None,
                )
            else:
                loss = round(bal / (random.randint(10, 25)))
                curr_balance = character.bal
                looted = ""
                try:
                    await bank.withdraw_credits(ctx.author, loss)
                    offering_value += loss
                    loss_string = humanize_number(loss)
                except ValueError:
                    await bank.set_balance(ctx.author, 0)
                    loss_string = _("all of their")
                    offering_value += curr_balance
                loss_state = True
                if character.bal < loss:
                    items = await character.looted(
                        how_many=max(int(10 - roll) // 2, 1), exclude={"event", "normal", "rare", "epic"}
                    )
                    if items:
                        item_string = "\n".join([f"{i}  - {v}" for v, i in items])
                        looted = box(f"{item_string}", lang="ansi")
                        await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))
                loss_msg = _(", losing {loss} {currency_name} as {negachar} looted their backpack.").format(
                    loss=loss_string,
                    currency_name=currency_name,
                    negachar=bold(negachar),
                )
                if looted:
                    loss_msg += _(" {negachar} also stole the following items:\n\n{items}").format(
                        items=looted, negachar=bold(negachar)
                    )
                await nega_msg.edit(
                    content=_("{author} {dice}({roll}) was killed by {negachar} {dice}({versus}){loss_msg}").format(
                        dice=self.emojis.dice,
                        author=bold(ctx.author.display_name),
                        roll=roll,
                        negachar=bold(negachar),
                        versus=versus,
                        loss_msg=loss_msg,
                    ),
                    view=None,
                )
                ctx.command.reset_cooldown(ctx)
        finally:
            lock = self.get_lock(ctx.author)
            with contextlib.suppress(Exception):
                lock.release()
            try:
                character = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
            else:
                changed = False
                if character.last_currency_check + 600 < time.time() or character.bal > character.last_known_currency:
                    character.last_known_currency = await bank.get_balance(ctx.author)
                    character.last_currency_check = time.time()
                    changed = True
                if offering_value > 0:
                    current_gold__losses_value = character.nega.get("gold__losses", 0)
                    character.nega.update({"gold__losses": int(current_gold__losses_value + offering_value)})
                    changed = True
                if xp_won_final > 0:
                    current_xp__earnings_value = character.nega.get("xp__earnings", 0)
                    character.nega.update({"xp__earnings": current_xp__earnings_value + xp_won_final})
                    changed = True
                if winning_state is not False:
                    current_wins_value = character.nega.get("wins", 0)
                    character.nega.update({"wins": current_wins_value + 1})
                    changed = True
                if loss_state is not False:
                    current_loses_value = character.nega.get("loses", 0)
                    character.nega.update({"loses": current_loses_value + 1})
                    changed = True

                if changed:
                    await self.config.user(ctx.author).set(await character.to_json(ctx, self.config))

    @_negaverse_command.error
    async def negaverse_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            currency_name = await bank.get_currency_name(
                ctx.guild,
            )
            return await smart_embed(
                ctx,
                _(
                    "**{author}**, you need to specify how many "
                    "{currency_name} you are willing to offer to the gods for your success."
                ).format(author=escape(ctx.author.display_name), currency_name=currency_name),
            )
        else:
            await ctx.bot.on_command_error(ctx, error, unhandled_by_cog=True)
