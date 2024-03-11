from __future__ import annotations

import random
import re
import time
from enum import Enum
from typing import TYPE_CHECKING, Optional, Union

import discord
from discord.ext.commands import CheckFailure
from redbot.core.commands import Cog, Context, check
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape as _escape
from redbot.core.utils.common_filters import filter_various_mentions

from .charsheet import Character, Item
from .constants import DEV_LIST, Rarities

_ = Translator("Adventure", __file__)

if TYPE_CHECKING:
    from .abc import AdventureMixin


async def _get_epoch(seconds: int):
    epoch = time.time()
    epoch += seconds
    return epoch


def escape(t: str) -> str:
    return _escape(filter_various_mentions(t), mass_mentions=True, formatting=True)


async def smart_embed(
    ctx: Optional[Context] = None,
    message: Optional[str] = None,
    success: Optional[bool] = None,
    image: Optional[str] = None,
    ephemeral: bool = False,
    cog: Optional[AdventureMixin] = None,
    interaction: Optional[discord.Interaction] = None,
    view: Optional[discord.ui.View] = discord.utils.MISSING,
    embed_colour: Optional[str] = None,
) -> discord.Message:
    interaction_only = interaction is not None and ctx is None
    if interaction_only:
        bot = interaction.client
        guild = interaction.guild
        channel = interaction.channel
    else:
        bot = ctx.bot
        guild = ctx.guild
        channel = ctx.channel
    if success is True:
        colour = discord.Colour.dark_green()
    elif success is False:
        colour = discord.Colour.dark_red()
    elif embed_colour is not None:
        try:
            colour = discord.Colour.from_str(embed_colour)
        except (ValueError, TypeError):
            colour = await bot.get_embed_colour(channel)
    else:
        colour = await bot.get_embed_colour(channel)

    if cog is None:
        cog = bot.get_cog("Adventure")
    if guild:
        use_embeds = await cog.config.guild(guild).embed()
    else:
        use_embeds = True or await bot.embed_requested(channel)
    if use_embeds:
        embed = discord.Embed(description=message, color=colour)
        if image:
            embed.set_thumbnail(url=image)
        if interaction_only:
            if interaction.response.is_done():
                msg = await interaction.followup.send(embed=embed, ephemeral=ephemeral, view=view, wait=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral, view=view)
                msg = await interaction.original_response()
            return msg
        else:
            return await ctx.send(embed=embed, ephemeral=ephemeral, view=view)
    if interaction_only:
        if interaction.response.is_done():
            msg = await interaction.followup.send(message, ephemeral=ephemeral, view=view, wait=True)
        else:
            await interaction.response.send_message(message, ephemeral=ephemeral, view=view)
            msg = await interaction.original_response()
        return msg
    else:
        return await ctx.send(message, ephemeral=ephemeral, view=view)


def check_running_adventure(ctx):
    for guild_id, session in ctx.bot.get_cog("Adventure")._sessions.items():
        user_ids: list = []
        options = ["fight", "magic", "talk", "pray", "run"]
        for i in options:
            user_ids += [u.id for u in getattr(session, i)]
        if ctx.author.id in user_ids:
            return False
    return True


async def _title_case(phrase: str):
    exceptions = ["a", "and", "in", "of", "or", "the"]
    lowercase_words = re.split(" ", phrase.lower())
    final_words = [lowercase_words[0].capitalize()]
    final_words += [word if word in exceptions else word.capitalize() for word in lowercase_words[1:]]
    return " ".join(final_words)


async def _remaining(epoch):
    remaining = epoch - time.time()
    finish = remaining < 0
    m, s = divmod(remaining, 60)
    h, m = divmod(m, 60)
    s = int(s)
    m = int(m)
    h = int(h)
    if h == 0 and m == 0:
        out = "{:02d}".format(s)
    elif h == 0:
        out = "{:02d}:{:02d}".format(m, s)
    else:
        out = "{:01d}:{:02d}:{:02d}".format(h, m, s)
    return (out, finish, remaining)


def _sell(c: Character, item: Item, *, amount: int = 1):
    if item.rarity is Rarities.ascended:
        base = (5000, 10000)
    elif item.rarity is Rarities.legendary:
        base = (1000, 2000)
    elif item.rarity is Rarities.epic:
        base = (500, 750)
    elif item.rarity is Rarities.rare:
        base = (250, 500)
    else:
        base = (10, 100)
    price = random.randint(base[0], base[1]) * abs(item.max_main_stat)
    price += price * max(int((c.total_cha) / 1000), -1)

    if c.luck > 0:
        price = price + round(price * (c.luck / 1000))
    if c.luck < 0:
        price = price - round(price * (abs(c.luck) / 1000))
    if price < 0:
        price = 0
    price += round(price * min(0.1 * c.rebirths / 15, 0.4))

    return max(price, base[0])


def is_dev(user: Union[discord.User, discord.Member]):
    return user.id in DEV_LIST


def has_separated_economy():
    async def predicate(ctx):
        if not (ctx.cog and getattr(ctx.cog, "_separate_economy", False)):
            raise CheckFailure
        return True

    return check(predicate)


class ConfirmView(discord.ui.View):
    def __init__(self, timeout: float, author: Union[discord.User, discord.Member], *, get_name: bool = False):
        super().__init__(timeout=timeout)
        self.confirmed = None
        self.author = author
        self.message: Optional[discord.Message] = None
        self.name_button = ForgeNameButton()
        self.item_name = None
        if get_name:
            self.add_item(self.name_button)

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=None)

    @discord.ui.button(label=_("Yes"), style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.confirmed = True
        self.stop()

    @discord.ui.button(label=_("No"), style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.confirmed = False
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("You are not authorized to interact with this."), ephemeral=True)
            return False
        return True


class NameModal(discord.ui.Modal):
    def __init__(self, view: discord.ui.View):
        super().__init__(title=_("Name your new item"))
        self.name = discord.ui.TextInput(
            label=_("Item Name"),
            max_length=40,
            placeholder=_("Enter the new item's name"),
        )
        self.add_item(self.name)
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.item_name = self.name.value
        self.view.confirmed = True
        self.view.stop()


class ForgeNameButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.green, label=_("Change Name"), row=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(NameModal(self.view))


class LootSellEnum(Enum):
    put_away = 0
    equip = 1
    sell = 2


class LootView(discord.ui.View):
    def __init__(self, timeout: float, author: discord.User):
        super().__init__(timeout=timeout)
        self.result = LootSellEnum.put_away
        self.author = author

    @discord.ui.button(label=_("Equip"), style=discord.ButtonStyle.green)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.result = LootSellEnum.equip
        self.stop()

    @discord.ui.button(label=_("Sell"), style=discord.ButtonStyle.red)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.result = LootSellEnum.sell
        self.stop()

    @discord.ui.button(label=_("Put away"), style=discord.ButtonStyle.grey)
    async def putaway_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.result = LootSellEnum.put_away
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("You are not authorized to interact with this."), ephemeral=True)
            return False
        return True
