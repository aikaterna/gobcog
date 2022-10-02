import random
import re
import time
from typing import Union

import discord
from discord.ext.commands import CheckFailure
from redbot.core.commands import check
from redbot.core.utils.chat_formatting import escape as _escape
from redbot.core.utils.common_filters import filter_various_mentions

from .charsheet import Character, Item
from .constants import DEV_LIST


async def _get_epoch(seconds: int):
    epoch = time.time()
    epoch += seconds
    return epoch


def escape(t: str) -> str:
    return _escape(filter_various_mentions(t), mass_mentions=True, formatting=True)


async def smart_embed(ctx, message, success=None, image=None):
    if ctx.guild:
        use_embeds = await ctx.cog.config.guild(ctx.guild).embed()
    else:
        use_embeds = True
    if use_embeds:
        if await ctx.embed_requested():
            if success is True:
                colour = discord.Colour.dark_green()
            elif success is False:
                colour = discord.Colour.dark_red()
            else:
                colour = await ctx.embed_colour()
            embed = discord.Embed(description=message, color=colour)
            if image:
                embed.set_thumbnail(url=image)
            return await ctx.send(embed=embed)
        else:
            return await ctx.send(message)
    return await ctx.send(message)


def check_running_adventure(ctx):
    for (guild_id, session) in ctx.bot.get_cog("Adventure")._sessions.items():
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
    if item.rarity == "ascended":
        base = (5000, 10000)
    elif item.rarity == "legendary":
        base = (1000, 2000)
    elif item.rarity == "epic":
        base = (500, 750)
    elif item.rarity == "rare":
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
