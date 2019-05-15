import asyncio
import discord
import json
import random
import time
import logging
import os
from typing import Optional

from redbot.core import commands, bank, checks, Config
from redbot.core.commands.context import Context
from redbot.core.errors import BalanceTooHigh
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.utils.chat_formatting import box, pagify, bold, humanize_list, escape
from redbot.core.utils.common_filters import filter_various_mentions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS, start_adding_reactions
from redbot.core.i18n import Translator, cog_i18n

from .charsheet import Character, Item, GameSession, Stats, parse_timedelta


BaseCog = getattr(commands, "Cog", object)

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.adventure")
listener = getattr(commands.Cog, "listener", None)

if listener is None:

    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class Adventure(BaseCog):
    """Adventure, derived from the Goblins Adventure cog by locastan"""

    __version__ = "2.3.1"

    def __init__(self, bot):
        self.bot = bot
        self._last_trade = {}

        self._adventure_actions = ["🗡", "✨", "🗨", "🛐", "🏃"]
        self._adventure_controls = {
            "fight": "🗡",
            "magic": "✨",
            "talk": "🗨",
            "pray": "🛐",
            "run": "🏃",
        }
        self._order = [
            "head",
            "neck",
            "chest",
            "gloves",
            "belt",
            "legs",
            "boots",
            "left",
            "right",
            "two handed",
            "ring",
            "charm",
        ]
        self._treasure_controls = {"✅": "equip", "❎": "backpack", "💰": "sell"}

        self._adventure_countdown = {}
        self._rewards = {}
        self._trader_countdown = {}
        self._current_traders = {}
        self._sessions = {}
        self.tasks = []
        self.locks = {}

        self.config = Config.get_conf(self, 2_710_801_001, force_registration=True)

        default_user = {
            "exp": 0,
            "lvl": 1,
            "att": 0,
            "cha": 0,
            "int": 0,
            "treasure": [0, 0, 0, 0],
            "items": {
                "head": {},
                "neck": {},
                "chest": {},
                "gloves": {},
                "belt": {},
                "legs": {},
                "boots": {},
                "left": {},
                "right": {},
                "ring": {},
                "charm": {},
                "backpack": {},
            },
            "loadouts": {},
            "class": {
                "name": _("Hero"),
                "ability": False,
                "desc": _("Your basic adventuring hero."),
                "forage": 0,
            },
            "skill": {"pool": 0, "att": 0, "cha": 0, "int": 0},
        }

        default_guild = {
            "cart_channels": [],
            "god_name": "",
            "cart_name": "",
            "embed": True,
            "cart_timeout": 10800,
        }
        default_global = {
            "god_name": _("Herbert"),
            "cart_name": _("Hawl's brother"),
            "theme": "default",
        }

        self.RAISINS: list = None
        self.THREATEE: list = None
        self.TR_COMMON: dict = None
        self.TR_RARE: dict = None
        self.TR_EPIC: dict = None
        self.TR_LEGENDARY: dict = None
        self.ATTRIBS: dict = None
        self.MONSTERS: dict = None
        self.LOCATIONS: list = None
        self.PETS: dict = None

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.cleanup_loop = self.bot.loop.create_task(self.cleanup_tasks())

    async def initialize(self):
        """This will load all the bundled data into respective variables"""
        theme = await self.config.theme()
        pets_fp = cog_data_path(self) / "{theme}/pets.json".format(theme=theme)
        attribs_fp = cog_data_path(self) / "{theme}/attribs.json".format(theme=theme)
        monster_fp = cog_data_path(self) / "{theme}/monsters.json".format(theme=theme)
        locations_fp = cog_data_path(self) / "{theme}/locations.json".format(theme=theme)
        raisins_fp = cog_data_path(self) / "{theme}/raisins.json".format(theme=theme)
        threatee_fp = cog_data_path(self) / "{theme}/threatee.json".format(theme=theme)
        tr_common_fp = cog_data_path(self) / "{theme}/tr_common.json".format(theme=theme)
        tr_rare_fp = cog_data_path(self) / "{theme}/tr_rare.json".format(theme=theme)
        tr_epic_fp = cog_data_path(self) / "{theme}/tr_epic.json".format(theme=theme)
        tr_legendary_fp = cog_data_path(self) / "{theme}/tr_legendary.json".format(theme=theme)
        files = {
            "pets": pets_fp,
            "attr": attribs_fp,
            "monster": monster_fp,
            "location": locations_fp,
            "raisins": raisins_fp,
            "threatee": threatee_fp,
            "common": tr_common_fp,
            "rare": tr_rare_fp,
            "epic": tr_epic_fp,
            "legendary": tr_legendary_fp,
        }
        for name, file in files.items():
            if not file.exists():
                files[name] = bundled_data_path(self) / "default/{name}".format(name=file.name)
        with files["pets"].open("r") as f:
            self.PETS = json.load(f)
        with files["attr"].open("r") as f:
            self.ATTRIBS = json.load(f)
        with files["monster"].open("r") as f:
            self.MONSTERS = json.load(f)
        with files["location"].open("r") as f:
            self.LOCATIONS = json.load(f)
        with files["raisins"].open("r") as f:
            self.RAISINS = json.load(f)
        with files["threatee"].open("r") as f:
            self.THREATEE = json.load(f)
        with files["common"].open("r") as f:
            self.TR_COMMON = json.load(f)
        with files["rare"].open("r") as f:
            self.TR_RARE = json.load(f)
        with files["epic"].open("r") as f:
            self.TR_EPIC = json.load(f)
        with files["legendary"].open("r") as f:
            self.TR_LEGENDARY = json.load(f)

    async def cleanup_tasks(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("Adventure"):
            for task in self.tasks:
                if task.done():
                    self.tasks.remove(task)
            await asyncio.sleep(300)

    async def allow_in_dm(self, ctx):
        """Checks if the bank is global and allows the command in dm"""
        if ctx.guild is not None:
            return True
        if ctx.guild is None and await bank.is_global():
            return True
        else:
            return False

    def get_lock(self, member: discord.Member):
        if member.id not in self.locks:
            self.locks[member.id] = asyncio.Lock()
        return self.locks[member.id]

    @staticmethod
    def E(t: str) -> str:
        return escape(filter_various_mentions(t), mass_mentions=True, formatting=True)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def makecart(self, ctx):
        """
            Force cart to appear in a channel
        """
        await self._trader(ctx)

    @commands.group(name="backpack", autohelp=False)
    async def _backpack(self, ctx: Context):
        """This shows the contents of your backpack.

        Selling: `[p]backpack sell item_name`
        Trading: `[p]backpack trade @user price item_name`
        Equip:   `[p]backpack equip item_name`
        or respond with the item name to the backpack command output.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        # bkpk = "Items in Backpack: \n"
        if not ctx.invoked_subcommand:
            backpack_contents = _("[{author}'s backpack] \n\n{backpack}\n").format(
                author=self.E(ctx.author.display_name), backpack=c.__backpack__()
            )
            msgs = []
            for page in pagify(backpack_contents, delims=["\n"], shorten_by=20):
                msgs.append(box(page, lang="css"))
                # await ctx.send(box(page, lang="css"))
            return await menu(ctx, msgs, DEFAULT_CONTROLS)

            try:
                reply = await ctx.bot.wait_for(
                    "message", check=MessagePredicate.same_context(ctx), timeout=30
                )
            except asyncio.TimeoutError:
                return
            if not reply:
                return
            else:
                equip = None
                for name, item in c.backpack.items():
                    if (
                        reply.content.lower() in item.name.lower()
                        or reply.content.lower() in str(item).lower()
                    ):
                        equip = item
                        break
                if equip:
                    slot = item.slot[0]
                    if len(item.slot) > 1:
                        slot = "two handed"
                    if not getattr(c, item.slot[0]):
                        equip_msg = box(
                            _("{author} equipped {item} ({slot} slot).").format(
                                author=self.E(ctx.author.display_name), item=item, slot=slot
                            ),
                            lang="css",
                        )
                    else:
                        equip_msg = box(
                            _(
                                "{author} equipped {item} "
                                "({slot} slot) and put "
                                "{put} into their backpack."
                            ).format(
                                author=self.E(ctx.author.display_name),
                                item=item,
                                slot=slot,
                                put=humanize_list([str(getattr(c, s)) for s in item.slot]),
                            ),
                            lang="css",
                        )
                    current_stats = box(
                        _(
                            "{author}'s new stats: "
                            "Attack: {att} [{att_skill}], "
                            "Intelligence: {int} [{int_skill}], "
                            "Diplomacy: {cha} [{cha_skill}]."
                        ).format(
                            author=self.E(ctx.author.display_name),
                            att=c.att,
                            att_skill=c.skill["att"],
                            int=c.int,
                            int_skill=c.skill["int"],
                            cha=c.cha,
                            cha_skill=c.skill["cha"],
                        ),
                        lang="css",
                    )
                    await ctx.send(equip_msg + current_stats)
                    async with self.get_lock(c.user):
                        try:
                            c = await Character._from_json(self.config, ctx.author)
                        except Exception:
                            log.exception("Error with the new character sheet")
                            return
                        c = await c._equip_item(item, True)
                        await self.config.user(ctx.author).set(c._to_json())

    @_backpack.command(name="equip")
    async def backpack_equip(self, ctx: Context, *, equip_item: str):
        """Equip an item from your backpack"""
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        equip = None
        for name, item in c.backpack.items():
            if equip_item.lower() in item.name.lower() or equip_item.lower() in str(item).lower():
                equip = item
                break
        # log.debug(equip._to_json())
        if equip:
            slot = item.slot[0]
            if len(item.slot) > 1:
                slot = "two handed"
            if not getattr(c, item.slot[0]):
                equip_msg = box(
                    _("{author} equipped {item} ({slot} slot).").format(
                        author=self.E(ctx.author.display_name), item=item, slot=slot
                    ),
                    lang="css",
                )
            else:
                equip_msg = box(
                    _(
                        "{author} equipped {item} "
                        "({slot} slot) and put {put} into their backpack."
                    ).format(
                        author=self.E(ctx.author.display_name),
                        item=item,
                        slot=slot,
                        put=getattr(c, item.slot[0]),
                    ),
                    lang="css",
                )
            await ctx.send(equip_msg)
            async with self.get_lock(c.user):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                c = await c._equip_item(item, True)
                await self.config.user(ctx.author).set(c._to_json())

    @_backpack.command(name="sell")
    async def backpack_sell(self, ctx: Context, *, item: str):
        """Sell an item from your backpack"""
        if item.startswith("."):
            item = item.replace("_", " ").replace(".", "")
        if item.startswith("["):
            item = item.replace("[", "").replace("]", "")
        if item.startswith("{.:'"):
            item = item.replace("{.:'", "").replace("':.}", "")
        if item.startswith("{Legendary:'"):
            item = item.replace("{Legendary:'", "").replace("'}", "")
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not any([x for x in c.backpack if item.lower() in x.lower()]):
            await ctx.send(
                _(
                    "{}, you have to specify an item (or partial name) from your backpack to sell."
                ).format(self.E(ctx.author.display_name))
            )
            return
        lookup = list(i for x, i in c.backpack.items() if item.lower() in x.lower())
        if any([x for x in lookup if x.rarity == "forged"]):
            device = lookup[0]
            return await ctx.send(
                box(
                    _(
                        "\n{author}, your {device} is "
                        "refusing to be sold and bit your finger for trying."
                    ).format(author=self.E(ctx.author.display_name), device=device),
                    lang="css",
                )
            )
        item_str = box(humanize_list([f"{str(y)} - {y.owned}" for y in lookup]), lang="css")
        start_msg = await ctx.send(
            _("{author}, do you want to sell these items? {item}").format(
                author=self.E(ctx.author.display_name), item=item_str
            )
        )
        currency_name = await bank.get_currency_name(ctx.guild)

        emojis = [
            "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
            "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}",
            "\N{CROSS MARK}",
        ]
        start_adding_reactions(start_msg, emojis)
        pred = ReactionPredicate.with_emojis(emojis, start_msg)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await self._clear_react(start_msg)
            return
        async with self.get_lock(c.user):
            try:
                c = await Character._from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            msg = ""
            if pred.result == 0:  # user reacted with one to sell.
                # sell one of the item
                price = 0
                for item in lookup:
                    item.owned -= 1
                    price += await self._sell(ctx.author, item)
                    msg += _("{author} sold one " "{item} for {price} {currency_name}.\n").format(
                        author=self.E(ctx.author.display_name),
                        item=box(item, lang="css"),
                        price=price,
                        currency_name=currency_name,
                    )
                    if item.owned <= 0:
                        del c.backpack[item.name]
                try:
                    await bank.deposit_credits(ctx.author, price)
                except BalanceTooHigh:
                    pass
            if pred.result == 1:  # user wants to sell all owned.
                for item in lookup:
                    price = 0
                    old_owned = item.owned
                    for x in range(0, item.owned):
                        item.owned -= 1
                        price += await self._sell(ctx.author, item)
                        if item.owned <= 0:
                            del c.backpack[item.name]
                    msg += _(
                        "{author} sold all their {old_item} for {price} {currency_name}.\n"
                    ).format(
                        author=self.E(ctx.author.display_name),
                        old_item=box(str(item) + " - " + str(old_owned), lang="css"),
                        price=price,
                        currency_name=currency_name,
                    )
                try:
                    await bank.deposit_credits(ctx.author, price)
                except BalanceTooHigh:
                    pass
            if pred.result == 2:  # user wants to sell all but one.
                price = 0
                for item in lookup:
                    old_owned = item.owned
                    for x in range(1, item.owned):
                        item.owned -= 1
                        price += await self._sell(ctx.author, item)
                    if price != 0:
                        msg += _(
                            "{author} sold all but one of their {old_item} for {price} {currency_name}.\n"
                        ).format(
                            author=self.E(ctx.author.display_name),
                            old_item=box(str(item) + " - " + str(old_owned - 1), lang="css"),
                            price=price,
                            currency_name=currency_name,
                        )
                        try:
                            await bank.deposit_credits(ctx.author, price)
                        except BalanceTooHigh:
                            pass
            if pred.result == 3:  # user doesn't want to sell those items.
                msg = _("Not selling those items.")

            if msg:
                await self.config.user(ctx.author).set(c._to_json())
                for page in pagify(msg, delims=["\n"]):
                    await ctx.send(page)

    @_backpack.command(name="trade")
    async def backpack_trade(
        self, ctx: Context, buyer: discord.Member, asking: Optional[int] = 1000, *, item
    ):
        """Trade an item from your backpack to another user"""
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not any([x for x in c.backpack if item.lower() in x.lower()]):
            return await ctx.send(
                _("{author}, you have to specify an item from your backpack to trade.").format(
                    author=self.E(ctx.author.display_name)
                )
            )
        lookup = list(x for n, x in c.backpack.items() if item.lower() in x.name.lower())
        if len(lookup) > 1:
            await ctx.send(
                _(
                    "{author}, I found multiple items ({items}) "
                    "matching that name in your backpack.\nPlease be more specific."
                ).format(
                    author=self.E(ctx.author.display_name),
                    items=humanize_list([x.name for x in lookup]),
                )
            )
            return
        if any([x for x in lookup if x.rarity == "forged"]):
            device = [x for x in lookup if x.rarity == "forged"]
            return await ctx.send(
                box(
                    _("\n{author}, your {device} does not want to leave you.").format(
                        author=self.E(ctx.author.display_name), device=str(device[0])
                    ),
                    lang="css",
                )
            )
        else:
            item = lookup[0]
            hand = item.slot[0] if len(item.slot) < 2 else "two handed"
            currency_name = await bank.get_currency_name(ctx.guild)
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
                    author=self.E(ctx.author.display_name),
                    item=item,
                    att_item=str(item.att),
                    cha_item=str(item.cha),
                    int_item=str(item.int),
                    dex_item=str(item.dex),
                    luck_item=str(item.luck),
                    hand=hand,
                    buyer=self.E(buyer.display_name),
                    asking=str(asking),
                    currency_name=currency_name,
                ),
                lang="css",
            )
            trade_msg = await ctx.send(f"{buyer.mention}\n{trade_talk}")
            start_adding_reactions(trade_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(trade_msg, buyer)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await self._clear_react(trade_msg)
                return
            if pred.result:  # buyer reacted with Yes.
                try:
                    if await bank.can_spend(buyer, asking):
                        async with self.get_lock(c.user):
                            try:
                                c = await Character._from_json(self.config, ctx.author)
                            except Exception:
                                log.exception("Error with the new character sheet")
                                return
                            await bank.transfer_credits(buyer, ctx.author, asking)
                            c.backpack[item.name].owned -= 1
                            if c.backpack[item.name].owned <= 0:
                                del c.backpack[item.name]
                            await self.config.user(ctx.author).set(c._to_json())
                        async with self.get_lock(buyer):
                            try:
                                buy_user = await Character._from_json(self.config, buyer)
                            except Exception:
                                log.exception("Error with the new character sheet")
                                return
                            if item.name in buy_user.backpack:
                                buy_user.backpack[item.name].owned += 1
                            else:
                                item.owned = 1
                                buy_user.backpack[item.name] = item
                                await self.config.user(buyer).set(buy_user._to_json())
                        await trade_msg.edit(
                            content=(
                                box(
                                    _(
                                        "\n{author} traded {item} to "
                                        "{buyer} for {asking} {currency_name}."
                                    ).format(
                                        author=self.E(ctx.author.display_name),
                                        item=item,
                                        buyer=self.E(buyer.display_name),
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
                                buyer=self.E(buyer.display_name), currency_name=currency_name
                            )
                        )
                except discord.errors.NotFound:
                    pass
            else:
                try:
                    await trade_msg.delete()
                except discord.errors.Forbidden:
                    pass

    @commands.group(aliases=["loadouts"])
    async def loadout(self, ctx):
        """Setup various adventure settings"""
        pass

    @loadout.command(name="save")
    async def save_loadout(self, ctx: Context, name: str):
        """Save your current equipment as a loadout"""
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        name = name.lower()
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if name in c.loadouts:
            await ctx.send(
                _("{author}, you already have a loadout named {name}.").format(
                    author=self.E(ctx.author.display_name), name=name
                )
            )
            return
        else:
            async with self.get_lock(c.user):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                loadout = await Character._save_loadout(c)
                c.loadouts[name] = loadout
                await self.config.user(ctx.author).set(c._to_json())
            await ctx.send(
                _("{author}, your current equipment has been saved to {name}.").format(
                    author=self.E(ctx.author.display_name), name=name
                )
            )

    @loadout.command(name="delete", aliases=["del", "rem", "remove"])
    async def remove_loadout(self, ctx: Context, name: str):
        """Delete a saved loadout"""
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        name = name.lower()
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if name not in c.loadouts:
            await ctx.send(
                _("{author}, you don't have a loadout named {name}.").format(
                    author=self.E(ctx.author.display_name), name=name
                )
            )
            return
        else:
            async with self.get_lock(c.user):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                del c.loadouts[name]
                await self.config.user(ctx.author).set(c._to_json())
            await ctx.send(
                _("{author}, loadout {name} has been deleted.").format(
                    author=self.E(ctx.author.display_name), name=name
                )
            )

    @loadout.command(name="show")
    async def show_loadout(self, ctx: Context, name: str = None):
        """Show saved loadouts"""
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not c.loadouts:
            await ctx.send(
                _("{author}, you don't have any loadouts saved.").format(
                    author=self.E(ctx.author.display_name)
                )
            )
            return
        if name is not None and name.lower() not in c.loadouts:
            await ctx.send(
                _("{author}, you don't have a loadout named {name}.").format(
                    author=self.E(ctx.author.display_name), name=name
                )
            )
            return
        else:
            msg_list = []
            index = 0
            count = 0
            for l_name, loadout in c.loadouts.items():
                if name and name.lower() == l_name:
                    index = count
                stats = await self._build_loadout_display({"items": loadout})
                msg = _("[{name} Loadout for {author}]\n\n{stats}").format(
                    name=l_name, author=self.E(ctx.author.display_name), stats=stats
                )
                msg_list.append(box(msg, lang="css"))
                count += 1
            await menu(ctx, msg_list, DEFAULT_CONTROLS, page=index)

    @loadout.command(name="equip", aliases=["load"])
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def equip_loadout(self, ctx: Context, name: str):
        """Equip a saved loadout"""
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        name = name.lower()
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if name not in c.loadouts:
            await ctx.send(
                _("{author}, you don't have a loadout named {name}.").format(
                    author=self.E(ctx.author.display_name), name=name
                )
            )
            return
        else:
            async with self.get_lock(c.user):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                c = await c._equip_loadout(name)
                current_stats = box(
                    _(
                        "{author}'s new stats: "
                        "Attack: {stat_att} [{skill_att}], "
                        "Intelligence: {stat_int} [{skill_int}], "
                        "Diplomacy: {stat_cha} [{skill_cha}]."
                    ).format(
                        author=self.E(ctx.author.display_name),
                        stat_att=c.__stat__("att"),
                        skill_att=c.skill["att"],
                        stat_int=c.__stat__("int"),
                        skill_int=c.skill["int"],
                        stat_cha=c.__stat__("cha"),
                        skill_cha=c.skill["cha"],
                    ),
                    lang="css",
                )
                await ctx.send(current_stats)
                await self.config.user(ctx.author).set(c._to_json())
        return

        # saving this code to potentially be used later should not be read at all
        await bank.get_balance(ctx.author)
        currency_name = await bank.get_currency_name(ctx.guild)
        if str(currency_name).startswith("<"):
            currency_name = "credits"
        spend = 2000
        msg = await ctx.send(
            box(
                _(
                    "This will cost {spend} {currency_name}. Do you want to continue, {author}?"
                ).format(
                    spend=spend,
                    currency_name=currency_name,
                    author=self.E(ctx.author.display_name),
                ),
                lang="css",
            )
        )
        broke = box(
            _("You don't have enough {currency_name} to pay your squire.").format(
                currency_name=currency_name
            ),
            lang="css",
        )

        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await self._clear_react(msg)
            return

        if not pred.result:
            await msg.edit(
                content=box(
                    _("{author} decided not to change his loadout.").format(
                        author=self.E(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
            return await self._clear_react(msg)
        try:
            await bank.withdraw_credits(ctx.author, spend)
            await msg.edit(content=box(_("Your squire changed you in record time."), lang="css"))
            await self._clear_react(msg)
        except ValueError:
            await self._clear_react(msg)
            return await msg.edit(content=broke)

    @commands.group()
    @commands.guild_only()
    async def adventureset(self, ctx):
        """Setup various adventure settings"""
        pass

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def version(self, ctx):
        """Display the version of adventure being used"""
        await ctx.send(box(_("Adventure version: {}").format(self.__version__)))

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def god(self, ctx: Context, *, name):
        """[Admin] Set the server's name of the god"""
        await self.config.guild(ctx.guild).god_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.is_owner()
    async def globalgod(self, ctx: Context, *, name):
        """[Owner] Set the default name of the god"""
        await self.config.god_name.set(name)
        await ctx.tick()

    @adventureset.command(aliases=["embed"])
    @checks.admin_or_permissions(administrator=True)
    async def embeds(self, ctx):
        """[Admin] Set whether or not to use embeds for the adventure game"""
        toggle = await self.config.guild(ctx.guild).embed()
        await self.config.guild(ctx.guild).embed.set(not toggle)
        await ctx.send(_("Embeds: {}").format(not toggle))

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def cartname(self, ctx: Context, *, name):
        """[Admin] Set the server's name of the cart"""
        await self.config.guild(ctx.guild).cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def carttime(self, ctx: Context, *, time: str):
        """[Admin] Set the cooldown of the cart"""
        time_delta = parse_timedelta(time)
        if time_delta is None:
            return await ctx.send(_("You must supply a ammount and time unit like `120 seconds`."))
        if time_delta.total_seconds() < 600:
            cartname = await self.config.guild(ctx.guild).cart_name()
            if not cartname:
                cartname = await self.config.cart_name()
            return await ctx.send(
                _("{} doesn't have the energy to return that often.").format(cartname)
            )
        await self.config.guild(ctx.guild).cart_timeout.set(time_delta.seconds)
        await ctx.tick()

    @adventureset.command()
    @checks.is_owner()
    async def globalcartname(self, ctx: Context, *, name):
        """[Owner] Set the default name of the cart"""
        await self.config.cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.is_owner()
    async def theme(self, ctx: Context, *, theme):
        """Change the theme for adventure"""
        # log.debug(os.listdir(cog_data_path(self) / "default"))
        if theme == "default":
            await self.config.theme.set("default")
            await ctx.send(_("Going back to the default theme."))
            await self.initialize()
            return
        if theme not in os.listdir(cog_data_path(self)):
            await ctx.send(_("That theme pack does not exist!"))
            return
        good_files = [
            "attribs.json",
            "bosses.json",
            "locations.json",
            "minibosses.json",
            "monsters.json",
            "pets.json",
            "raisins.json",
            "threatee.json",
            "tr_common.json",
            "tr_epic.json",
            "tr_rare.json",
            "tr_legendary.json",
        ]
        missing_files = set(good_files).difference(os.listdir(cog_data_path(self) / theme))

        if missing_files:
            await ctx.send(
                _("That theme pack is missing the following files {}").format(
                    humanize_list(missing_files)
                )
            )
            return
        else:
            await self.config.theme.set(theme)
            await ctx.tick()
        await self.initialize()

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def cart(self, ctx: Context, *, channel: discord.TextChannel = None):
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
            await ctx.send(
                _("The {} channel has been removed from the cart delivery list.").format(channel)
            )
            return await self.config.guild(ctx.guild).cart_channels.set(new_channels)
        else:
            channel_list.append(channel.id)
            await ctx.send(
                _("The {} channel has been added to the cart delivery list.").format(channel)
            )
            await self.config.guild(ctx.guild).cart_channels.set(channel_list)

    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.guild)
    async def convert(self, ctx: Context, box_rarity: str, amount: int = 1):
        """Convert normal, rare or epic chests.

        Trade 5 normal treasure chests for 1 rare treasure chest.
        Trade 4 rare treasure chests for 1 epic treasure chest.
        """

        # Thanks to flare#0001 for the idea and writing the first instance of this
        if amount < 1:
            return await ctx.send(_("Nice try :smirk:"))
        if amount > 1:
            plural = "s"
        else:
            plural = ""
        async with self.get_lock(ctx.author):
            try:
                c = await Character._from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            if box_rarity.lower() == "normal":
                if c.treasure[0] >= (5 * amount):
                    c.treasure[0] -= 5 * amount
                    c.treasure[1] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} normal treasure "
                                "chests to {to} rare treasure chest{plur}.\n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic "
                                "and {leg} legendary treasure chests."
                            ).format(
                                converted=(5 * amount),
                                to=(1 * amount),
                                plur=plural,
                                author=self.E(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[0],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(c._to_json())
                else:
                    await ctx.send(
                        _(
                            "{author}, you do not have {amount} "
                            "normal treasure chests to convert."
                        ).format(author=self.E(ctx.author.display_name), amount=(5 * amount))
                    )
            elif box_rarity.lower() == "rare":
                if c.treasure[1] >= (4 * amount):
                    c.treasure[1] -= 4 * amount
                    c.treasure[2] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} rare treasure "
                                "chests to {to} epic treasure chest{plur}. \n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic "
                                "and {leg} legendary treasure chests."
                            ).format(
                                converted=(4 * amount),
                                to=(1 * amount),
                                plur=plural,
                                author=self.E(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(c._to_json())
                else:
                    await ctx.send(
                        _(
                            "{author}, you do not have {amount} "
                            "rare treasure chests to convert."
                        ).format(author=self.E(ctx.author.display_name), amount=(4 * amount))
                    )
            elif box_rarity.lower() == "epic":
                return await ctx.send(
                    _("{}, I cannot convert " "loot rarer than epic.").format(
                        self.E(ctx.author.display_name)
                    )
                )
                if c.treasure[2] >= (4 * amount):
                    c.treasure[2] -= 4 * amount
                    c.treasure[3] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} epic treasure "
                                "chests to {to} legendary treasure chest{plural}. \n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic "
                                "and {leg} legendary treasure chests."
                            ).format(
                                converted=(4 * amount),
                                to=(1 * amount),
                                plur=plural,
                                author=self.E(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(c._to_json())
                else:
                    await ctx.send(
                        _(
                            "{author}, you do not have {amount} "
                            "epic treasure chests to convert."
                        ).format(author=self.E(ctx.author.display_name), amount=(4 * amount))
                    )
            else:
                await ctx.send(
                    _(
                        "{}, please select between normal or rare treasure chests to convert."
                    ).format(self.E(ctx.author.display_name))
                )

    @commands.command()
    async def equip(self, ctx: Context, *, item: str):
        """This equips an item from your backpack.

        `[p]equip name of item`
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))

        await ctx.invoke(self.backpack_equip, equip_item=item)

    @commands.command()
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    async def forge(self, ctx):
        """[Tinkerer Class Only]

        This allows a Tinkerer to forge two items into a device.
        (2h cooldown)
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        async with self.get_lock(ctx.author):
            try:
                c = await Character._from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            if c.heroclass["name"] != "Tinkerer":
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    _("{}, you need to be a Tinkerer to do this.").format(
                        self.E(ctx.author.display_name)
                    )
                )
            else:
                consumed = []
                forgeables = len([i for n, i in c.backpack.items() if i.rarity != "forged"])
                if forgeables <= 1:
                    ctx.command.reset_cooldown(ctx)
                    return await ctx.send(
                        _(
                            "{}, you need at least two forgeable items in your backpack to forge."
                        ).format(self.E(ctx.author.display_name))
                    )
                forgeables = _(
                    "[{author}'s forgeables]\n{bc}\n"
                    "(Reply with the full or partial name "
                    "of item 1 to select for forging. Try to be specific.)"
                ).format(author=self.E(ctx.author.display_name), bc=c.__backpack__(True))
                for page in pagify(forgeables, delims=["\n"], shorten_by=20):
                    try:
                        await ctx.author.send(box(page, lang="css"))
                    except discord.errors.Forbidden:
                        await ctx.send(box(page, lang="css"))

                try:
                    reply = await ctx.bot.wait_for(
                        "message", check=MessagePredicate.same_context(user=ctx.author), timeout=30
                    )
                except asyncio.TimeoutError:
                    ctx.command.reset_cooldown(ctx)
                    timeout_msg = _("I don't have all day you know, {}.").format(
                        self.E(ctx.author.display_name)
                    )
                    try:
                        return await ctx.author.send(timeout_msg)
                    except discord.errors.Forbidden:
                        return await ctx.send(timeout_msg)
                for name, item in c.backpack.items():
                    if reply.content.lower() in name.lower():
                        if item.rarity != "forgeable":
                            consumed.append(item)
                            break
                        else:
                            ctx.command.reset_cooldown(ctx)
                            return await ctx.send(
                                _("{}, tinkered devices cannot be reforged.").format(
                                    self.E(ctx.author.display_name)
                                )
                            )
                if not consumed:
                    ctx.command.reset_cooldown(ctx)
                    wrong_item = _("{}, I could not find that item - check your spelling.").format(
                        self.E(ctx.author.display_name)
                    )
                    try:
                        return await ctx.author.send(wrong_item)
                    except discord.errors.Forbidden:
                        return await ctx.send(wrong_item)
                forgeables = _(
                    "(Reply with the full or partial name "
                    "of item 2 to select for forging. Try to be specific.)"
                )
                try:
                    await ctx.author.send(box(forgeables, lang="css"))
                except discord.errors.Forbidden:
                    await ctx.send(box(forgeables, lang="css"))
                # check = lambda m: m.author == ctx.author and not m.content.isnumeric()
                try:
                    reply = await ctx.bot.wait_for(
                        "message", check=MessagePredicate.same_context(user=ctx.author), timeout=30
                    )
                except asyncio.TimeoutError:
                    ctx.command.reset_cooldown(ctx)
                    timeout_msg = _("I don't have all day you know, {}.").format(
                        self.E(ctx.author.display_name)
                    )
                    try:
                        return await ctx.author.send(timeout_msg)
                    except discord.errors.Forbidden:
                        return await ctx.send(timeout_msg)
                for name, item in c.backpack.items():
                    if reply.content.lower() in name and item not in consumed:
                        if item.rarity != "forged":
                            # item2 = backpack_items.get(item)
                            consumed.append(item)
                            break
                        else:
                            ctx.command.reset_cooldown(ctx)
                            try:
                                return await ctx.author.send(
                                    _("{}, tinkered devices cannot be reforged.").format(
                                        self.E(ctx.author.display_name)
                                    )
                                )
                            except discord.errors.Forbidden:
                                return await ctx.send(
                                    _("{}, tinkered devices cannot be reforged.").format(
                                        self.E(ctx.author.display_name)
                                    )
                                )
                if len(consumed) < 2:
                    ctx.command.reset_cooldown(ctx)
                    try:
                        return await ctx.author.send(
                            _("{}, I could not find that item - check your spelling.").format(
                                self.E(ctx.author.display_name)
                            )
                        )
                    except discord.errors.Forbidden:
                        return await ctx.send(
                            _("{}, I could not find that item - check your spelling.").format(
                                self.E(ctx.author.display_name)
                            )
                        )

                newitem = await self._to_forge(ctx, consumed)
                for x in consumed:
                    c.backpack[x.name].owned -= 1
                    if c.backpack[x.name].owned <= 0:
                        del c.backpack[x.name]
                    await self.config.user(ctx.author).set(c._to_json())
                # save so the items are eaten up already
                log.debug("tambourine" in c.backpack)
                for items in c.current_equipment():
                    if items.rarity == "forged":
                        c = await c._unequip_item(items)
                lookup = list(i for n, i in c.backpack.items() if i.rarity == "forged")
                if len(lookup) > 0:
                    forge_str = box(
                        _(
                            "{author}, you already have a device. "
                            "Do you want to replace {replace}?"
                        ).format(
                            author=self.E(ctx.author.display_name),
                            replace=", ".join([str(x) for x in lookup]),
                        ),
                        lang="css",
                    )
                    try:
                        forge_msg = await ctx.author.send(forge_str)
                    except discord.errors.Forbidden:
                        forge_msg = await ctx.send(forge_str)
                    start_adding_reactions(forge_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                    pred = ReactionPredicate.yes_or_no(forge_msg, ctx.author)
                    try:
                        await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                    except asyncio.TimeoutError:
                        await self._clear_react(forge_msg)
                        return
                    try:
                        await forge_msg.delete()
                    except discord.errors.Forbidden:
                        pass
                    if pred.result:  # user reacted with Yes.
                        created_item = box(
                            _(
                                "{author}, your new {newitem} consumed {lk} "
                                "and is now lurking in your backpack."
                            ).format(
                                author=self.E(ctx.author.display_name),
                                newitem=newitem,
                                lk=", ".join([str(x) for x in lookup]),
                            ),
                            lang="css",
                        )
                        for item in lookup:
                            del c.backpack[item.name]
                        try:
                            await ctx.author.send(created_item)
                        except discord.errors.Forbidden:
                            await ctx.send(created_item)
                        c.backpack[newitem.name] = newitem
                        await self.config.user(ctx.author).set(c._to_json())
                    else:
                        mad_forge = box(
                            _(
                                "{author}, {newitem} got mad at your rejection and blew itself up."
                            ).format(author=self.E(ctx.author.display_name), newitem=newitem),
                            lang="css",
                        )
                        try:
                            return await ctx.author.send(mad_forge)
                        except discord.errors.Forbidden:
                            return await ctx.send(mad_forge)
                else:
                    c.backpack[newitem.name] = newitem
                    await self.config.user(ctx.author).set(c._to_json())
                    forged_item = box(
                        _("{author}, your new {newitem} is lurking in your backpack.").format(
                            author=self.E(ctx.author.display_name), newitem=newitem
                        ),
                        lang="css",
                    )
                    try:
                        await ctx.author.send(forged_item)
                    except discord.errors.Forbidden:
                        await ctx.send(forged_item)

    async def _to_forge(self, ctx: Context, consumed):
        item1 = consumed[0]
        item2 = consumed[1]

        roll = random.randint(1, 20)
        if roll == 1:
            modifier = 0.4
        if roll > 1 and roll <= 6:
            modifier = 0.5
        if roll > 6 and roll <= 8:
            modifier = 0.6
        if roll > 8 and roll <= 10:
            modifier = 0.7
        if roll > 10 and roll <= 13:
            modifier = 0.8
        if roll > 13 and roll <= 16:
            modifier = 0.9
        if roll > 16 and roll <= 17:
            modifier = 1.0
        if roll > 17 and roll <= 19:
            modifier = 1.1
        if roll == 20:
            modifier = 1.2
        newatt = round((int(item1.att) + int(item2.att)) * modifier)
        newdip = round((int(item1.cha) + int(item2.cha)) * modifier)
        newint = round((int(item1.int) + int(item2.int)) * modifier)
        newdex = round((int(item1.dex) + int(item2.dex)) * modifier)
        newluck = round((int(item1.luck) + int(item2.luck)) * modifier)
        newslot = random.choice([item1.slot, item2.slot])
        if len(newslot) == 2:  # two handed weapons add their bonuses twice
            hand = "two handed"
        else:
            if newslot[0] == "right" or newslot[0] == "left":
                hand = newslot[0] + " handed"
            else:
                hand = newslot[0] + " slot"
        if len(newslot) == 2:
            two_handed_msg = box(
                _(
                    "{author}, your forging roll was 🎲({roll}).\n"
                    "The device you tinkered will have "
                    "(ATT {new_att} | "
                    "CHA {new_cha} | "
                    "INT {new_int} | "
                    "DEX {new_dex} | "
                    "LUCK {new_luck})"
                    " and be {hand}."
                ).format(
                    author=self.E(ctx.author.display_name),
                    roll=roll,
                    new_att=(newatt * 2),
                    new_cha=(newdip * 2),
                    new_int=(newint * 2),
                    new_dex=(newdex * 2),
                    new_luck=(newluck * 2),
                    hand=hand,
                ),
                lang="css",
            )
            try:
                await ctx.author.send(two_handed_msg)
            except discord.errors.Forbidden:
                await ctx.send(two_handed_msg)
        else:
            reg_item = box(
                _(
                    "{author}, your forging roll was 🎲({roll}).\n"
                    "The device you tinkered will have "
                    "(ATT {new_att} | "
                    "CHA {new_dip} | "
                    "INT {new_int} | "
                    "DEX {new_dex} | "
                    "LUCK {new_luck})"
                    " and be {hand}."
                ).format(
                    author=self.E(ctx.author.display_name),
                    roll=roll,
                    new_att=newatt,
                    new_dip=newdip,
                    new_int=newint,
                    new_dex=newdex,
                    new_luck=newluck,
                    hand=hand,
                )
            )
            try:
                await ctx.author.send(reg_item)
            except discord.errors.Forbidden:
                await ctx.send(reg_item)
        get_name = _(
            "{}, please respond with "
            "a name for your creation within 30s.\n"
            "(You will not be able to change it afterwards. 40 characters maximum.)"
        ).format(self.E(ctx.author.display_name))
        try:
            await ctx.author.send(get_name)
        except discord.errors.Forbidden:
            await ctx.send(get_name)
        reply = None
        try:
            reply = await ctx.bot.wait_for(
                "message", check=MessagePredicate.same_context(user=ctx.author), timeout=30
            )
        except asyncio.TimeoutError:
            name = _("Unnamed Artifact")
        if reply is None:
            name = _("Unnamed Artifact")
        else:
            if hasattr(reply, "content"):
                if len(reply.content) > 40:
                    name = _("Long-winded Artifact")
                else:
                    name = reply.content.lower()
        item = {
            name: {
                "slot": newslot,
                "att": newatt,
                "cha": newdip,
                "int": newint,
                "dex": newdex,
                "luck": newluck,
                "rarity": _("forged"),
            }
        }
        item = Item._from_json(item)
        return item

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def give(self, ctx):
        """[Admin] Commands to add things to players' inventories."""

        pass

    @give.command(name="funds")
    @checks.admin_or_permissions(administrator=True)
    async def _give_funds(self, ctx: Context, amount: int = 1, *, to: discord.Member = None):
        """[Admin] Adds currency to a specified member's balance.

        `[p]give funds 10 @Elder Aramis`
        will create 10 currency and add to Elder Aramis' total.
        """
        if await bank.is_global() and not await ctx.bot.is_owner(ctx.author):
            return await ctx.send(_("You are not worthy."))
        if to is None:
            return await ctx.send(
                _("You need to specify a receiving member, {}.").format(
                    self.E(ctx.author.display_name)
                )
            )
        to_fund = discord.utils.find(lambda m: m.name == to.name, ctx.guild.members)
        if not to_fund:
            return await ctx.send(
                _(
                    "I could not find that user, {}. Try using their full Discord name (name#0000)."
                ).format(self.E(ctx.author.display_name))
            )
        try:
            bal = await bank.deposit_credits(to, amount)
        except BalanceTooHigh:
            bal = 9223372036854775807
            pass
        currency = await bank.get_currency_name(ctx.guild)
        if str(currency).startswith("<:"):
            currency = "credits"
        await ctx.send(
            box(
                _(
                    "{author}, you funded {amount} {currency}. {to} now has {bal} {currency}."
                ).format(
                    author=self.E(ctx.author.display_name),
                    amount=amount,
                    currency=currency,
                    to=self.E(to.display_name),
                    bal=bal,
                ),
                lang="css",
            )
        )

    @give.command(name="item")
    async def _give_item(
        self, ctx: Context, user: discord.Member, item_name: str, *, stats: Stats
    ):
        """[Admin] Adds a custom item to a specified member.

        Item names containing spaces must be enclosed in double quotes.
        `[p]give item @locastan "fine dagger" 1 att 1 diplomacy rare twohanded`
        will give a two handed .fine_dagger with 1 attack and 1 diplomacy to locastan.
        if a stat is not specified it will default to 0, order does not matter.
        available stats are attack(att), diplomacy(diplo) or charisma(cha),
        intelligence(int), dexterity(dex), and luck.
        """
        item_name = item_name.lower()
        if item_name.isnumeric():
            return await ctx.send(_("Item names cannot be numbers."))
        if user is None:
            user = ctx.author
        new_item = {item_name: stats}
        item = Item._from_json(new_item)
        async with self.get_lock(user):
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            if item.name in c.backpack:
                c.backpack[item.name].owned += 1
            else:
                c.backpack[item.name] = item
            await self.config.user(user).set(c._to_json())
        await ctx.send(
            box(
                _(
                    "An item named {item} has been created and placed in {author}'s backpack."
                ).format(item=item, author=self.E(user.display_name)),
                lang="css",
            )
        )

    @give.command(name="loot")
    async def _give_loot(
        self, ctx: Context, loot_type: str, user: discord.Member = None, number: int = 1
    ):
        """[Admin] This rewards a treasure chest to a specified member.

        `[p]give loot normal @locastan 5`
        will give locastan 5 normal chests.
        Loot types: normal, rare, epic, legendary
        """

        if user is None:
            user = ctx.author
        loot_types = ["normal", "rare", "epic", "legendary"]
        if loot_type not in loot_types:
            return await ctx.send(
                _(
                    "Valid loot types: `normal`, `rare`, `epic` or `legendary`: "
                    "ex. `{}give loot normal @locastan` "
                ).format(ctx.prefix)
            )
        if loot_type == "legendary" and not await ctx.bot.is_owner(ctx.author):
            return await ctx.send(_("You are not worthy to award legendary loot."))
        async with self.get_lock(user):
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            if loot_type == "rare":
                c.treasure[1] += number
            elif loot_type == "epic":
                c.treasure[2] += number
            elif loot_type == "legendary":
                c.treasure[3] += number
            else:
                c.treasure[0] += number
            await self.config.user(user).set(c._to_json())
            await ctx.send(
                box(
                    _(
                        "{author} now owns {normal} normal, "
                        "{rare} rare, {epic} epic and {leg} legendary chests."
                    ).format(
                        author=self.E(user.display_name),
                        normal=str(c.treasure[0]),
                        rare=str(c.treasure[1]),
                        epic=str(c.treasure[2]),
                        leg=str(c.treasure[3]),
                    ),
                    lang="css",
                )
            )

    @commands.command()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def heroclass(self, ctx: Context, clz: str = None, action: str = None):
        """This allows you to select a class if you are Level 10 or above.

        For information on class use: `[p]heroclass "classname" info`
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))

        classes = {
            "Wizard": {
                "name": _("Wizard"),
                "ability": False,
                "desc": _(
                    "Wizards have the option to focus and add large bonuses to their magic, "
                    "but their focus can sometimes go astray...\nUse the focus command when attacking in an adventure."
                ),
            },
            "Tinkerer": {
                "name": _("Tinkerer"),
                "ability": False,
                "desc": _(
                    "Tinkerers can forge two different items into a device "
                    "bound to their very soul.\nUse the forge command."
                ),
            },
            "Berserker": {
                "name": _("Berserker"),
                "ability": False,
                "desc": _(
                    "Berserkers have the option to rage and add big bonuses to attacks, "
                    "but fumbles hurt.\nUse the rage command when attacking in an adventure."
                ),
            },
            "Cleric": {
                "name": _("Cleric"),
                "ability": False,
                "desc": _(
                    "Clerics can bless the entire group when praying.\n"
                    "Use the bless command when fighting in an adventure."
                ),
            },
            "Ranger": {
                "name": _("Ranger"),
                "ability": False,
                "desc": _(
                    "Rangers can gain a special pet, which can find items and give "
                    "reward bonuses.\nUse the pet command to see pet options."
                ),
                "pet": {},
                "forage": 0.0,
            },
            "Bard": {
                "name": _("Bard"),
                "ability": False,
                "desc": _(
                    "Bards can perform to aid their comrades in diplomacy.\n"
                    "Use the music command when being diplomatic in an adventure."
                ),
            },
        }

        if clz is None:
            ctx.command.reset_cooldown(ctx)
            await ctx.send(
                _(
                    "So you feel like taking on a class, **{author}**?\n"
                    "Available classes are: Tinkerer, Berserker, Wizard, Cleric, Ranger and Bard.\n"
                    "Use `{prefix}heroclass name-of-class` to choose one."
                ).format(author=self.E(ctx.author.display_name), prefix=ctx.prefix)
            )

        else:
            clz = clz.title()
            if clz in classes and action == "info":
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(f"{classes[clz]['desc']}")
            elif clz not in classes and action is None:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    _("{} may be a class somewhere, but not on my watch.").format(clz)
                )
            bal = await bank.get_balance(ctx.author)
            currency_name = await bank.get_currency_name(ctx.guild)
            if str(currency_name).startswith("<"):
                currency_name = "credits"
            spend = round(bal * 0.2)
            class_msg = await ctx.send(
                box(
                    _(
                        "This will cost {spend} {currency_name}. "
                        "Do you want to continue, {author}?"
                    ).format(
                        spend=spend,
                        currency_name=currency_name,
                        author=self.E(ctx.author.display_name),
                    ),
                    lang="css",
                )
            )
            broke = box(
                _("You don't have enough {currency_name} to train to be a {clz}.").format(
                    currency_name=currency_name, clz=clz.title()
                ),
                lang="css",
            )
            try:
                c = await Character._from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            start_adding_reactions(class_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(class_msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await self._clear_react(class_msg)
                return

            if not pred.result:
                await class_msg.edit(
                    content=box(
                        _("{author} decided to continue being a {h_class}.").format(
                            author=self.E(ctx.author.display_name), h_class=c.heroclass["name"]
                        ),
                        lang="css",
                    )
                )
                ctx.command.reset_cooldown(ctx)
                return await self._clear_react(class_msg)
            if bal < spend:
                await class_msg.edit(content=broke)
                ctx.command.reset_cooldown(ctx)
                return await self._clear_react(class_msg)
            try:
                await bank.withdraw_credits(ctx.author, spend)
            except ValueError:
                return await class_msg.edit(content=broke)
                ctx.command.reset_cooldown(ctx)

            if clz in classes and action is None:
                async with self.get_lock(ctx.author):
                    try:
                        c = await Character._from_json(self.config, ctx.author)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        return
                    now_class_msg = _("Congratulations, {author}.\nYou are now a {clz}.").format(
                        author=self.E(ctx.author.display_name), clz=classes[clz]["name"]
                    )
                    if c.lvl >= 10:
                        if c.heroclass["name"] == "Tinkerer" or c.heroclass["name"] == "Ranger":
                            if c.heroclass["name"] == "Tinkerer":
                                await self._clear_react(class_msg)
                                await class_msg.edit(
                                    content=box(
                                        _(
                                            "{}, you will lose your forged "
                                            "device if you change your class.\nShall I proceed?"
                                        ).format(self.E(ctx.author.display_name)),
                                        lang="css",
                                    )
                                )
                            else:
                                await self._clear_react(class_msg)
                                await class_msg.edit(
                                    content=box(
                                        _(
                                            "{}, you will lose your pet "
                                            "if you change your class.\nShall I proceed?"
                                        ).format(self.E(ctx.author.display_name)),
                                        lang="css",
                                    )
                                )
                            start_adding_reactions(class_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                            pred = ReactionPredicate.yes_or_no(class_msg, ctx.author)
                            try:
                                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                            except asyncio.TimeoutError:
                                await self._clear_react(class_msg)
                                return
                            if pred.result:  # user reacted with Yes.
                                if c.heroclass["name"] == "Tinkerer":
                                    tinker_wep = []
                                    for item in c.current_equipment():
                                        if item.rarity == "forged":
                                            c = await c._unequip_item(item)
                                    for name, item in c.backpack.items():
                                        if item.rarity == "forged":
                                            tinker_wep.append(item)
                                    for item in tinker_wep:
                                        del c.backpack[item.name]
                                    await self.config.user(ctx.author).set(c._to_json())
                                    if tinker_wep:
                                        await class_msg.edit(
                                            content=box(
                                                _("{} has run off to find a new master.").format(
                                                    humanize_list(tinker_wep)
                                                ),
                                                lang="css",
                                            )
                                        )

                                else:
                                    c.heroclass["ability"] = False
                                    c.heroclass["pet"] = {}
                                    c.heroclass = classes[clz]
                                    await self.config.user(ctx.author).set(c._to_json())
                                    await self._clear_react(class_msg)
                                    await class_msg.edit(
                                        content=box(
                                            _("{} released their pet into the wild.\n").format(
                                                self.E(ctx.author.display_name)
                                            ),
                                            lang="css",
                                        )
                                    )
                                c.heroclass = classes[clz]
                                await self.config.user(ctx.author).set(c._to_json())
                                await self._clear_react(class_msg)
                                return await class_msg.edit(
                                    content=class_msg.content + box(now_class_msg, lang="css")
                                )

                            else:
                                ctx.command.reset_cooldown(ctx)
                                return
                        else:
                            c.heroclass = classes[clz]
                            await self.config.user(ctx.author).set(c._to_json())
                            await self._clear_react(class_msg)
                            return await class_msg.edit(content=box(now_class_msg, lang="css"))
                    else:
                        ctx.command.reset_cooldown(ctx)
                        await ctx.send(
                            _("{}, you need to be at least level 10 to choose a class.").format(
                                self.E(ctx.author.display_name)
                            )
                        )

    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.user)
    async def loot(self, ctx: Context, box_type: str = None, amount: int = 1):
        """This opens one of your precious treasure chests.

        Use the box rarity type with the command: normal, rare, epic or legendary.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        if amount < 1 or amount > 100:
            return await ctx.send(_("Nice try :smirk:"))
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not box_type:
            return await ctx.send(
                box(
                    _(
                        "{author} owns {normal} normal, "
                        "{rare} rare, {epic} epic and {leg} legendary chests."
                    ).format(
                        author=self.E(ctx.author.display_name),
                        normal=str(c.treasure[0]),
                        rare=str(c.treasure[1]),
                        epic=str(c.treasure[2]),
                        leg=str(c.treasure[3]),
                    ),
                    lang="css",
                )
            )
        if box_type == "normal":
            redux = [1, 0, 0, 0]
        elif box_type == "rare":
            redux = [0, 1, 0, 0]
        elif box_type == "epic":
            redux = [0, 0, 1, 0]
        elif box_type == "legendary":
            redux = [0, 0, 0, 1]
        else:
            return await ctx.send(
                _("There is talk of a {} treasure chest but nobody ever saw one.").format(box_type)
            )
        treasure = c.treasure[redux.index(1)]
        if treasure < amount:
            await ctx.send(
                _("{author}, you do not have enough {box} treasure chest to open.").format(
                    author=self.E(ctx.author.display_name), box=box_type
                )
            )
        else:
            async with self.get_lock(ctx.author):
                # atomically save reduced loot count then lock again when saving inside
                # open chests
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                c.treasure[redux.index(1)] -= amount
                await self.config.user(ctx.author).set(c._to_json())
            if amount > 1:
                items = await self._open_chests(ctx, ctx.author, box_type, amount)
                msg = _(
                    "{}, you've opened the following items:\n"
                    "( ATT  |  CHA  |  INT  |  DEX  |  LUCK)"
                ).format(self.E(ctx.author.display_name))
                rjust = max([len(str(i)) for n, i in items.items()])
                for name, item in items.items():
                    att_space = " " if len(str(item.att)) == 1 else ""
                    cha_space = " " if len(str(item.cha)) == 1 else ""
                    int_space = " " if len(str(item.int)) == 1 else ""
                    dex_space = " " if len(str(item.dex)) == 1 else ""
                    luck_space = " " if len(str(item.luck)) == 1 else ""
                    msg += (
                        f"\n {item.owned} - {str(item):<{rjust}} - "
                        f"({att_space}{item.att}  | "
                        f"{int_space}{item.cha}  | "
                        f"{cha_space}{item.int}  | "
                        f"{dex_space}{item.dex}  | "
                        f"{luck_space}{item.luck} )"
                    )
                msgs = []
                for page in pagify(msg):
                    msgs.append(box(page, lang="css"))
                await menu(ctx, msgs, DEFAULT_CONTROLS)
            else:
                await self._open_chest(ctx, ctx.author, box_type)  # returns item and msg

    @commands.command(name="negaverse", aliases=["nv"])
    @commands.cooldown(rate=1, per=10, type=commands.BucketType.user)
    @commands.guild_only()
    async def _negaverse(self, ctx: Context, offering: int = None):
        """This will send you to fight a nega-member!

        `[p]negaverse offering`
        'offering' in this context is the amount of currency you are sacrificing for this fight.
        """
        bal = await bank.get_balance(ctx.author)
        currency_name = await bank.get_currency_name(ctx.guild)

        if not offering:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                _(
                    "{author}, you need to specify how many "
                    "{currency_name} you are willing to offer to the gods for your success."
                ).format(author=self.E(ctx.author.display_name), currency_name=currency_name)
            )
        if offering <= 500 or bal <= 500:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(_("The gods refuse your pitiful offering."))
        if offering > bal:
            offering = bal

        nv_msg = await ctx.send(
            _(
                "{author}, this will cost you at least {offer} {currency_name}.\n"
                "You currently have {bal}. Do you want to proceed?"
            ).format(
                author=self.E(ctx.author.display_name),
                offer=offering,
                currency_name=currency_name,
                bal=bal,
            )
        )
        start_adding_reactions(nv_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(nv_msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await self._clear_react(nv_msg)
            return
        if not pred.result:
            try:
                ctx.command.reset_cooldown(ctx)
                await nv_msg.edit(
                    content=_("{} decides against visiting the negaverse... for now.").format(
                        self.E(ctx.author.display_name)
                    )
                )
                return await self._clear_react(nv_msg)
            except discord.errors.Forbidden:
                pass

        entry_roll = random.randint(1, 20)
        if entry_roll == 1:
            tax_mod = random.randint(4, 8)
            tax = round(bal / tax_mod)
            if tax > offering:
                loss = tax
            else:
                loss = offering
            await bank.withdraw_credits(ctx.author, loss)
            entry_msg = _(
                "A swirling void slowly grows and you watch in horror as it rushes to "
                "wash over you, leaving you cold... and your coin pouch significantly lighter. "
                "The portal to the negaverse remains closed."
            )
            return await nv_msg.edit(content=entry_msg)
        else:
            entry_msg = _(
                "Shadowy hands reach out to take your offering from you and a swirling "
                "black void slowly grows and engulfs you, transporting you to the negaverse."
            )
            await nv_msg.edit(content=entry_msg)
            await self._clear_react(nv_msg)
            await bank.withdraw_credits(ctx.author, offering)

        negachar = bold(f"Nega-{self.E(random.choice(ctx.message.guild.members).display_name)}")
        nega_msg = await ctx.send(
            _("{author} enters the negaverse and meets {negachar}.").format(
                author=bold(ctx.author.display_name), negachar=negachar
            )
        )
        roll = random.randint(1, 20)
        versus = random.randint(1, 20)
        xp_mod = random.randint(1, 10)
        if roll == 1:
            loss_mod = random.randint(1, 10)
            loss = round((offering / loss_mod) * 3)
            try:
                await bank.withdraw_credits(ctx.author, loss)
                loss_msg = ""
            except ValueError:
                await bank.set_balance(ctx.author, 0)
                loss = _("all of their")
            loss_msg = _(
                ", losing {loss} {currency_name} as {negachar} rifled through their belongings"
            ).format(loss=loss, currency_name=currency_name, negachar=negachar)
            await nega_msg.edit(
                content=_(
                    "{content}\n{author} fumbled and died to {negachar}'s savagery{loss_msg}."
                ).format(
                    content=nega_msg.content,
                    author=bold(ctx.author.display_name),
                    negachar=negachar,
                    loss_msg=loss_msg,
                )
            )
        elif roll == 20:
            await nega_msg.edit(
                content=_(
                    "{content}\n{author} decapitated {negachar}. You gain {xp_gain} xp and take "
                    "{offering} {currency_name} back from the shadowy corpse."
                ).format(
                    content=nega_msg.content,
                    author=bold(ctx.author.display_name),
                    negachar=negachar,
                    xp_gain=int(offering / xp_mod),
                    offer=offering,
                    currency_name=currency_name,
                )
            )
            await self._add_rewards(
                ctx, ctx.message.author, (int(offering / xp_mod)), offering, False
            )
        elif roll > versus:
            await nega_msg.edit(
                content=_(
                    "{content}\n{author} "
                    "🎲({roll}) bravely defeated {negachar} 🎲({versus}). "
                    "You gain {xp_gain} xp."
                ).format(
                    content=nega_msg.content,
                    author=bold(ctx.author.display_name),
                    roll=roll,
                    negachar=negachar,
                    versus=versus,
                    xp_gain=int(offering / xp_mod),
                )
            )
            await self._add_rewards(ctx, ctx.message.author, (int(offering / xp_mod)), 0, False)
        elif roll == versus:
            await nega_msg.edit(
                content=_(
                    "{content}\n{author} " "🎲({roll}) almost killed {negachar} 🎲({versus})."
                ).format(
                    content=nega_msg.content,
                    author=bold(ctx.author.display_name),
                    roll=roll,
                    negachar=negachar,
                    versus=versus,
                )
            )
        else:
            loss = round(offering * 0.8)
            try:
                await bank.withdraw_credits(ctx.author, loss)
                loss_msg = ""
            except ValueError:
                await bank.set_balance(ctx.author, 0)
                loss = _("all of their")
            loss_msg = _(
                ", losing {loss} {currency_name} as {negachar} looted their backpack"
            ).format(loss=loss, currency_name=currency_name, negachar=negachar)
            await nega_msg.edit(
                content=_(
                    "{author} 🎲({roll}) was killed by {negachar} 🎲({versus}){loss_msg}."
                ).format(
                    author=bold(ctx.author.display_name),
                    roll=roll,
                    negachar=negachar,
                    versus=versus,
                    loss_msg=loss_msg,
                )
            )

    @commands.group(autohelp=False)
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.user)
    async def pet(self, ctx):
        """[Ranger Class Only]

        This allows a Ranger to tame or set free a pet or send it foraging.
        (2h cooldown)
        """

        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Ranger":
            return await ctx.send(
                box(
                    _("{}, you need to be a Ranger to do this.").format(
                        self.E(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        if ctx.invoked_subcommand is None:
            if c.heroclass["pet"]:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    box(
                        _(
                            "{author}, you already have a pet. "
                            "Try foraging ({prefix}pet forage)."
                        ).format(author=self.E(ctx.author.display_name), prefix=ctx.prefix),
                        lang="css",
                    )
                )
            async with self.get_lock(ctx.author):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                pet = random.choice(list(self.PETS.keys()))
                roll = random.randint(1, 20)
                dipl_value = roll + c.cha + c.skill["cha"]

                pet_msg = box(
                    _("{} is trying to tame a pet.").format(self.E(ctx.author.display_name)),
                    lang="css",
                )
                user_msg = await ctx.send(pet_msg)
                await asyncio.sleep(2)
                pet_msg2 = box(
                    _(
                        "{author} started tracking a wild {pet_name} with a roll of 🎲({roll})."
                    ).format(
                        author=self.E(ctx.author.display_name),
                        pet_name=self.PETS[pet]["name"],
                        roll=roll,
                    ),
                    lang="css",
                )
                await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}")
                await asyncio.sleep(2)
                bonus = ""
                if roll == 1:
                    bonus = _("But they stepped on a twig and scared it away.")
                elif roll == 20:
                    bonus = _("They happen to have its favorite food.")
                    dipl_value += 10
                if dipl_value > self.PETS[pet]["cha"] and roll > 1:
                    pet_msg3 = box(
                        _("{bonus}\nThey successfully tamed the {pet_name}.").format(
                            bonus=bonus, pet_name=self.PETS[pet]["name"]
                        ),
                        lang="css",
                    )
                    await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}")
                    c.heroclass["pet"] = self.PETS[pet]
                    await self.config.user(ctx.author).set(c._to_json())
                else:
                    pet_msg3 = box(
                        _("{bonus}\nThe {pet_name} escaped.").format(
                            bonus=bonus, pet_name=self.PETS[pet]["name"]
                        ),
                        lang="css",
                    )
                    await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}")

    @pet.command(name="forage")
    async def _forage(self, ctx):
        """
            Use your pet to forage for items!
        """
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Ranger":
            return await ctx.send(
                box(
                    _("{}, you need to be a Ranger to do this.").format(
                        self.E(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        if not c.heroclass["pet"]:
            return await ctx.send(
                box(
                    _("{}, you need to have a pet to do this.").format(
                        self.E(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        if "forage" not in c.heroclass:
            c.heroclass["forage"] = 7201
        if c.heroclass["forage"] <= time.time() - 7200:
            await self._open_chest(ctx, c.heroclass["pet"]["name"], "pet")
            async with self.get_lock(ctx.author):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                c.heroclass["forage"] = time.time()
                await self.config.user(ctx.author).set(c._to_json())
        else:
            cooldown_time = (c.heroclass["forage"] + 7200) - time.time()
            return await ctx.send(
                _("This command is on cooldown. Try again in {:g}s").format(cooldown_time)
            )

    @pet.command(name="free")
    async def _free(self, ctx):
        """
            Free your pet :cry:
        """
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Ranger":
            return await ctx.send(
                box(
                    _("{}, you need to be a Ranger to do this.").format(
                        self.E(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        if c.heroclass["pet"]:
            async with self.get_lock(ctx.author):
                c.heroclass["pet"] = {}
                await self.config.user(ctx.author).set(c._to_json())
            return await ctx.send(
                box(
                    "{} released their pet into the wild.".format(self.E(ctx.author.display_name)),
                    lang="css",
                )
            )
        else:
            return await ctx.send(box(_("You don't have a pet."), lang="css"))

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def bless(self, ctx):
        """[Cleric Class Only]

        This allows a praying Cleric to add substantial bonuses for heroes fighting the battle.
        (10 minute cooldown)
        """

        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Cleric":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                _("{}, you need to be a Cleric to do this.").format(
                    self.E(ctx.author.display_name)
                )
            )
        else:
            if c.heroclass["ability"]:
                return await ctx.send(
                    _("{}, ability already in use.").format(self.E(ctx.author.display_name))
                )
            c.heroclass["ability"] = True
            async with self.get_lock(c.user):
                await self.config.user(ctx.author).set(c._to_json())
            await ctx.send(
                _("📜 {} is starting an inspiring sermon. 📜").format(
                    bold(self.E(ctx.author.display_name))
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def rage(self, ctx):
        """[Berserker Class Only]

        This allows a Berserker to add substantial attack bonuses for one battle.
        (10 minute cooldown)
        """

        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Berserker":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                _("{}, you need to be a Berserker to do this.").format(
                    self.E(ctx.author.display_name)
                )
            )
        else:
            if c.heroclass["ability"] is True:
                return await ctx.send(
                    _("{}, ability already in use.").format(self.E(ctx.author.display_name))
                )
            c.heroclass["ability"] = True
            async with self.get_lock(c.user):
                await self.config.user(ctx.author).set(c._to_json())
            await ctx.send(
                _("🗯️ {} is starting to froth at the mouth...🗯️").format(
                    bold(self.E(ctx.author.display_name))
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def focus(self, ctx):
        """[Wizard Class Only]

        This allows a Wizard to add substantial magic bonuses for one battle.
        (10 minute cooldown)
        """

        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Wizard":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                _("{}, you need to be a Wizard to do this.").format(
                    self.E(ctx.author.display_name)
                )
            )
        else:
            if c.heroclass["ability"] is True:
                return await ctx.send(
                    _("{}, ability already in use.").format(self.E(ctx.author.display_name))
                )
            c.heroclass["ability"] = True
            async with self.get_lock(c.user):
                await self.config.user(ctx.author).set(c._to_json())
            await ctx.send(
                _("⚡️ {} is focusing all of their energy...⚡️").format(
                    bold(self.E(ctx.author.display_name))
                )
            )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def music(self, ctx):
        """[Bard Class Only]

        This allows a Bard to add substantial diplomacy bonuses for one battle.
        (10 minute cooldown)
        """

        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Bard":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                _("{}, you need to be a Bard to do this.").format(self.E(ctx.author.display_name))
            )
        else:
            if c.heroclass["ability"]:
                return await ctx.send(
                    _("{}, ability already in use.").format(self.E(ctx.author.display_name))
                )
            c.heroclass["ability"] = True
            async with self.get_lock(c.user):
                await self.config.user(ctx.author).set(c._to_json())
        await ctx.send(
            _("♪♫♬ {} " "is whipping up a performance...♬♫♪").format(
                bold(self.E(ctx.author.display_name))
            )
        )

    @commands.command()
    async def skill(self, ctx: Context, spend: str = None, amount: int = 1):
        """This allows you to spend skillpoints.

        `[p]skill attack/diplomacy/intelligence`
        `[p]skill reset` Will allow you to reset your skill points for a cost.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        if amount < 1:
            return await ctx.send(_("Nice try :smirk:"))
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if spend == "reset":
            bal = c.bal
            currency_name = await bank.get_currency_name(ctx.guild)

            offering = int(bal / 8)
            nv_msg = await ctx.send(
                _(
                    "{author}, this will cost you at least {offering} {currency_name}.\n"
                    "You currently have {bal}. Do you want to proceed?"
                ).format(
                    author=self.E(ctx.author.display_name),
                    offer=offering,
                    currency_name=currency_name,
                    bal=bal,
                )
            )
            start_adding_reactions(nv_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(nv_msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await self._clear_react(nv_msg)
                return

            if pred.result:
                c.skill["pool"] = c.skill["att"] + c.skill["cha"] + c.skill["int"]
                c.skill["att"] = 0
                c.skill["cha"] = 0
                c.skill["int"] = 0
                async with self.get_lock(c.user):
                    await self.config.user(ctx.author).set(c._to_json())
                await bank.withdraw_credits(ctx.author, offering)
                await ctx.send(
                    _("{}, your skill points have been reset.").format(
                        self.E(ctx.author.display_name)
                    )
                )
            else:
                await ctx.send(
                    _("Don't play games with me, {}.").format(self.E(ctx.author.display_name))
                )
            return

        if c.skill["pool"] < amount:
            return await ctx.send(
                _("{}, you do not have unspent skillpoints.").format(
                    self.E(ctx.author.display_name)
                )
            )
        if spend is None:
            await ctx.send(
                _(
                    "{author}, you currently have {skillpoints} unspent skillpoints.\n"
                    "If you want to put them towards a permanent attack, diplomacy or intelligence bonus, use "
                    "`{prefix}skill attack`, `{prefix}skill diplomacy` or  `{prefix}skill intelligence`"
                ).format(
                    author=self.E(ctx.author.display_name),
                    skillpoints=bold(str(c.skill["pool"])),
                    prefix=ctx.prefix,
                )
            )
        else:
            if spend not in ["attack", "diplomacy", "intelligence"]:
                return await ctx.send(
                    _("Don't try to fool me! There is no such thing as {}.").format(spend)
                )
            elif spend == "attack":
                c.skill["pool"] -= amount
                c.skill["att"] += amount
            elif spend == "diplomacy":
                c.skill["pool"] -= amount
                c.skill["cha"] += amount
            elif spend == "intelligence":
                c.skill["pool"] -= amount
                c.skill["int"] += amount
            async with self.get_lock(c.user):
                await self.config.user(ctx.author).set(c._to_json())
            await ctx.send(
                _("{author}, you permanently raised your {spend} value by {amount}.").format(
                    author=self.E(ctx.author.display_name), spend=spend, amount=amount
                )
            )

    @commands.command()
    async def stats(self, ctx: Context, *, user: discord.Member = None):
        """This draws up a charsheet of you or an optionally specified member.

        `[p]stats @locastan`
        will bring up locastans stats.
        `[p]stats` without user will open your stats.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        if user is None:
            user = ctx.author
        if user.bot:
            return
        try:
            c = await Character._from_json(self.config, user)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        msg = await ctx.send(box(c, lang="css"))
        try:
            await msg.add_reaction("\N{CROSS MARK}")
        except discord.errors.Forbidden:
            return
        pred = ReactionPredicate.same_context(msg, ctx.author)
        try:
            react, user = await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            return
        if str(react.emoji) == "\N{CROSS MARK}":
            await msg.delete()

    async def _build_loadout_display(self, userdata):
        form_string = _("Items Equipped:")
        last_slot = ""
        for slot, data in userdata["items"].items():

            if slot == "backpack":
                continue
            if last_slot == "two handed":
                last_slot = slot
                continue

            if not data:
                last_slot = slot
                form_string += _("\n\n {} slot").format(slot.title())
                continue
            item = Item._from_json(data)
            slot_name = userdata["items"][slot]["".join(i for i in data.keys())]["slot"]
            slot_name = slot_name[0] if len(slot_name) < 2 else _("two handed")
            form_string += _("\n\n {} slot").format(slot_name.title())
            last_slot = slot_name
            rjust = max([len(i) for i in data.keys()])
            form_string += _(
                "\n  - {item:<{rjust}} - (ATT: {item_att} | DPL: {item_cha} | INT: {item_int})"
            ).format(item=str(item), item_att=item.att, item_cha=item.cha, item_int=item.int)

        return form_string + "\n"

    @commands.command()
    async def unequip(self, ctx: Context, *, item: str):
        """This stashes a specified equipped item into your backpack.

        `[p]unequip name of item` or `[p]unequip slot`
        You can only have one of each uniquely named item in your backpack.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send(_("This command is not available in DM's on this bot."))
        async with self.get_lock(ctx.author):
            try:
                c = await Character._from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            slots = [
                "head",
                "neck",
                "chest",
                "gloves",
                "belt",
                "legs",
                "boots",
                "left",
                "right",
                "ring",
                "charm",
            ]
            msg = ""

            if item in slots:
                current_item = getattr(c, item, None)
                await c._unequip_item(current_item)
                msg = _(
                    "{author} removed the {current_item} and put it into their backpack."
                ).format(author=self.E(ctx.author.display_name), current_item=current_item)
            else:
                for current_item in c.current_equipment():
                    if item.lower() in current_item.name.lower():
                        await c._unequip_item(current_item)
                        msg = _(
                            "{author} removed the {current_item} and put it into their backpack."
                        ).format(author=self.E(ctx.author.display_name), current_item=current_item)
            if msg:
                await ctx.send(box(msg, lang="css"))
                await self.config.user(ctx.author).set(c._to_json())
            else:
                await ctx.send(
                    _("{author}, you do not have an item matching {item} equipped.").format(
                        author=self.E(ctx.author.display_name), item=item
                    )
                )

    @commands.command(name="adventure", aliases=["a"])
    @commands.guild_only()
    @commands.cooldown(rate=1, per=125, type=commands.BucketType.guild)
    async def _adventure(self, ctx: Context, *, challenge=None):
        """This will send you on an adventure!

        You play by reacting with the offered emojis.
        """
        if ctx.guild.id in self._sessions:
            return await ctx.send(_("There's already another adventure going on in this server."))
        if challenge and not await ctx.bot.is_owner(ctx.author):
            # Only let the bot owner specify a specific challenge
            challenge = None
        adventure_msg = _("You feel adventurous, {}?").format(self.E(ctx.author.display_name))
        try:
            reward, participants = await self._simple(ctx, adventure_msg, challenge)
        except Exception:
            log.error("Something went wrong controlling the game", exc_info=True)
            return
        reward_copy = reward.copy()
        for userid, rewards in reward_copy.items():
            if not rewards:
                pass
            else:
                user = ctx.guild.get_member(userid)  # bot.get_user breaks sometimes :ablobsweats:
                if user is None:
                    # sorry no rewards if you leave the server
                    continue
                await self._add_rewards(
                    ctx, user, rewards["xp"], rewards["cp"], rewards["special"]
                )
                self._rewards[userid] = {}
        if participants:
            for user in participants:  # reset activated abilities
                async with self.get_lock(user):
                    try:
                        c = await Character._from_json(self.config, user)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        continue
                    if c.heroclass["name"] != "Ranger" and c.heroclass["ability"]:
                        c.heroclass["ability"] = False
                        await self.config.user(user).set(c._to_json())
        del self._sessions[ctx.guild.id]

    async def get_challenge(self, ctx):
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            possible_monsters = random.choice(list(self.MONSTERS.keys()))
        possible_monsters = []
        for m, stats in self.MONSTERS.items():
            if c.lvl < 20:
                if stats["hp"] < (c.lvl * 20):
                    possible_monsters.append(m)
            else:
                possible_monsters.append(m)
        log.debug(possible_monsters)
        return random.choice(possible_monsters)

    async def _simple(self, ctx: Context, adventure_msg, challenge=None):

        text = ""
        if challenge and challenge.title() in list(self.MONSTERS.keys()):
            challenge = challenge.title()
        else:
            challenge = await self.get_challenge(ctx)
        attribute = random.choice(list(self.ATTRIBS.keys()))

        if self.MONSTERS[challenge]["boss"]:
            timer = 120
            text = box(_("\n [{} Alarm!]").format(challenge), lang="css")
            self.bot.dispatch("adventure_boss", ctx)  # dispatches an event on bosses
        elif self.MONSTERS[challenge]["miniboss"]:
            timer = 60
            self.bot.dispatch("adventure_miniboss", ctx)
        else:
            timer = 30
            self.bot.dispatch("adventure", ctx)
        self._sessions[ctx.guild.id] = GameSession(
            challenge=challenge,
            attribute=attribute,
            guild=ctx.guild,
            boss=self.MONSTERS[challenge]["boss"],
            miniboss=self.MONSTERS[challenge]["miniboss"],
            timer=timer,
            monster=self.MONSTERS[challenge],
        )
        adventure_msg = (
            f"{adventure_msg}{text}\n{random.choice(self.LOCATIONS)}\n"
            f"**{self.E(ctx.author.display_name)}**{random.choice(self.RAISINS)}"
        )
        await self._choice(ctx, adventure_msg)
        rewards = self._rewards
        participants = self._sessions[ctx.guild.id].participants
        return (rewards, participants)

    async def _choice(self, ctx: Context, adventure_msg):
        session = self._sessions[ctx.guild.id]

        dragon_text = _(
            "but **a{attr} {chall}** just landed in front of you glaring! \n\n"
            "What will you do and will other heroes be brave enough to help you?\n"
            "Heroes have 2 minutes to participate via reaction:"
        ).format(attr=session.attribute, chall=session.challenge)
        basilisk_text = _(
            "but **a{attr} {chall}** stepped out looking around. \n\n"
            "What will you do and will other heroes help your cause?\n"
            "Heroes have 1 minute to participate via reaction:"
        ).format(attr=session.attribute, chall=session.challenge)
        normal_text = _(
            "but **a{attr} {chall}** "
            "is guarding it with{threat}. \n\n"
            "What will you do and will other heroes help your cause?\n"
            "Heroes have 30s to participate via reaction:"
        ).format(
            attr=session.attribute, chall=session.challenge, threat=random.choice(self.THREATEE)
        )

        timer = await self._adv_countdown(ctx, session.timer, _("Time remaining: "))
        self.tasks.append(timer)
        embed = discord.Embed(colour=discord.Colour.blurple())
        use_embeds = (
            await self.config.guild(ctx.guild).embed()
            and ctx.channel.permissions_for(ctx.me).embed_links
        )
        if session.boss:
            if use_embeds:
                embed.description = f"{adventure_msg}\n{dragon_text}"
                embed.colour = discord.Colour.dark_red()
                if session.monster["image"]:
                    embed.set_image(url=session.monster["image"])
                adventure_msg = await ctx.send(embed=embed)
            else:
                adventure_msg = await ctx.send(f"{adventure_msg}\n{dragon_text}")
            timeout = 120

        elif session.miniboss:
            if use_embeds:
                embed.description = f"{adventure_msg}\n{basilisk_text}"
                embed.colour = discord.Colour.dark_green()
                if session.monster["image"]:
                    embed.set_image(url=session.monster["image"])
                adventure_msg = await ctx.send(embed=embed)
            else:
                adventure_msg = await ctx.send(f"{adventure_msg}\n{basilisk_text}")
            timeout = 60
        else:
            if use_embeds:
                embed.description = f"{adventure_msg}\n{normal_text}"
                if session.monster["image"]:
                    embed.set_thumbnail(url=session.monster["image"])
                adventure_msg = await ctx.send(embed=embed)
            else:
                adventure_msg = await ctx.send(f"{adventure_msg}\n{normal_text}")
            timeout = 30
        session.message_id = adventure_msg.id
        start_adding_reactions(adventure_msg, self._adventure_actions, ctx.bot.loop)
        try:
            await asyncio.wait_for(timer, timeout=timeout + 5)
        except Exception:
            timer.cancel()
            log.error("Error with the countdown timer", exc_info=True)
            pass

        return await self._result(ctx, adventure_msg)

    async def local_perms(self, user):
        """Check the user is/isn't locally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(user):
            return True
        guild_settings = self.bot.db.guild(user.guild)
        local_blacklist = await guild_settings.blacklist()
        local_whitelist = await guild_settings.whitelist()

        _ids = [r.id for r in user.roles if not r.is_default()]
        _ids.append(user.id)
        if local_whitelist:
            return any(i in local_whitelist for i in _ids)

        return not any(i in local_blacklist for i in _ids)

    async def global_perms(self, user):
        """Check the user is/isn't globally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(user):
            return True

        whitelist = await self.bot.db.whitelist()
        if whitelist:
            return user.id in whitelist

        return user.id not in await self.bot.db.blacklist()

    @listener()  # 3.1 backwards compatibility fix Thanks Sinbad!
    async def on_reaction_add(self, reaction, user):
        """This will be a cog level reaction_add listener for game logic"""
        if user.bot:
            return
        try:
            guild = user.guild
        except AttributeError:
            return
        if not await self.local_perms(user) or not await self.global_perms(user):
            return
        log.debug("reactions working")
        emojis = ReactionPredicate.NUMBER_EMOJIS[:5] + self._adventure_actions
        if str(reaction.emoji) not in emojis:
            log.debug("emoji not in pool")
            return
        guild = user.guild
        if guild.id in self._sessions:
            if reaction.message.id == self._sessions[guild.id].message_id:
                await self._handle_adventure(reaction, user)
        if guild.id in self._current_traders:
            if reaction.message.id == self._current_traders[guild.id]["msg"]:
                log.debug("handling cart")
                if user in self._current_traders[guild.id]["users"]:
                    return
                await self._handle_cart(reaction, user)

    async def _handle_adventure(self, reaction, user):
        action = {v: k for k, v in self._adventure_controls.items()}[str(reaction.emoji)]
        log.debug(action)
        session = self._sessions[user.guild.id]
        for x in ["fight", "magic", "talk", "pray", "run"]:
            if x == action:
                continue
            if user in getattr(session, x):
                symbol = self._adventure_controls[x]
                getattr(session, x).remove(user)
                try:
                    symbol = self._adventure_controls[x]
                    await reaction.message.remove_reaction(symbol, user)
                except Exception:
                    # print(e)
                    pass
        if user not in getattr(session, action):
            getattr(session, action).append(user)

    async def _handle_cart(self, reaction, user):
        guild = user.guild
        emojis = ReactionPredicate.NUMBER_EMOJIS[:5]
        itemindex = emojis.index(str(reaction.emoji)) - 1
        items = self._current_traders[guild.id]["stock"][itemindex]
        self._current_traders[guild.id]["users"].append(user)
        spender = user
        channel = reaction.message.channel
        currency_name = await bank.get_currency_name(guild)
        item_data = box(items["itemname"] + " - " + str(items["price"]), lang="css")
        to_delete = await channel.send(
            _("{user}, how many {item} would you like to buy?").format(
                user=user.mention, item=item_data
            )
        )
        ctx = await self.bot.get_context(reaction.message)
        ctx.author = user
        pred = MessagePredicate.valid_int(ctx)
        try:
            await self.bot.wait_for("message", check=pred, timeout=30)
        except asyncio.TimeoutError:
            self._current_traders[guild.id]["users"].remove(user)
            return
        if pred.result < 1:
            await to_delete.delete()
            await ctx.send(_("You're wasting my time."))
            self._current_traders[guild.id]["users"].remove(user)
            return
        if await bank.can_spend(spender, int(items["price"]) * pred.result):
            await bank.withdraw_credits(spender, int(items["price"]) * pred.result)
            async with self.get_lock(user):
                try:
                    c = await Character._from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                if "chest" in items["itemname"]:
                    if items["itemname"] == ".rare_chest":
                        c.treasure[1] += pred.result
                    elif items["itemname"] == "[epic chest]":
                        c.treasure[2] += pred.result
                    else:
                        c.treasure[0] += pred.result
                else:
                    item = items["item"]
                    item.owned = pred.result
                    log.debug(item.name)
                    if item.name in c.backpack:
                        log.debug("item already in backpack")
                        c.backpack[item.name].owned += pred.result
                    else:
                        c.backpack[item.name] = item
                await self.config.user(user).set(c._to_json())
                await to_delete.delete()
                await channel.send(
                    box(
                        _(
                            "{author} bought {p_result} {item_name} for "
                            "{item_price} {currency_name} and put it into their backpack."
                        ).format(
                            author=self.E(user.display_name),
                            p_result=pred.result,
                            item_name=items["itemname"],
                            item_price=str(items["price"] * pred.result),
                            currency_name=currency_name,
                        ),
                        lang="css",
                    )
                )
                self._current_traders[guild.id]["users"].remove(user)
        else:
            await to_delete.delete()
            await channel.send(
                _("{author}, you do not have enough {currency_name}.").format(
                    author=self.E(user.display_name), currency_name=currency_name
                )
            )
            self._current_traders[guild.id]["users"].remove(user)

    async def _result(self, ctx: commands.Context, message: discord.Message):
        calc_msg = await ctx.send(_("Calculating..."))
        attack = 0
        diplomacy = 0
        magic = 0
        fumblelist: list = []
        critlist: list = []
        failed = False
        session = self._sessions[ctx.guild.id]
        people = len(session.fight) + len(session.talk) + len(session.pray) + len(session.magic)

        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:  # cannot remove all reactions
            pass
            # for key in controls.keys():
            # await message.remove_reaction(key, ctx.bot.user)

        fight_list = session.fight
        talk_list = session.talk
        pray_list = session.pray
        run_list = session.run
        magic_list = session.magic

        challenge = session.challenge

        attack, diplomacy, magic, run_msg = await self.handle_run(
            ctx.guild.id, attack, diplomacy, magic
        )
        failed = await self.handle_basilisk(ctx, failed)
        fumblelist, attack, diplomacy, magic, pray_msg = await self.handle_pray(
            ctx.guild.id, fumblelist, attack, diplomacy, magic
        )
        fumblelist, critlist, diplomacy, talk_msg = await self.handle_talk(
            ctx.guild.id, fumblelist, critlist, diplomacy
        )

        # need to pass challenge because we need to query MONSTERS[challenge]["pdef"] (and mdef)
        fumblelist, critlist, attack, magic, fight_msg = await self.handle_fight(
            ctx.guild.id, fumblelist, critlist, attack, magic, challenge
        )

        result_msg = run_msg + pray_msg + talk_msg + fight_msg
        challenge_attrib = session.attribute

        hp = self.MONSTERS[challenge]["hp"] * self.ATTRIBS[challenge_attrib][0]
        dipl = self.MONSTERS[challenge]["dipl"] * self.ATTRIBS[challenge_attrib][1]

        slain = (attack + magic) >= hp
        persuaded = diplomacy >= dipl
        damage_str = ""
        diplo_str = ""
        if attack or magic:
            damage_str = _("The group {status} {challenge} **({result}/{int_hp})**.\n").format(
                status=_("hit the") if not slain else _("killed the"),
                challenge=challenge,
                result=attack + magic,
                int_hp=int(hp),
            )
        if diplomacy:
            diplo_str = _(
                "The group {status} the {challenge} with {how}" " **({diplomacy}/{int_dipl})**.\n"
            ).format(
                status=_("tried to persuade") if not persuaded else _("distracted"),
                challenge=challenge,
                how=_("flattery") if not persuaded else _("insults"),
                diplomacy=diplomacy,
                int_dipl=int(dipl),
            )
        result_msg = result_msg + "\n" + damage_str + diplo_str

        fight_name_list = []
        wizard_name_list = []
        talk_name_list = []
        pray_name_list = []
        for user in fight_list:
            fight_name_list.append(self.E(user.display_name))
        for user in magic_list:
            wizard_name_list.append(self.E(user.display_name))
        for user in talk_list:
            talk_name_list.append(self.E(user.display_name))
        for user in pray_list:
            pray_name_list.append(self.E(user.display_name))

        fighters = " and ".join(
            [", ".join(fight_name_list[:-1]), fight_name_list[-1]]
            if len(fight_name_list) > 2
            else fight_name_list
        )
        wizards = " and ".join(
            [", ".join(wizard_name_list[:-1]), wizard_name_list[-1]]
            if len(wizard_name_list) > 2
            else wizard_name_list
        )
        talkers = " and ".join(
            [", ".join(talk_name_list[:-1]), talk_name_list[-1]]
            if len(talk_name_list) > 2
            else talk_name_list
        )
        preachermen = " and ".join(
            [", ".join(pray_name_list[:-1]), pray_name_list[-1]]
            if len(pray_name_list) > 2
            else pray_name_list
        )
        await calc_msg.delete()
        text = ""
        if slain or persuaded and not failed:
            CR = hp + dipl
            treasure = [0, 0, 0, 0]
            if (
                session.miniboss
            ):  # rewards 50:50 rare:normal chest for killing something like the basilisk
                treasure = random.choice([[0, 1, 0, 0], [1, 0, 0, 0]])
            elif CR >= 600:  # super hard stuff
                treasure = [0, 0, 1, 0]  # guaranteed epic
            elif CR >= 320:  # rewards 50:50 rare:epic chest for killing hard stuff.
                treasure = random.choice([[0, 0, 1, 0], [0, 1, 0, 0]])
            elif CR >= 180:  # rewards 50:50 rare:normal chest for killing hardish stuff
                treasure = random.choice([[1, 0, 0, 0], [0, 1, 0, 0]])
            elif (
                CR >= 80
            ):  # small chance of a normal chest on killing stuff that's not terribly weak
                roll = random.randint(1, 5)
                if roll == 1:
                    treasure = [1, 0, 0, 0]

            if session.boss:  # always rewards at least an epic chest.
                # roll for legendary chest
                roll = random.randint(1, 100)
                if roll <= 20:
                    treasure[3] += 1
                else:
                    treasure[2] += 1
            if len(critlist) != 0:
                treasure[0] += 1
            if treasure == [0, 0, 0, 0]:
                treasure = False
        if session.miniboss and failed:
            session.participants = set(
                fight_list + talk_list + pray_list + magic_list + run_list + fumblelist
            )
            currency_name = await bank.get_currency_name(ctx.guild)
            repair_list = []
            for user in session.participants:
                try:
                    c = await Character._from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    continue
                multiplier = 0.05
                if c.dex != 0:
                    if c.dex < 0:
                        dex = 1 / abs(c.dex)
                    else:
                        dex = abs(c.dex)
                    multiplier = multiplier / dex
                loss = round(c.bal * multiplier)
                if loss > c.bal:
                    loss == c.bal
                if c.bal > 500:
                    repair_list.append([user, loss])
                    try:
                        await bank.withdraw_credits(user, loss)
                    except ValueError:
                        await bank.set_balance(user, 0)
                        pass
                else:
                    pass
            loss_list = []
            result_msg += session.miniboss["defeat"]
            if len(repair_list) > 0:
                for user, loss in repair_list:
                    loss_list.append(
                        _("{user} used {loss} {currency_name}").format(
                            user=bold(self.E(user.display_name)),
                            loss=str(loss),
                            currency_name=currency_name,
                        )
                    )
                result_msg += _(
                    "\n{loss_list} to repay a passing cleric that unfroze the group."
                ).format(humanize_list(loss_list))
            return await ctx.send(result_msg)
        if session.miniboss and not slain and not persuaded:
            session.participants = set(
                fight_list + talk_list + pray_list + magic_list + run_list + fumblelist
            )
            repair_list = []
            currency_name = await bank.get_currency_name(ctx.guild)
            for user in session.participants:
                try:
                    c = await Character._from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    continue
                multiplier = 0.05
                if c.dex != 0:
                    if c.dex < 0:
                        dex = 1 / abs(c.dex)
                    else:
                        dex = c.dex
                    multiplier = multiplier / dex
                loss = round(c.bal * multiplier)
                if loss > c.bal:
                    loss == c.bal
                if c.bal > 500:
                    repair_list.append([user, loss])
                    try:
                        await bank.withdraw_credits(user, loss)
                    except ValueError:
                        await bank.set_balance(user, 0)
                        pass
                else:
                    pass
            loss_list = []
            if len(repair_list) > 0:
                for user, loss in repair_list:
                    loss_list.append(
                        f"{bold(self.E(user.display_name))} used {str(loss)} {currency_name}"
                    )
            miniboss = session.challenge
            item = session.miniboss["requirements"][0]
            special = session.miniboss["special"]
            result_msg += _(
                "The {item} countered the {miniboss}'s "
                "{special}, but he still managed to kill you."
                "\n{loss_l} to repay a passing "
                "cleric that resurrected the group."
            ).format(
                item=item, miniboss=miniboss, special=special, loss_l=humanize_list(loss_list)
            )
        amount = (hp + dipl) * people
        if people == 1:
            if slain:
                group = fighters if len(fight_list) == 1 else wizards
                text = _("{b_group} has slain the {chall} in an epic battle!").format(
                    b_group=bold(group), chall=session.challenge
                )
                text += await self._reward(
                    ctx,
                    fight_list + magic_list + pray_list,
                    amount,
                    round(((attack if group == fighters else magic) / hp) * 0.2),
                    treasure,
                )

            if persuaded:
                text = _(
                    "{b_talkers} almost died in battle, but confounded the {chall} in the last second."
                ).format(b_talkers=bold(talkers), chall=session.challenge)
                text += await self._reward(
                    ctx, talk_list + pray_list, amount, round((diplomacy / dipl) * 0.2), treasure
                )

            if not slain and not persuaded:
                currency_name = await bank.get_currency_name(ctx.guild)
                repair_list = []
                users = fight_list + magic_list + talk_list + pray_list + run_list + fumblelist
                for user in users:
                    try:
                        c = await Character._from_json(self.config, user)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        continue
                    multiplier = 0.05
                    if c.dex != 0:
                        if c.dex < 0:
                            dex = 1 / abs(c.dex)
                        else:
                            dex = c.dex
                        multiplier = multiplier / dex
                    loss = round(c.bal * multiplier)
                    if loss > c.bal:
                        loss == c.bal
                    if c.bal > 500:
                        repair_list.append([user, loss])
                        try:
                            await bank.withdraw_credits(user, loss)
                        except ValueError:
                            await bank.set_balance(user, 0)
                            pass
                    else:
                        pass
                loss_list = []
                if len(repair_list) > 0:
                    for user, loss in repair_list:
                        loss_list.append(
                            f"{bold(self.E(user.display_name))} used {str(loss)} {currency_name}"
                        )
                repair_text = (
                    ""
                    if not loss_list
                    else f"{humanize_list(loss_list)} " + _("to repair their gear.")
                )
                options = [
                    _("No amount of diplomacy or valiant fighting could save you.\n{}").format(
                        repair_text
                    ),
                    _("This challenge was too much for one hero.\n{}").format(repair_text),
                    _(
                        "You tried your best, but the group couldn't succeed at their attempt.\n{}"
                    ).format(repair_text),
                ]
                text = random.choice(options)
        else:
            if slain and persuaded:
                if len(pray_list) > 0:
                    god = await self.config.god_name()
                    if await self.config.guild(ctx.guild).god_name():
                        god = await self.config.guild(ctx.guild).god_name()
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with flattery, "
                            "{b_wizard} chanted magical incantations and "
                            "{b_preachers} aided in {god}'s name."
                        ).format(
                            b_fighters=bold(fighters),
                            chall=session.challenge,
                            b_talkers=bold(talkers),
                            b_wizard=bold(wizards),
                            b_preachers=bold(preachermen),
                            god=god,
                        )
                    else:
                        group = fighters if len(fight_list) > 0 else wizards
                        text = _(
                            "{b_group} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with flattery and "
                            "{b_preachers} aided in {god}'s name."
                        ).format(
                            b_group=bold(group),
                            chall=session.challenge,
                            b_talkers=bold(talkers),
                            b_preachers=bold(preachermen),
                            god=god,
                        )
                else:
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with insults and "
                            "{b_wizard} chanted magical incantations."
                        ).format(
                            b_fighters=bold(fighters),
                            chall=session.challenge,
                            b_talkers=bold(talkers),
                            b_wizard=bold(wizards),
                        )
                    else:
                        group = fighters if len(fight_list) > 0 else wizards
                        text = _(
                            "{b_group} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with insults."
                        ).format(
                            b_group=bold(group), chall=session.challenge, b_talkers=bold(talkers)
                        )
                text += await self._reward(
                    ctx,
                    fight_list + magic_list + talk_list + pray_list,
                    amount,
                    round((((attack + magic) / hp) + (diplomacy / dipl)) * 0.2),
                    treasure,
                )

            if not slain and persuaded:
                if len(pray_list) > 0:
                    text = _(
                        "{b_talkers} talked the {chall} " "down with {b_preachers}'s blessing."
                    ).format(
                        b_talkers=bold(talkers),
                        chall=session.challenge,
                        b_preachers=bold(preachermen),
                    )
                else:
                    text = _("{b_talkers} talked the {chall} down.").format(
                        b_talkers=bold(talkers), chall=session.challenge
                    )
                text += await self._reward(
                    ctx, talk_list + pray_list, amount, round((diplomacy / dipl) * 0.2), treasure
                )

            if slain and not persuaded:
                if len(pray_list) > 0:
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} killed the {chall} "
                            "in a most heroic battle with a little help from {b_preachers} and "
                            "{b_wizard} chanting magical incantations."
                        ).format(
                            b_fighters=bold(fighters),
                            chall=session.challenge,
                            b_preachers=bold(preachermen),
                            b_wizard=bold(wizards),
                        )
                    else:
                        group = fighters if len(fight_list) > 0 else wizards
                        text = _(
                            "{b_group} killed the {chall} "
                            "in a most heroic battle with a little help from {b_preachers}."
                        ).format(
                            b_group=bold(group),
                            chall=session.challenge,
                            b_preachers=bold(preachermen),
                        )
                else:
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} killed the {chall} "
                            "in a most heroic battle with {b_wizard} chanting magical incantations."
                        ).format(
                            b_fighters=bold(fighters),
                            chall=session.challenge,
                            b_wizard=bold(wizards),
                        )
                    else:
                        group = fighters if len(fight_list) > 0 else wizards
                        text = _("{b_group} killed the {chall} in an epic fight.").format(
                            b_group=bold(group), chall=session.challenge
                        )
                text += await self._reward(
                    ctx,
                    fight_list + magic_list + pray_list,
                    amount,
                    round(((attack + magic) / hp) * 0.2),
                    treasure,
                )

            if not slain and not persuaded:
                currency_name = await bank.get_currency_name(ctx.guild)
                repair_list = []
                users = fight_list + magic_list + talk_list + pray_list + run_list + fumblelist
                for user in users:
                    try:
                        c = await Character._from_json(self.config, user)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        continue
                    multiplier = 0.05
                    if c.dex != 0:
                        if c.dex < 0:
                            dex = 1 / abs(c.dex)
                        else:
                            dex = c.dex
                        multiplier = multiplier / dex
                    loss = round(c.bal * multiplier)
                    if loss > c.bal:
                        loss == c.bal
                    if c.bal > 500:
                        repair_list.append([user, loss])
                        try:
                            await bank.withdraw_credits(user, loss)
                        except ValueError:
                            await bank.set_balance(user, 0)
                            pass
                    else:
                        pass
                loss_list = []
                if len(repair_list) > 0:
                    for user, loss in repair_list:
                        loss_list.append(
                            _("{user} used {loss} {currency_name}").format(
                                user=bold(self.E(user.display_name)),
                                loss=loss,
                                currency_name=currency_name,
                            )
                        )
                repair_text = (
                    ""
                    if not loss_list
                    else _("{} to repair their gear.").format(humanize_list(loss_list))
                )
                options = [
                    _("No amount of diplomacy or valiant fighting could save you.\n{}").format(
                        repair_text
                    ),
                    _("This challenge was too much for the group.\n{}").format(repair_text),
                    _("You tried your best, but couldn't succeed.\n{}").format(repair_text),
                ]
                text = random.choice(options)

        await ctx.send(result_msg + "\n" + text)
        await self._data_check(ctx)
        session.participants = set(
            fight_list + magic_list + talk_list + pray_list + run_list + fumblelist
        )

    async def handle_run(self, guild_id, attack, diplomacy, magic):
        runners = []
        msg = ""
        session = self._sessions[guild_id]
        if len(list(session.run)) != 0:
            for user in session.run:
                attack -= 1
                diplomacy -= 1
                magic -= 1
                runners.append(self.E(user.display_name))
            msg += _("{} just ran away.\n").format(bold(humanize_list(runners)))
        return (attack, diplomacy, magic, msg)

    async def handle_fight(self, guild_id, fumblelist, critlist, attack, magic, challenge):
        session = self._sessions[guild_id]
        pdef = self.MONSTERS[challenge]["pdef"]
        mdef = self.MONSTERS[challenge]["mdef"]
        # make sure we pass this check first
        if len(session.fight + session.magic) >= 1:
            msg = ""
            if len(session.fight) >= 1:
                if pdef >= 1.5:
                    msg += _(
                        "Swords bounce off this monster as it's skin is **almost impenetrable!**\n"
                    )
                elif pdef >= 1.25:
                    msg += _("This monster has **extremely tough** armour!\n")
                elif pdef > 1:
                    msg += _("Swords don't cut this monster **quite as well!**\n")
                elif pdef >= 0.75 and pdef < 1:
                    msg += _("This monster is **soft and easy** to slice!\n")
                elif pdef > 0 and pdef != 1:
                    msg += _(
                        "Swords slice through this monster like a **hot knife through butter!**\n"
                    )
            if len(session.magic) >= 1:
                if mdef >= 1.5:
                    msg += _("Magic? Pfft, your puny magic is **no match** for this creature!\n")
                elif mdef >= 1.25:
                    msg += _("This monster has **substantial magic resistance!**\n")
                elif mdef > 1:
                    msg += _("This monster has increased **magic resistance!**\n")
                elif mdef >= 0.75 and mdef < 1:
                    msg += _("This monster's hide **melts to magic!**\n")
                elif mdef > 0 and mdef != 1:
                    msg += _("Magic spells are **hugely effective** against this monster!\n")
            report = _("Attack Party: ")
        else:
            return (fumblelist, critlist, attack, magic, "")

        for user in session.fight:
            roll = random.randint(1, 20)
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            crit_mod = max(c.dex, c.luck)
            mod = 0
            if crit_mod != 0:
                mod = round(crit_mod / 10)
            crit_roll = random.randint(1 + mod, 20)
            att_value = c.att + c.skill["att"]
            if roll == 1:
                msg += _("{} fumbled the attack.\n").format(bold(self.E(user.display_name)))
                fumblelist.append(user)
                if c.heroclass["name"] == "Berserker" and c.heroclass["ability"]:
                    bonus_roll = random.randint(5, 15)
                    bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                    bonus = max(bonus_roll, int((roll + att_value) * bonus_multi))
                    attack += int((roll - bonus + att_value) / pdef)
                    report += (
                        f"| {bold(self.E(user.display_name))}: "
                        f"🎲({roll}) + 💥{bonus} +🗡{str(att_value)} | "
                    )
            elif crit_roll == 20 or (
                c.heroclass["name"] == "Berserker" and c.heroclass["ability"]
            ):
                ability = ""
                if crit_roll == 20:
                    msg += _("{} landed a critical hit.\n").format(bold(self.E(user.display_name)))
                    critlist.append(user)
                if c.heroclass["ability"]:
                    ability = "🗯️"
                bonus_roll = random.randint(5, 15)
                bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                bonus = max(bonus_roll, int((roll + att_value) * bonus_multi))
                attack += int((roll + bonus + att_value) / pdef)
                bonus = ability + str(bonus)
                report += (
                    f"| {bold(self.E(user.display_name))}: "
                    f"🎲({roll}) +💥{bonus} +🗡{str(att_value)} | "
                )
            else:
                attack += int((roll + att_value) / pdef)
                report += f"| {bold(self.E(user.display_name))}: 🎲({roll}) +🗡{str(att_value)} | "
        for user in session.magic:
            roll = random.randint(1, 20)
            crit_roll = random.randint(1, 20)
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            int_value = c.int + c.skill["int"]
            if roll == 1:
                msg += _("{} almost set themselves on fire.\n").format(
                    bold(self.E(user.display_name))
                )
                fumblelist.append(user)
                if c.heroclass["name"] == "Wizard" and c.heroclass["ability"]:
                    bonus_roll = random.randint(5, 15)
                    bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                    bonus = max(bonus_roll, int((roll + int_value) * bonus_multi))
                    magic += int((roll - bonus + int_value) / mdef)
                    report += (
                        f"| {bold(self.E(user.display_name))}: "
                        f"🎲({roll}) +💥{bonus} +✨{str(int_value)} | "
                    )
            elif crit_roll == 20 or (c.heroclass["name"] == "Wizard" and c.heroclass["ability"]):
                ability = ""
                if crit_roll == 20:
                    msg += _("{} had a surge of energy.\n").format(bold(self.E(user.display_name)))
                    critlist.append(user)
                if c.heroclass["ability"]:
                    ability = "⚡️"
                bonus_roll = random.randint(5, 15)
                bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                bonus = max(bonus_roll, int((roll + int_value) * bonus_multi))
                magic += int((roll + bonus + int_value) / mdef)
                bonus = ability + str(bonus)
                report += (
                    f"| {bold(self.E(user.display_name))}: "
                    f"🎲({roll}) +💥{bonus} +✨{str(int_value)} | "
                )
            else:
                magic += int((roll + int_value) / mdef)
                report += f"| {bold(self.E(user.display_name))}: 🎲({roll}) +✨{str(int_value)} | "
        msg = msg + report + "\n"
        for user in fumblelist:
            if user in session.fight:
                session.fight.remove(user)
            elif user in session.magic:
                session.magic.remove(user)
        return (fumblelist, critlist, attack, magic, msg)

    async def handle_pray(self, guild_id, fumblelist, attack, diplomacy, magic):
        session = self._sessions[guild_id]
        talk_list = session.talk
        pray_list = session.pray
        fight_list = session.fight
        magic_list = session.magic
        god = await self.config.god_name()
        if await self.config.guild(self.bot.get_guild(guild_id)).god_name():
            god = await self.config.guild(self.bot.get_guild(guild_id)).god_name()
        msg = ""
        for user in pray_list:
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            if c.heroclass["name"] == "Cleric" and c.heroclass["ability"]:
                roll = random.randint(1, 20)
                if len(fight_list + talk_list + magic_list) == 0:
                    msg += _(
                        "{} blessed like a madman but nobody was there to receive it.\n"
                    ).format(bold(self.E(user.display_name)))

                if roll == 1:
                    attack -= 5 * len(fight_list)
                    diplomacy -= 5 * len(talk_list)
                    magic -= 5 * len(magic_list)
                    fumblelist.append(user)
                    msg += _(
                        "{user}'s sermon offended the mighty {god}. "
                        "(-{len_f_list}🗡/-{len_t_list}🗨/-{len_m_list}✨)\n"
                    ).format(
                        user=bold(self.E(user.display_name)),
                        god=god,
                        len_f_list=(5 * len(fight_list)),
                        len_t_list=(5 * len(talk_list)),
                        len_m_list=(5 * len(magic_list)),
                    )

                elif roll in range(2, 10):
                    attack += len(fight_list)
                    diplomacy += len(talk_list)
                    magic += len(magic_list)
                    msg += _(
                        "{user} blessed you all in {god}'s name. "
                        "(+{len_f_list}🗡/+{len_t_list}🗨/+{len_m_list}✨)\n"
                    ).format(
                        user=bold(self.E(user.display_name)),
                        god=god,
                        len_f_list=len(fight_list),
                        len_t_list=len(talk_list),
                        len_m_list=len(magic_list),
                    )

                elif roll in range(11, 19):
                    attack += 5 * len(fight_list)
                    diplomacy += 5 * len(talk_list)
                    magic += 5 * len(magic_list)
                    msg += _(
                        "{user} blessed you all in {god}'s name. "
                        "(+{len_f_list}🗡/+{len_t_list}🗨/+{len_m_list}✨)\n"
                    ).format(
                        user=bold(self.E(user.display_name)),
                        god=god,
                        len_f_list=(5 * len(fight_list)),
                        len_t_list=(5 * len(talk_list)),
                        len_m_list=(5 * len(magic_list)),
                    )

                else:
                    attack += 10 * len(fight_list)
                    diplomacy += 10 * len(talk_list)
                    magic += 10 * len(magic_list)
                    msg += _(
                        "{user} turned into an avatar of mighty {god}. "
                        "(+{len_f_list}🗡/+{}🗨/+{len_m_list}✨)\n"
                    ).format(
                        user=bold(self.E(user.display_name)),
                        god=god,
                        len_f_list=(10 * len(fight_list)),
                        len_t_list=(10 * len(talk_list)),
                        len_m_list=(10 * len(magic_list)),
                    )
            else:
                roll = random.randint(1, 4)
                if len(fight_list + talk_list + magic_list) == 0:
                    msg += _("{} prayed like a madman but nobody else helped them.\n").format(
                        bold(self.E(user.display_name))
                    )

                elif roll == 4:
                    attack += 10 * len(fight_list)
                    diplomacy += 10 * len(talk_list)
                    magic += 10 * len(magic_list)
                    msg += _(
                        "{user}'s prayer called upon the mighty {god} to help you. "
                        "(+{len_f_list}🗡/+{len_t_list}🗨/+{len_m_list}✨)\n"
                    ).format(
                        user=bold(self.E(user.display_name)),
                        god=god,
                        len_f_list=(10 * len(fight_list)),
                        len_t_list=(10 * len(talk_list)),
                        len_m_list=(10 * len(magic_list)),
                    )
                else:
                    fumblelist.append(user)
                    msg += _("{}'s prayers went unanswered.\n").format(
                        bold(self.E(user.display_name))
                    )
        for user in fumblelist:
            if user in pray_list:
                pray_list.remove(user)
        return (fumblelist, attack, diplomacy, magic, msg)

    async def handle_talk(self, guild_id, fumblelist, critlist, diplomacy):
        session = self._sessions[guild_id]
        if len(session.talk) >= 1:
            report = _("Talking Party: ")
            msg = ""
        else:
            return (fumblelist, critlist, diplomacy, "")
        for user in session.talk:
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            roll = random.randint(1, 20)
            dipl_value = c.cha + c.skill["cha"]
            if roll == 1:
                msg += _("{} accidentally offended the enemy.\n").format(
                    bold(self.E(user.display_name))
                )
                fumblelist.append(user)
                if c.heroclass["name"] == "Bard" and c.heroclass["ability"]:
                    bonus = random.randint(5, 15)
                    diplomacy += roll - bonus + dipl_value
                    report += (
                        f"| {bold(self.E(user.display_name))} "
                        f"🎲({roll}) +💥{bonus} +🗨{str(dipl_value)} | "
                    )
            elif roll == 20 or c.heroclass["name"] == "Bard" and c.heroclass["ability"]:
                ability = ""
                if roll == 20:
                    msg += _("{} made a compelling argument.\n").format(
                        bold(self.E(user.display_name))
                    )
                    critlist.append(user)
                if c.heroclass["ability"]:
                    ability = "🎵"
                bonus = random.randint(5, 15)
                diplomacy += roll + bonus + dipl_value
                bonus = ability + str(bonus)
                report += (
                    f"| {bold(self.E(user.display_name))} "
                    f"🎲({roll}) +💥{bonus} +🗨{str(dipl_value)} | "
                )
            else:
                diplomacy += roll + dipl_value
                report += f"| {bold(self.E(user.display_name))} 🎲({roll}) +🗨{str(dipl_value)} | "
        msg = msg + report + "\n"
        for user in fumblelist:
            if user in session.talk:
                session.talk.remove(user)
        return (fumblelist, critlist, diplomacy, msg)

    async def handle_basilisk(self, ctx: Context, failed):
        session = self._sessions[ctx.guild.id]
        fight_list = session.fight
        magic_list = session.magic
        talk_list = session.talk
        pray_list = session.pray
        challenge = session.challenge
        if session.miniboss:
            failed = True
            item, slot = session.miniboss["requirements"]
            for user in (
                fight_list + magic_list + talk_list + pray_list
            ):  # check if any fighter has an equipped mirror shield to give them a chance.
                try:
                    c = await Character._from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    continue
                try:
                    current_item = getattr(c, slot)
                    if item in str(current_item):
                        failed = False
                        break
                except KeyError:
                    continue
        else:
            failed = False
        return failed

    async def _add_rewards(self, ctx: Context, user, exp, cp, special):
        async with self.get_lock(user):
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            c.exp += exp
            member = ctx.guild.get_member(user.id)
            try:
                await bank.deposit_credits(member, cp)
            except BalanceTooHigh:
                pass
            lvl_start = c.lvl
            lvl_end = int(c.exp ** (1 / 4))

            if lvl_start < lvl_end:
                # recalculate free skillpoint pool based on new level and already spent points.
                await ctx.send(f"{user.mention} is now level {lvl_end}!")
                c.lvl = lvl_end
                c.skill["pool"] = int(lvl_end / 5) - (
                    c.skill["att"] + c.skill["cha"] + c.skill["int"]
                )
                if c.skill["pool"] > 0:
                    await ctx.send(
                        _("{}, you have skillpoints available.").format(self.E(user.display_name))
                    )
            if special is not False:
                c.treasure = [sum(x) for x in zip(c.treasure, special)]
            await self.config.user(user).set(c._to_json())

    async def _adv_countdown(self, ctx: Context, seconds, title) -> asyncio.Task:
        await self._data_check(ctx)

        async def adv_countdown():
            secondint = int(seconds)
            adv_end = await self._get_epoch(secondint)
            timer, done, sremain = await self._remaining(adv_end)
            message_adv = await ctx.send(f"⏳ [{title}] {timer}s")
            while not done:
                timer, done, sremain = await self._remaining(adv_end)
                self._adventure_countdown[ctx.guild.id] = (timer, done, sremain)
                if done:
                    await message_adv.delete()
                    break
                elif int(sremain) % 5 == 0:
                    await message_adv.edit(content=(f"⏳ [{title}] {timer}s"))
                await asyncio.sleep(1)
            log.debug("Timer countdown done.")

        return ctx.bot.loop.create_task(adv_countdown())

    async def _cart_countdown(self, ctx: Context, seconds, title) -> asyncio.Task:
        await self._data_check(ctx)

        async def cart_countdown():
            secondint = int(seconds)
            cart_end = await self._get_epoch(secondint)
            timer, done, sremain = await self._remaining(cart_end)
            message_cart = await ctx.send(f"⏳ [{title}] {timer}s")
            while not done:
                timer, done, sremain = await self._remaining(cart_end)
                self._trader_countdown[ctx.guild.id] = (timer, done, sremain)
                if done:
                    await message_cart.delete()
                    break
                if int(sremain) % 5 == 0:
                    await message_cart.edit(content=(f"⏳ [{title}] {timer}s"))
                await asyncio.sleep(1)

        return ctx.bot.loop.create_task(cart_countdown())

    @staticmethod
    async def _clear_react(msg):
        try:
            await msg.clear_reactions()
        except discord.errors.Forbidden:
            pass

    async def _data_check(self, ctx):
        try:
            self._adventure_countdown[ctx.guild.id]
        except KeyError:
            self._adventure_countdown[ctx.guild.id] = 0
        try:
            self._rewards[ctx.author.id]
        except KeyError:
            self._rewards[ctx.author.id] = {}
        try:
            self._trader_countdown[ctx.guild.id]
        except KeyError:
            self._trader_countdown[ctx.guild.id] = 0

    @staticmethod
    async def _get_epoch(seconds: int):
        epoch = time.time()
        epoch += seconds
        return epoch

    @listener()  # backwards compatibility 3.1 fix, thanks Sinbad!
    async def on_message(self, message):
        if not message.guild:
            return
        channels = await self.config.guild(message.guild).cart_channels()
        if not channels:
            return
        if message.channel.id not in channels:
            return
        if not message.author.bot:
            try:
                self._last_trade[message.guild.id]
            except KeyError:
                self._last_trade[message.guild.id] = 0
            if self._last_trade[message.guild.id] == 0:
                self._last_trade[message.guild.id] = time.time()
            roll = random.randint(1, 20)
            if roll == 20:
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(5)
                await self._trader(ctx)

    async def _roll_chest(self, chest_type: str, c: Character):
        multiplier = 500 + round(-c.luck * 5)
        if multiplier < 1:
            multiplier = 1
        # -multiplier because higher luck is better negative luck takes away
        roll = random.randint(1, multiplier)
        if chest_type == "pet":
            if roll == 1:
                chance = self.TR_LEGENDARY
            elif roll <= 25:
                chance = self.TR_EPIC
            elif roll > 25 and roll <= 125:
                chance = self.TR_RARE
            elif roll > 125 and roll <= 375:
                chance = self.TR_COMMON
            else:
                return None
        if chest_type == "normal":
            if roll <= 5:
                chance = self.TR_EPIC
            elif roll > 5 and roll <= 125:
                chance = self.TR_RARE
            else:
                chance = self.TR_COMMON
        elif chest_type == "rare":
            if roll <= 5:
                chance = self.TR_EPIC
            elif roll > 5 and roll <= 350:
                chance = self.TR_RARE
            else:
                chance = self.TR_COMMON
        elif chest_type == "epic":
            if roll <= 10:
                chance = self.TR_LEGENDARY
            elif roll > 10 and roll <= 350:
                chance = self.TR_EPIC
            else:
                chance = self.TR_RARE
        elif chest_type == "legendary":
            if roll <= 125:
                chance = self.TR_LEGENDARY
            else:
                chance = self.TR_EPIC
        else:
            chance = self.TR_COMMON
            # not sure why this was put here but just incase someone
            # tries to add a new loot type we give them normal loot instead
        itemname = random.choice(list(chance.keys()))
        return Item._from_json({itemname: chance[itemname]})

    async def _open_chests(self, ctx: Context, user: discord.Member, chest_type: str, amount: int):
        """This allows you you to open multiple chests at once and put them in your inventory"""
        async with self.get_lock(user):
            try:
                c = await Character._from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            items = {}
            for i in range(0, amount):
                item = await self._roll_chest(chest_type, c)
                if item.name in items:
                    items[item.name].owned += 1
                else:
                    items[item.name] = item

            for name, item in items.items():
                if item.name in c.backpack:
                    c.backpack[item.name].owned += item.owned
                else:
                    c.backpack[item.name] = item
            await self.config.user(ctx.author).set(c._to_json())
            return items

    async def _open_chest(self, ctx: Context, user, chest_type):
        if hasattr(user, "display_name"):
            chest_msg = _("{} is opening a treasure chest. What riches lay inside?").format(
                self.E(user.display_name)
            )
        else:
            chest_msg = _("{user}'s {f} is " "foraging for treasure. What will it find?").format(
                user=self.E(ctx.author.display_name), f=(user[:1] + user[1:])
            )
        try:
            c = await Character._from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        open_msg = await ctx.send(box(chest_msg, lang="css"))
        await asyncio.sleep(2)

        item = await self._roll_chest(chest_type, c)
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
        old_item = getattr(c, item.slot[0], None)
        old_stats = ""
        if len(item.slot) > 1:
            slot = _("two handed")
        if hasattr(user, "display_name"):

            chest_msg2 = (
                _("{user} found {item} [{slot}].").format(
                    user=self.E(user.display_name), item=str(item), slot=slot
                )
                + f" (ATT: {str(item.att)}, "
                f"CHA: {str(item.cha)}, "
                f"INT: {str(item.int)}, "
                f"DEX: {str(item.dex)}, "
                f"LUCK: {str(item.luck)}) "
            )
            if old_item:
                old_slot = old_item.slot[0]
                if len(old_item.slot) > 1:
                    old_slot = _("two handed")
                old_stats = (
                    _("You currently have {item} [{slot}] equipped.").format(
                        item=old_item, slot=old_slot
                    )
                    + f" (ATT: {str(old_item.att)}, "
                    f"CHA: {str(old_item.cha)}, "
                    f"INT: {str(old_item.int)}, "
                    f"DEX: {str(old_item.dex)}, "
                    f"LUCK: {str(old_item.luck)}) "
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
                _("The {user} found {item} [{slot}].").format(user=user, item=str(item), slot=slot)
                + f" (ATT: {str(item.att)}, "
                f"CHA: {str(item.cha)}, "
                f"INT: {str(item.int)}, "
                f"DEX: {str(item.dex)}, "
                f"LUCK: {str(item.luck)}), "
            )
            await open_msg.edit(
                content=box(
                    _(
                        "{c_msg}\n{c_msg_2}\nDo you want to equip "
                        "this item, put in your backpack, or sell this item?"
                    ).format(c_msg=chest_msg, c_msg_2=chest_msg2),
                    lang="css",
                )
            )

        start_adding_reactions(open_msg, self._treasure_controls.keys())
        if hasattr(user, "id"):
            pred = ReactionPredicate.with_emojis(
                tuple(self._treasure_controls.keys()), open_msg, user
            )
        else:
            pred = ReactionPredicate.with_emojis(
                tuple(self._treasure_controls.keys()), open_msg, ctx.author
            )
        try:
            react, user = await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await self._clear_react(open_msg)
            async with self.get_lock(ctx.author):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                if item.name in c.backpack:
                    c.backpack[item.name].owned += 1
                else:
                    c.backpack[item.name] = item
                await open_msg.edit(
                    content=(
                        box(
                            _("{user} put the {item} into their backpack.").format(
                                user=self.E(ctx.author.display_name), item=item
                            ),
                            lang="css",
                        )
                    )
                )
                await self.config.user(ctx.author).set(c._to_json())
                return
        await self._clear_react(open_msg)
        if self._treasure_controls[react.emoji] == "sell":
            price = await self._sell(ctx.author, item)
            try:
                await bank.deposit_credits(ctx.author, price)
            except BalanceTooHigh:
                pass
            currency_name = await bank.get_currency_name(ctx.guild)
            if str(currency_name).startswith("<"):
                currency_name = "credits"
            await open_msg.edit(
                content=(
                    box(
                        _("{user} sold the {item} for {price} {currency_name}.").format(
                            user=self.E(ctx.author.display_name),
                            item=item,
                            price=price,
                            currency_name=currency_name,
                        ),
                        lang="css",
                    )
                )
            )
            await self._clear_react(open_msg)
            await self.config.user(ctx.author).set(c._to_json())
        elif self._treasure_controls[react.emoji] == "equip":
            # equip = {"itemname": item[0]["itemname"], "item": item[0]["item"]}
            async with self.get_lock(ctx.author):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                if not getattr(c, item.slot[0]):
                    equip_msg = box(
                        _("{user} equipped {item} ({slot} slot).").format(
                            user=self.E(ctx.author.display_name), item=item, slot=slot
                        ),
                        lang="css",
                    )
                else:
                    equip_msg = box(
                        _(
                            "{user} equipped {item} "
                            "({slot} slot) and put {old_item} into their backpack."
                        ).format(
                            user=self.E(ctx.author.display_name),
                            item=item,
                            slot=slot,
                            old_item=getattr(c, item.slot[0]),
                        ),
                        lang="css",
                    )
                await open_msg.edit(content=equip_msg)
                c = await c._equip_item(item, False)
                await self.config.user(ctx.author).set(c._to_json())
        else:
            # async with self.config.user(ctx.author).all() as userinfo:
            # userinfo["items"]["backpack"].update({item[0]["itemname"]: item[0]["item"]})
            async with self.get_lock(ctx.author):
                try:
                    c = await Character._from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                if item.name in c.backpack:
                    c.backpack[item.name].owned += 1
                else:
                    c.backpack[item.name] = item
                await open_msg.edit(
                    content=(
                        box(
                            _("{user} put the {item} into their backpack.").format(
                                user=self.E(ctx.author.display_name), item=item
                            ),
                            lang="css",
                        )
                    )
                )
                await self._clear_react(open_msg)
                await self.config.user(ctx.author).set(c._to_json())

    @staticmethod
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
        return out, finish, remaining

    async def _reward(self, ctx: Context, userlist, amount, modif, special):
        if modif == 0:
            modif = 0.5
        xp = max(1, round(amount))
        cp = max(1, round(amount * modif))
        rewards_list = []
        phrase = ""
        for user in userlist:
            self._rewards[user.id] = {}
            try:
                c = await Character._from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            roll = random.randint(1, 5)
            if roll == 5 and c.heroclass["name"] == "Ranger" and c.heroclass["pet"]:
                self._rewards[user.id]["xp"] = int(xp * c.heroclass["pet"]["bonus"])
                self._rewards[user.id]["cp"] = int(cp * c.heroclass["pet"]["bonus"])
                percent = round((c.heroclass["pet"]["bonus"] - 1.0) * 100)
                phrase = _(
                    "\n{user} received a {percent}% reward bonus from their {pet_name}."
                ).format(
                    user=bold(self.E(user.display_name)),
                    percent=bold(str(percent)),
                    pet_name=c.heroclass["pet"]["name"],
                )

            else:
                self._rewards[user.id]["xp"] = xp
                self._rewards[user.id]["cp"] = cp
            if special is not False:
                self._rewards[user.id]["special"] = special
            else:
                self._rewards[user.id]["special"] = False
            rewards_list.append(self.E(user.display_name))

        currency_name = await bank.get_currency_name(ctx.guild)
        to_reward = " and ".join(
            [", ".join(rewards_list[:-1]), rewards_list[-1]]
            if len(rewards_list) > 2
            else rewards_list
        )

        word = "has" if len(userlist) == 1 else "have"
        if special is not False and sum(special) == 1:
            types = [" normal", " rare", "n epic", " legendary"]
            chest_type = types[special.index(1)]
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found {cp} {currency_name}. "
                "You also secured **a{chest_type} treasure chest**!"
            ).format(
                b_reward=bold(to_reward),
                word=word,
                xp=xp,
                cp=cp,
                currency_name=currency_name,
                chest_type=chest_type,
            )
        elif special is not False and sum(special) > 1:
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found {cp} {currency_name}. "
                "You also secured **several treasure chests**!"
            ).format(
                b_reward=bold(to_reward), word=word, xp=xp, cp=cp, currency_name=currency_name
            )
        else:
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found {cp} {currency_name}."
            ).format(
                b_reward=bold(to_reward), word=word, xp=xp, cp=cp, currency_name=currency_name
            )
        return phrase

    @staticmethod
    async def _sell(user, item: Item):
        if item.rarity == "legendary":
            base = (2000, 5000)
        elif item.rarity == "epic":
            base = (500, 1000)
        elif item.rarity == "rare":
            base = (100, 500)
        else:
            base = (10, 200)
        price = random.randint(base[0], base[1]) * max([item.att, item.cha, item.int], default=1)
        if item.luck > 0:
            price = price + round(price * (item.luck / 10))
        return price

    async def _trader(self, ctx):

        em_list = ReactionPredicate.NUMBER_EMOJIS[:5]
        react = False
        controls = {em_list[1]: 0, em_list[2]: 1, em_list[3]: 2, em_list[4]: 3}
        cart = await self.config.cart_name()
        if await self.config.guild(ctx.guild).cart_name():
            cart = await self.config.guild(ctx.guild).cart_name()
        text = box(_("[{} is bringing the cart around!]").format(cart), lang="css")
        timeout = await self.config.guild(ctx.guild).cart_timeout()
        if ctx.guild.id not in self._last_trade:
            self._last_trade[ctx.guild.id] = 0

        if self._last_trade[ctx.guild.id] == 0:
            self._last_trade[ctx.guild.id] = time.time()
        elif self._last_trade[ctx.guild.id] >= time.time() - timeout:
            # trader can return after 3 hours have passed since last visit.
            return  # silent return.
        self.bot.dispatch("adventure_cart", ctx)  # dispatch after silent return
        self._last_trade[ctx.guild.id] = time.time()
        stock = await self._trader_get_items()
        currency_name = await bank.get_currency_name(ctx.guild)
        if str(currency_name).startswith("<"):
            currency_name = "credits"
        for index, item in enumerate(stock):
            item = stock[index]
            if "chest" not in item["itemname"]:
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
                        "\n[{i}] {item_name} ("
                        "Attack: {str_att}, "
                        "Intelligence: {str_int}, "
                        "Charisma: {str_cha} "
                        "Luck: {str_luck} "
                        "Dexterity: {str_dex} "
                        "[{hand}]) for {item_price} {currency_name}."
                    ).format(
                        i=str(index + 1),
                        item_name=item["itemname"],
                        str_att=str(att),
                        str_int=str(intel),
                        str_cha=str(cha),
                        str_luck=str(luck),
                        str_dex=str(dex),
                        hand=hand,
                        item_price=item["price"],
                        currency_name=currency_name,
                    ),
                    lang="css",
                )
            else:
                text += box(
                    _("\n[{i}] {item_name} " "for {item_price} {currency_name}.").format(
                        i=str(index + 1),
                        item_name=item["itemname"],
                        item_price=item["price"],
                        currency_name=currency_name,
                    ),
                    lang="css",
                )
        text += _("Do you want to buy any of these fine items? Tell me which one below:")
        msg = await ctx.send(text)
        start_adding_reactions(msg, controls.keys())
        self._current_traders[ctx.guild.id] = {"msg": msg.id, "stock": stock, "users": []}
        timeout = self._last_trade[ctx.guild.id] + 180 - time.time()
        if timeout <= 0:
            timeout = 0
        timer = await self._cart_countdown(ctx, timeout, _("The cart will leave in: "))
        self.tasks.append(timer)
        try:
            await asyncio.wait_for(timer, timeout + 5)
        except asyncio.TimeoutError:
            pass
        try:
            await msg.delete()
        except Exception:
            log.error("Error deleting the cart message", exc_info=True)
            pass

    async def _trader_get_items(self):
        items = {}
        output = {}

        chest_type = random.randint(1, 100)
        while len(items) < 4:
            chance = None
            roll = random.randint(1, 100)
            if chest_type <= 60:
                if roll <= 5:
                    chance = self.TR_EPIC
                elif roll > 5 and roll <= 25:
                    chance = self.TR_RARE
                elif roll >= 90:
                    chest = [1, 0, 0]
                    types = ["normal chest", ".rare_chest", "[epic chest]"]
                    if "normal chest" not in items:
                        items.update(
                            {
                                "normal chest": {
                                    "itemname": _("normal chest"),
                                    "item": chest,
                                    "price": 2000,
                                }
                            }
                        )
                else:
                    chance = self.TR_COMMON
            elif chest_type <= 75:
                if roll <= 15:
                    chance = self.TR_EPIC
                elif roll > 15 and roll <= 45:
                    chance = self.TR_RARE
                elif roll >= 90:
                    chest = random.choice([[0, 1, 0], [1, 0, 0]])
                    types = ["normal chest", ".rare_chest", "[epic chest]"]
                    prices = [2000, 5000, 10000]
                    chesttext = types[chest.index(1)]
                    price = prices[chest.index(1)]
                    if chesttext not in items:
                        items.update(
                            {
                                chesttext: {
                                    "itemname": "{}".format(chesttext),
                                    "item": chest,
                                    "price": price,
                                }
                            }
                        )
                else:
                    chance = self.TR_COMMON
            else:
                if roll <= 25:
                    chance = self.TR_EPIC
                elif roll >= 90:
                    chest = random.choice([[0, 1, 0], [0, 0, 1]])
                    types = ["normal chest", ".rare_chest", "[epic chest]"]
                    prices = [2000, 5000, 10000]
                    chesttext = types[chest.index(1)]
                    price = prices[chest.index(1)]
                    if chesttext not in items:
                        items.update(
                            {
                                chesttext: {
                                    "itemname": "{}".format(chesttext),
                                    "item": chest,
                                    "price": price,
                                }
                            }
                        )
                else:
                    chance = self.TR_RARE

            if chance is not None:
                itemname = random.choice(list(chance.keys()))
                item = Item._from_json({itemname: chance[itemname]})
                if len(item.slot) == 2:  # two handed weapons add their bonuses twice
                    att = item.att * 2
                    cha = item.cha * 2
                    intel = item.int * 2
                else:
                    att = item.att
                    cha = item.cha
                    intel = item.int
                if item.rarity == "epic":
                    price = random.randint(3000, 6000) * max(att + cha + intel, 1)
                elif item.rarity == "rare":
                    price = random.randint(500, 2000) * max(att + cha + intel, 1)
                else:
                    price = random.randint(200, 400) * max(att + cha + intel, 1)
                if itemname not in items:
                    items.update({itemname: {"itemname": itemname, "item": item, "price": price}})

        for index, item in enumerate(items):
            output.update({index: items[item]})
        return output

    # def cog_unload(self): #  another 3.1 change
    def cog_unload(self):
        for task in self.tasks:
            log.debug(f"removing task {task}")
            task.cancel()

    __unload = cog_unload
