import asyncio
import discord
import json
import random
import time
from typing import Optional

from redbot.core import commands, bank, checks, Config
from redbot.core.commands.context import Context
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.chat_formatting import box, pagify, bold, humanize_list, escape
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from .custommenu import menu, start_adding_reactions

BaseCog = getattr(commands, "Cog", object)

E = lambda t: escape(t, mass_mentions=True, formatting=True)


class Adventure(BaseCog):
    """Adventure, derived from the Goblins Adventure cog by locastan"""

    def __init__(self, bot):
        self.bot = bot
        self._last_trade = {}

        self._adventure_actions = {
            "🗡": self._fight,
            "🗨": self._talk,
            "🛐": self._pray,
            "🏃": self._run,
        }
        self._adventure_controls = {"fight": "🗡", "talk": "🗨", "pray": "🛐", "run": "🏃"}
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
        self._adventure_timer = {}
        self._adventure_userlist = {}
        self._challenge = {}
        self._challenge_attrib = {}
        self._rewards = {}
        self._participants = {}
        self._trader_countdown = {}

        self.config = Config.get_conf(self, 2710801001, force_registration=True)

        default_user = {
            "exp": 0,
            "lvl": 1,
            "att": 0,
            "cha": 0,
            "treasure": [0, 0, 0],
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
            "class": {
                "name": "Hero",
                "ability": False,
                "desc": "Your basic adventuring hero.",
                "forage": 0,
            },
            "skill": {"pool": 0, "att": 0, "cha": 0},
        }

        default_guild = {"cart_channels": [], "god_name": "", "cart_name": ""}
        default_global = {"god_name": "Herbert", "cart_name": "Hawl's cart"}

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)

    async def allow_in_dm(self, ctx):
        """Checks if the bank is global and allows the command in dm"""
        if ctx.guild is not None:
            return True
        if ctx.guild is None and await bank.is_global():
            return True
        else:
            return False

    @commands.command(name="backpack")
    async def _backpack(
        self,
        ctx,
        switch: str = "None",
        item: str = "None",
        asking: int = 10,
        buyer: discord.Member = None,
    ):
        """This shows the contents of your backpack.

        Selling: `[p]backpack sell "(partial) name of item"`
        Trading: `[p]backpack trade "name of item" credits @buyer`
        Equip:   `[p]backpack equip "(partial) name of item"`
        or respond with "name of item" to backpack.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")

        userdata = await self.config.user(ctx.author).all()
        bkpk = "Items in Backpack: \n"
        if switch == "None":
            bkpk = self._build_bkpk_display(userdata["items"]["backpack"])
            backpack_contents = (
                f"[{E(ctx.author.display_name)}'s backpack] \n\n\n{bkpk}\n"
                f"(Reply with the name of an item or use {ctx.prefix}backpack "
                "equip 'name of item' to equip it.)"
            )
            for page in pagify(backpack_contents, delims=["\n"], shorten_by=20):
                backpack_message = await ctx.send(box(page, lang="css"))

            try:
                reply = await ctx.bot.wait_for(
                    "message", check=MessagePredicate.same_context(ctx), timeout=30
                )
            except asyncio.TimeoutError:
                return
            if not reply:
                return
            else:
                if (
                    not " sell " in reply.content.lower()
                    and not " trade " in reply.content.lower()
                ):
                    equip = {}
                    for item in userdata["items"]["backpack"]:
                        if reply.content.lower() in item:
                            equip = {"itemname": item, "item": userdata["items"]["backpack"][item]}
                            break
                    if equip != {}:
                        await self._equip_item(ctx, equip, True, backpack_message)
        elif switch == "equip":
            if item == "None" or not any(
                [x for x in userdata["items"]["backpack"] if item in x.lower()]
            ):
                return await ctx.send(
                    f"{E(ctx.author.display_name)}, you have to specify an item from your backpack to equip."
                )
            lookup = list(x for x in userdata["items"]["backpack"] if item.lower() in x.lower())
            if len(lookup) > 1:
                await ctx.send(
                    box(
                        (
                            f"{E(ctx.author.display_name)}, I found multiple items "
                            f"({' and '.join([', '.join(lookup[:-1]), lookup[-1]] if len(lookup) > 2 else lookup)}) "
                            "matching that name in your backpack.\nPlease be more specific."
                        ),
                        lang="css",
                    )
                )
                return
            else:
                item = lookup[0]
                equip = {"itemname": item, "item": userdata["items"]["backpack"][item]}
                await self._equip_item(
                    ctx, equip, True
                )  # equip command with no backpack msg visible
        elif (
            switch == "sell"
        ):  # new logic allows for bulk sales. It also always confirms the sale by yes/no query to avoid accidents.
            if item == "None" or not any(
                [x for x in userdata["items"]["backpack"] if item in x.lower()]
            ):
                await ctx.send(
                    f"{E(ctx.author.display_name)}, you have to specify an item (or partial name) from your backpack to sell."
                )
                return
            lookup = list(x for x in userdata["items"]["backpack"] if item in x.lower())
            if any([x for x in lookup if "{.:'" in x.lower()]):
                device = [x for x in lookup if "{.:'" in x.lower()]
                return await ctx.send(
                    box(
                        f"\n{E(ctx.author.display_name)}, your {device} is refusing to be sold and bit your finger for trying.",
                        lang="css",
                    )
                )
            msg = await ctx.send(
                f"{E(ctx.author.display_name)}, do you want to sell these items {str(lookup)}?"
            )
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            await ctx.bot.wait_for("reaction_add", check=pred)
            try:
                await msg.delete()
            except discord.errors.Forbidden:
                pass
            if pred.result:  # user reacted with Yes.
                for item in lookup:
                    queryitem = {"itemname": item, "item": userdata["items"]["backpack"].get(item)}
                    price = await self._sell(ctx.author, queryitem)
                    async with self.config.user(ctx.author).all() as userdata:
                        del userdata["items"]["backpack"][item]
                    currency_name = await bank.get_currency_name(ctx.guild)
                    if str(currency_name).startswith("<"):
                        currency_name = "credits"
                    await ctx.send(
                        f"{E(ctx.author.display_name)} sold their {item} for {price} {currency_name}."
                    )

        elif switch == "trade":
            if item == "None" or not any(
                [x for x in userdata["items"]["backpack"] if item.lower() in x.lower()]
            ):
                return await ctx.send(
                    f"{E(ctx.author.display_name)}, you have to specify an item from your backpack to trade."
                )
            lookup = list(x for x in userdata["items"]["backpack"] if item.lower() in x.lower())
            if len(lookup) > 1:
                await ctx.send(
                    (
                        f"{E(ctx.author.display_name)}, I found multiple items "
                        f"({' and '.join([', '.join(lookup[:-1]), lookup[-1]] if len(lookup) > 2 else lookup)}) "
                        "matching that name in your backpack.\nPlease be more specific."
                    )
                )
                return
            if any([x for x in lookup if "{.:'" in x.lower()]):
                device = [x for x in lookup if "{.:'" in x.lower()]
                return await ctx.send(
                    box(
                        f"\n{E(ctx.author.display_name)}, your {device} does not want to leave you.",
                        lang="css",
                    )
                )
            else:
                if not buyer:
                    return
                item = lookup[0]
                if (
                    len(userdata["items"]["backpack"][item]["slot"]) == 2
                ):  # two handed weapons add their bonuses twice
                    hand = "two handed"
                    att = userdata["items"]["backpack"][item]["att"] * 2
                    cha = userdata["items"]["backpack"][item]["cha"] * 2
                else:
                    if (
                        userdata["items"]["backpack"][item]["slot"][0] == "right"
                        or userdata["items"]["backpack"][item]["slot"][0] == "left"
                    ):
                        hand = userdata["items"]["backpack"][item]["slot"][0] + " handed"
                    else:
                        hand = userdata["items"]["backpack"][item]["slot"][0] + " slot"
                    att = userdata["items"]["backpack"][item]["att"]
                    cha = userdata["items"]["backpack"][item]["cha"]

                currency_name = await bank.get_currency_name(ctx.guild)
                if str(currency_name).startswith("<"):
                    currency_name = "credits"
                trade_talk = box(
                    (
                        f"{E(ctx.author.display_name)} wants to sell {item}. (Attack: {str(att)}, "
                        f"Charisma: {str(cha)} [{hand}])\n{E(buyer.display_name)}, "
                        f"do you want to buy this item for {str(asking)} {currency_name}?"
                    ),
                    lang="css",
                )
                trade_msg = await ctx.send(f"{buyer.mention}\n{trade_talk}")
                start_adding_reactions(trade_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(trade_msg, buyer)
                await ctx.bot.wait_for("reaction_add", check=pred)
                if pred.result:  # buyer reacted with Yes.
                    try:
                        if await bank.can_spend(buyer, asking):
                            bal = await bank.transfer_credits(buyer, ctx.author, asking)
                            async with self.config.user(ctx.author).all() as give_user:
                                tradeitem = give_user["items"]["backpack"].pop(item)
                            async with self.config.user(buyer).all() as buy_user:
                                buy_user["items"]["backpack"].update({item: tradeitem})
                            await trade_msg.edit(
                                content=(
                                    box(
                                        (
                                            f"\n{E(ctx.author.display_name)} traded {item} to "
                                            f"{E(buyer.display_name)} for {asking} {currency_name}."
                                        ),
                                        lang="css",
                                    )
                                )
                            )
                            await self._clear_react(trade_msg)
                        else:
                            await trade_msg.edit(
                                content=f"{E(buyer.display_name)}, you do not have enough {currency_name}."
                            )
                    except discord.errors.NotFound:
                        pass
                else:
                    try:
                        await trade_msg.delete()
                    except discord.errors.Forbidden:
                        pass

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    async def bless(self, ctx):
        """[Cleric Class Only] 

        This allows a praying Cleric to add substantial bonuses for heroes fighting the battle. 
        (1h cooldown)
        """

        userdata = await self.config.user(ctx.author).all()
        if userdata["class"]["name"] != "Cleric":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{E(ctx.author.display_name)}, you need to be a Cleric to do this."
            )
        else:
            if userdata["class"]["ability"] == True:
                return await ctx.send(f"{E(ctx.author.display_name)}, ability already in use.")
            async with self.config.user(ctx.author).all() as userdata:
                userdata["class"]["ability"] = True
            await ctx.send(
                f"📜 {bold(E(ctx.author.display_name))} is starting an inspiring sermon. 📜"
            )

    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def adventureset(self, ctx):
        """Setup various adventure settings"""

    @adventureset.command()
    async def god(self, ctx, *, name):
        """[Admin] Set the server's name of the god"""
        await self.config.guild(ctx.guild).god_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.is_owner()
    async def globalgod(self, ctx, *, name):
        """[Owner] Set the default name of the god"""
        await self.config.god_name.set(name)
        await ctx.tick()

    @adventureset.command()
    async def cartname(self, ctx, *, name):
        """[Admin] Set the server's name of the cart"""
        await self.config.guild(ctx.guild).cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.is_owner()
    async def globalcartname(self, ctx, *, name):
        """[Owner] Set the default name of the cart"""
        await self.config.cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def cart(self, ctx, *, channel: discord.TextChannel = None):
        """[Admin] Add or remove a text channel that the Trader cart can appear in.

        If the channel is already in the list, it will be removed.
        Use `[p]cart` with no arguments to show the channel list.
        """

        channel_list = await self.config.guild(ctx.guild).cart_channels()
        if not channel_list:
            channel_list = []
        if channel is None:
            msg = "Active Cart Channels:\n"
            if not channel_list:
                msg += "None."
            else:
                name_list = []
                for chan_id in channel_list:
                    name_list.append(self.bot.get_channel(chan_id))
                msg += "\n".join(chan.name for chan in name_list)
            return await ctx.send(box(msg))
        elif channel.id in channel_list:
            new_channels = channel_list.remove(channel.id)
            await ctx.send(f"The {channel} channel has been removed from the cart delivery list.")
            return await self.config.guild(ctx.guild).cart_channels.set(new_channels)
        else:
            channel_list.append(channel.id)
            await ctx.send(f"The {channel} channel has been added to the cart delivery list.")
            await self.config.guild(ctx.guild).cart_channels.set(channel_list)

    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.guild)
    async def convert(self, ctx, box_rarity: str):
        """Convert normal or rare treasure chests to epic.

        Trade 5 normal treasure chests for 1 rare treasure chest.
        Trade 4 rare treasure chests for 1 epic treasure chest.
        """

        # Thanks to flare#0001 for the idea and writing the first instance of this
        userdata = await self.config.user(ctx.author).all()
        if box_rarity.lower() == "normal":
            if userdata["treasure"][0] >= 5:
                async with self.config.user(ctx.author).all() as userinfo:
                    userinfo["treasure"][0] -= 5
                    userinfo["treasure"][1] += 1
                    await ctx.send(
                        box(
                            (
                                f"Successfully converted 5 normal treasure chests to 1 rare treasure chest. "
                                f"\n{E(ctx.author.display_name)} now owns {userinfo['treasure'][0]} normal, "
                                f"{userinfo['treasure'][1]} rare and {userinfo['treasure'][2]} epic treasure chests."
                            ),
                            lang="css",
                        )
                    )
            else:
                await ctx.send(
                    f"{E(ctx.author.display_name)}, you do not have 5 normal treasure chests to convert."
                )
        elif box_rarity.lower() == "rare":
            if userdata["treasure"][1] >= 4:
                async with self.config.user(ctx.author).all() as userinfo:
                    userinfo["treasure"][1] -= 4
                    userinfo["treasure"][2] += 1
                    await ctx.send(
                        box(
                            (
                                f"Successfully converted 4 rare treasure chests to 1 epic treasure chest. "
                                f"\n{E(ctx.author.display_name)} now owns {userinfo['treasure'][0]} normal, "
                                f"{userinfo['treasure'][1]} rare and {userinfo['treasure'][2]} epic treasure chests."
                            ),
                            lang="css",
                        )
                    )
            else:
                await ctx.send(
                    f"{E(ctx.author.display_name)}, you do not have 4 rare treasure chests to convert."
                )
        else:
            await ctx.send(
                f"{E(ctx.author.display_name)}, please select between normal or rare treasure chests to convert."
            )

    @commands.command()
    async def equip(self, ctx, *, item: str = None):
        """This equips an item from your backpack.

        `[p]equip "name of item"`
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        if not item:
            return await ctx.send("Please use an item name with this command.")
        await ctx.invoke(self._backpack, switch="equip", item=item)

    @commands.command()
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    async def forge(self, ctx):
        """[Tinkerer Class Only] 

        This allows a Tinkerer to forge two items into a device. 
        (2h cooldown)
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        userdata = await self.config.user(ctx.author).all()
        if userdata["class"]["name"] != "Tinkerer":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{E(ctx.author.display_name)}, you need to be a Tinkerer to do this."
            )
        else:
            bkpk = ""
            consumed = []
            forgeables = len(userdata["items"]["backpack"]) - sum(
                "{.:'" in x for x in userdata["items"]["backpack"]
            )
            if forgeables <= 1:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    f"{E(ctx.author.display_name)}, you need at least two forgeable items in your backpack to forge."
                )
            backpack_items = userdata["items"]["backpack"]
            for item in backpack_items:
                if "{.:'" not in item:
                    if len(backpack_items[item]["slot"]) == 1:
                        bkpk += (
                            f" - {item} - (ATT: {str(backpack_items[item]['att'])} | "
                            f"DPL: {str(backpack_items[item]['cha'])} [{backpack_items[item]['slot'][0]} slot])\n"
                        )
                    else:
                        bkpk += (
                            f" - {item} - (ATT: {str(backpack_items[item]['att'] * 2)} | "
                            f"DPL: {str(backpack_items[item]['cha'] * 2)} [two handed])\n"
                        )

            await ctx.send(
                (
                    f"```css\n[{E(ctx.author.display_name)}'s forgeables]\n```\n```css\n"
                    f"{bkpk}\n(Reply with the full or partial name of item 1 to select for forging. Try to be specific.)```"
                )
            )
            try:
                reply = await ctx.bot.wait_for(
                    "message", check=MessagePredicate.same_context(ctx), timeout=30
                )
            except asyncio.TimeoutError:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    f"I don't have all day you know, {E(ctx.author.display_name)}."
                )
            item1 = {}
            for item in userdata["items"]["backpack"]:
                if reply.content.lower() in item:
                    if "{.:'" not in item:
                        item1 = userdata["items"]["backpack"].get(item)
                        consumed.append(item)
                        break
                    else:
                        ctx.command.reset_cooldown(ctx)
                        return await ctx.send(
                            f"{E(ctx.author.display_name)}, tinkered devices cannot be reforged."
                        )
            if item1 == {}:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    f"{E(ctx.author.display_name)}, I could not find that item - check your spelling."
                )
            bkpk = ""
            for item in backpack_items:
                if item not in consumed and "{.:'" not in item:
                    if len(backpack_items[item]["slot"]) == 1:
                        bkpk += (
                            f" - {item} - (ATT: {str(backpack_items[item]['att'])} | "
                            f"DPL: {str(backpack_items[item]['cha'])} [{backpack_items[item]['slot'][0]} slot])\n"
                        )
                    else:
                        bkpk += (
                            f" - {item} - (ATT: {str(backpack_items[item]['att'] * 2)} | "
                            f"DPL: {str(backpack_items[item]['cha'] * 2)} [two handed])\n"
                        )
            await ctx.send(
                (
                    f"```css\n[{E(ctx.author.display_name)}'s forgeables]\n```\n```css\n"
                    f"{bkpk}\n(Reply with the full or partial name of item 2 to select for forging. Try to be specific.)```"
                )
            )
            try:
                reply = await ctx.bot.wait_for(
                    "message", check=MessagePredicate.same_context(ctx), timeout=30
                )
            except asyncio.TimeoutError:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    f"I don't have all day you know, {E(ctx.author.display_name)}."
                )
            item2 = {}
            for item in backpack_items:
                if reply.content.lower() in item and reply.content.lower() not in consumed:
                    if "{.:'" not in item:
                        item2 = backpack_items.get(item)
                        consumed.append(item)
                        break
                    else:
                        ctx.command.reset_cooldown(ctx)
                        return await ctx.send(
                            f"{E(ctx.author.display_name)}, tinkered devices cannot be reforged."
                        )
            if item2 == {}:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    f"{E(ctx.author.display_name)}, I could not find that item - check your spelling."
                )

            newitem = await self._to_forge(ctx, item1, item2)
            async with self.config.user(ctx.author).all() as userdata:
                for item in consumed:
                    userdata["items"]["backpack"].pop(item)
            await self._sub_unequip(ctx, "{.:'")
            userdata = await self.config.user(ctx.author).all()
            lookup = list(x for x in userdata["items"]["backpack"] if "{.:'" in x.lower())
            if len(lookup) > 0:
                msg = await ctx.send(
                    box(
                        f"{E(ctx.author.display_name)}, you already have a device. Do you want to replace {', '.join(lookup)}?",
                        lang="css",
                    )
                )
                start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(msg, ctx.author)
                await ctx.bot.wait_for("reaction_add", check=pred)
                try:
                    await msg.delete()
                except discord.errors.Forbidden:
                    pass
                if pred.result:  # user reacted with Yes.
                    for item in lookup:
                        async with self.config.user(ctx.author).all() as userdata:
                            del userdata["items"]["backpack"][item]
                            userdata["items"]["backpack"].update(
                                {newitem["itemname"]: newitem["item"]}
                            )
                        await ctx.send(
                            box(
                                (
                                    f"{E(ctx.author.display_name)}, your new {newitem['itemname']} "
                                    f"consumed {', '.join(lookup)} and is now lurking in your backpack."
                                ),
                                lang="css",
                            )
                        )
                else:
                    return await ctx.send(
                        box(
                            f"{E(ctx.author.display_name)}, {newitem['itemname']} got mad at your rejection and blew itself up.",
                            lang="css",
                        )
                    )
            else:
                async with self.config.user(ctx.author).all() as userdata:
                    userdata["items"]["backpack"].update({newitem["itemname"]: newitem["item"]})
                await ctx.send(
                    box(
                        f"{E(ctx.author.display_name)}, your new {newitem['itemname']} is lurking in your backpack.",
                        lang="css",
                    )
                )

    async def _to_forge(self, ctx, item1, item2):
        newslot = random.choice([item1["slot"], item2["slot"]])
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
        newatt = round((int(item1["att"]) + int(item2["att"])) * modifier)
        newdip = round((int(item1["cha"]) + int(item2["cha"])) * modifier)
        newslot = random.choice([item1["slot"], item2["slot"]])
        if len(newslot) == 2:  # two handed weapons add their bonuses twice
            hand = "two handed"
        else:
            if newslot[0] == "right" or newslot[0] == "left":
                hand = newslot[0] + " handed"
            else:
                hand = newslot[0] + " slot"
        if len(newslot) == 2:
            await ctx.send(
                (
                    f"{E(ctx.author.display_name)}, your forging roll was 🎲({roll}).\n"
                    f"The device you tinkered will have {newatt * 2}🗡 and {newdip * 2}🗨 and be {hand}."
                )
            )
        else:
            await ctx.send(
                (
                    f"{E(ctx.author.display_name)}, your forging roll was 🎲({roll}).\n"
                    f"The device you tinkered will have {newatt}🗡 and {newdip}🗨 and be {hand}."
                )
            )
        await ctx.send(
            (
                f"{E(ctx.author.display_name)}, please respond with a name for your creation within 30s.\n"
                "(You will not be able to change it afterwards. 40 characters maximum.)"
            )
        )
        reply = None
        try:
            reply = await ctx.bot.wait_for(
                "message", check=MessagePredicate.same_context(ctx), timeout=30
            )
        except asyncio.TimeoutError:
            reply = "Unnamed Artifact"
        if reply == None:
            name = "{.:'Unnamed Artifact':.}"
        else:
            if hasattr(reply, "content"):
                if len(reply.content) > 40:
                    name = "{.:'Long-winded Artifact':.}"
                else:
                    name = "{.:'" + reply.content + "':.}"
            else:
                name = "{.:'" + reply + "':.}"
        item = {"itemname": name, "item": {"slot": newslot, "att": newatt, "cha": newdip}}
        return item

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def give(self, ctx):
        """[Admin] Commands to add things to players' inventories."""

        pass

    @give.command(name="funds")
    @checks.admin_or_permissions(administrator=True)
    async def _give_funds(self, ctx, amount: int = 1, *, to: discord.Member = None):
        """[Admin] Adds currency to a specified member's balance.

        `[p]give funds 10 @Elder Aramis`
        will create 10 currency and add to Elder Aramis' total.
        """

        if to is None:
            return await ctx.send(
                f"You need to specify a receiving member, {E(ctx.author.display_name)}."
            )
        to_fund = discord.utils.find(lambda m: m.name == to.name, ctx.guild.members)
        if not to_fund:
            return await ctx.send(
                f"I could not find that user, {E(ctx.author.display_name)}. Try using their full Discord name (name#0000)."
            )
        bal = await bank.deposit_credits(to, amount)
        currency = await bank.get_currency_name(ctx.guild)
        if str(currency).startswith("<:"):
            currency = "credits"
        await ctx.send(
            box(
                f"{E(ctx.author.display_name)}, you funded {amount} {currency}. {E(to.display_name)} now has {bal} {currency}."
            )
        )

    @give.command(name="item")
    async def _give_item(
        self,
        ctx,
        item_name: str,
        rarity: str,
        atk: int,
        cha: int,
        position: str,
        user: discord.Member = None,
    ):
        """[Admin] Adds a custom item to a specified member.

        Item names containing spaces must be enclosed in double quotes.
        `[p]give item "fine dagger" rare 1 1 right @locastan`
        will give a right-handed .fine_dagger with 1/1 stats to locastan.
        """

        positions = [
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
            "twohanded",
        ]
        rarities = ["normal", "rare", "epic"]
        if user is None:
            user = ctx.author
        if position not in positions:
            itempos = ", ".join(pos for pos in positions)
            return await ctx.send(f"{E(ctx.author.display_name)}, valid item slots are: {itempos}")
        # if cha > 4 or atk > 4:
        # return await ctx.send(f"{E(ctx.author.display_name)}, don't you think that's a bit overpowered? Not creating item.")
        if len(item_name) >= 40:
            return await ctx.send(f"{E(ctx.author.display_name)}, try again with a shorter name.")
        if rarity not in rarities:
            item_rarity = ", ".join(r for r in rarities)
            return await ctx.send(
                (
                    f"{E(ctx.author.display_name)}, valid item rarities are: {item_rarity}. If your created "
                    'item has a space in the name, enclose the name in double quotes. ex: `"item name"`.'
                )
            )
        if rarity == "rare":
            item_name = item_name.replace(" ", "_")
            item_name = f".{item_name}"
        if rarity == "epic":
            item_name = f"[{item_name}]"
        if position == "twohanded":
            position = ["right", "left"]
        else:
            position = [position]
        new_item = {item_name: {"slot": position, "att": atk, "cha": cha}}
        async with self.config.user(user).all() as userdata:
            userdata["items"]["backpack"].update(new_item)
        await ctx.send(
            box(
                f"An item named {item_name} has been created and placed in {E(user.display_name)}'s backpack.",
                lang="css",
            )
        )

    @give.command(name="loot")
    async def _give_loot(self, ctx, loot_type: str, user: discord.Member = None):
        """[Admin] This rewards a treasure chest to a specified member.
           
        `[p]give loot normal @locastan`
        will give locastan a normal chest.
        Loot types: normal, rare, epic
        """

        if user is None:
            user = ctx.author
        loot_types = ["normal", "rare", "epic"]
        if loot_type not in loot_types:
            return await ctx.send(
                f"Valid loot types: `normal`, `rare`, or `epic`: ex. `{ctx.prefix}give loot normal @locastan` "
            )

        async with self.config.user(user).all() as userdata:
            if loot_type == "rare":
                userdata["treasure"][1] += 1
            elif loot_type == "epic":
                userdata["treasure"][2] += 1
            else:
                userdata["treasure"][0] += 1
            await ctx.send(
                box(
                    (
                        f"{E(user.display_name)} now owns {str(userdata['treasure'][0])} "
                        f"normal, {str(userdata['treasure'][1])} rare and {str(userdata['treasure'][2])} epic chests."
                    ),
                    lang="css",
                )
            )

    @commands.command()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def heroclass(self, ctx, clz: str = None, action: str = None):
        """This allows you to select a class if you are Level 10 or above.

        For information on class use: `[p]heroclass "classname" info`
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        classes = {
            "Tinkerer": {
                "name": "Tinkerer",
                "ability": False,
                "desc": (
                    "Tinkerers can forge two different items into a device "
                    "bound to their very soul.\nUse the forge command."
                ),
            },
            "Berserker": {
                "name": "Berserker",
                "ability": False,
                "desc": (
                    "Berserkers have the option to rage and add big bonuses to attacks, "
                    "but fumbles hurt.\nUse the rage command when attacking in an adventure."
                ),
            },
            "Cleric": {
                "name": "Cleric",
                "ability": False,
                "desc": (
                    "Clerics can bless the entire group when praying.\n"
                    "Use the bless command when fighting in an adventure."
                ),
            },
            "Ranger": {
                "name": "Ranger",
                "ability": False,
                "desc": (
                    "Rangers can gain a special pet, which can find items and give "
                    "reward bonuses.\nUse the pet command to see pet options."
                ),
                "pet": {},
            },
            "Bard": {
                "name": "Bard",
                "ability": False,
                "desc": (
                    "Bards can perform to aid their comrades in diplomacy.\n"
                    "Use the music command when being diplomatic in an adventure."
                ),
            },
        }

        if clz == None:
            ctx.command.reset_cooldown(ctx)
            await ctx.send(
                (
                    f"So you feel like taking on a class, **{E(ctx.author.display_name)}**?\n"
                    "Available classes are: Tinkerer, Berserker, Cleric, Ranger and Bard.\n"
                    f"Use `{ctx.prefix}heroclass name-of-class` to choose one."
                )
            )

        else:
            clz = clz.title()
            if clz in classes and action == "info":
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(f"{classes[clz]['desc']}")
            elif clz not in classes and action is None:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(f"{clz} may be a class somewhere, but not on my watch.")
            bal = await bank.get_balance(ctx.author)
            currency_name = await bank.get_currency_name(ctx.guild)
            if str(currency_name).startswith("<"):
                currency_name = "credits"
            spend = round(bal * 0.2)
            class_msg = await ctx.send(
                box(
                    f"This will cost {spend} {currency_name}. Do you want to continue, {E(ctx.author.display_name)}?",
                    lang="css",
                )
            )
            broke = box(
                f"You don't have enough {currency_name} to train to be a {clz.title()}.",
                lang="css",
            )
            userdata = await self.config.user(ctx.author).all()
            start_adding_reactions(class_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(class_msg, ctx.author)
            await ctx.bot.wait_for("reaction_add", check=pred)

            if not pred.result:
                await class_msg.edit(
                    content=box(
                        f"{E(ctx.author.display_name)} decided to continue being a {userdata['class']['name']}.",
                        lang="css",
                    )
                )
                return await self._clear_react(class_msg)
            if bal < 500:
                await class_msg.edit(content=broke)
                return await self._clear_react(class_msg)
            try:
                await bank.withdraw_credits(ctx.author, spend)
            except ValueError:
                return await class_msg.edit(content=broke)

            userdata = await self.config.user(ctx.author).all()
            if clz in classes and action == None:
                now_class_msg = f"Congratulations, {E(ctx.author.display_name)}. You are now a {classes[clz]['name']}."
                if userdata["lvl"] >= 10:
                    if (
                        userdata["class"]["name"] == "Tinkerer"
                        or userdata["class"]["name"] == "Ranger"
                    ):
                        curclass = userdata["class"]["name"]
                        if curclass == "Tinkerer":
                            await self._clear_react(class_msg)
                            await class_msg.edit(
                                content=box(
                                    (
                                        f"{E(ctx.author.display_name)}, you will lose your forged device "
                                        "if you change your class.\nShall I proceed?"
                                    ),
                                    lang="css",
                                )
                            )
                        else:
                            await self._clear_react(class_msg)
                            await class_msg.edit(
                                content=box(
                                    (
                                        f"{E(ctx.author.display_name)}, you will lose your pet "
                                        "if you change your class.\nShall I proceed?"
                                    ),
                                    lang="css",
                                )
                            )
                        start_adding_reactions(class_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                        pred = ReactionPredicate.yes_or_no(class_msg, ctx.author)
                        await ctx.bot.wait_for("reaction_add", check=pred)

                        if pred.result:  # user reacted with Yes.
                            if curclass == "Tinkerer":
                                tinker_wep = []
                                for gear_slot in userdata["items"]:
                                    item_info = userdata["items"][gear_slot]
                                    for key in item_info:
                                        if gear_slot != "backpack":
                                            if "{.:'" in key:
                                                tinker_wep.append(item_info)

                                tinker_flat = []
                                [tinker_flat.append(x) for x in tinker_wep if x not in tinker_flat]
                                item_list = []
                                async with self.config.user(ctx.author).all() as userinfo:
                                    if len(tinker_flat) == 0:
                                        backpack_lookup = list(
                                            x
                                            for x in userdata["items"]["backpack"]
                                            if "{.:'" in x.lower()
                                        )
                                        if any(
                                            [x for x in backpack_lookup if "{.:'" in x.lower()]
                                        ):
                                            device = [
                                                x for x in backpack_lookup if "{.:'" in x.lower()
                                            ]
                                            del userinfo["items"]["backpack"][device[0]]
                                            userinfo["class"] = classes[clz]
                                            await self._clear_react(class_msg)
                                            return await class_msg.edit(
                                                content=box(
                                                    f"{device[0]} has run off to find a new master.",
                                                    lang="css",
                                                )
                                            )
                                    for item in tinker_flat:
                                        values = item.values()
                                        item_key = list(item.keys())
                                        item_att = list(values)[0]["att"]
                                        item_cha = list(values)[0]["cha"]
                                        container = list(values)[0]["slot"]
                                        item_list.append(item_key[0])
                                        if len(container) == 1:
                                            if container != "backpack":
                                                userinfo["items"][container[0]] = {}
                                                userinfo["att"] -= item_att
                                                userinfo["cha"] -= item_cha
                                                userinfo["class"] = classes[clz]
                                                await self._clear_react(class_msg)
                                                return await class_msg.edit(
                                                    content=box(
                                                        (
                                                            f"{', '.join(item_list)} has run off to "
                                                            f"find a new master.\n{now_class_msg}"
                                                        ),
                                                        lang="css",
                                                    )
                                                )
                                        else:
                                            userinfo["items"]["right"] = {}
                                            userinfo["items"]["left"] = {}
                                            userinfo["att"] -= item_att * 2
                                            userinfo["cha"] -= item_cha * 2
                                            userinfo["class"] = classes[clz]
                            else:
                                async with self.config.user(ctx.author).all() as userinfo:
                                    userinfo["class"]["ability"] = False
                                    userinfo["class"]["pet"] = {}
                                    userinfo["class"] = classes[clz]
                                await self._clear_react(class_msg)
                                return await class_msg.edit(
                                    content=box(
                                        f"{E(ctx.author.display_name)} released their pet into the wild.\n{now_class_msg}",
                                        lang="css",
                                    )
                                )
                            async with self.config.user(ctx.author).all() as userinfo:
                                userinfo["class"] = classes[clz]
                            await self._clear_react(class_msg)
                            return await class_msg.edit(content=box(now_class_msg, lang="css"))

                        else:
                            ctx.command.reset_cooldown(ctx)
                            return
                    else:
                        async with self.config.user(ctx.author).all() as userinfo:
                            userinfo["class"] = classes[clz]
                        await self._clear_react(class_msg)
                        return await class_msg.edit(content=box(now_class_msg, lang="css"))
                else:
                    ctx.command.reset_cooldown(ctx)
                    await ctx.send(
                        f"{E(ctx.author.display_name)}, you need to be at least level 10 to choose a class."
                    )

    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.user)
    async def loot(self, ctx, box_type: str = None):
        """This opens one of your precious treasure chests.

        Use the box rarity type with the command: normal, rare
        or epic.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        userdata = await self.config.user(ctx.author).all()
        if not box_type:
            return await ctx.send(
                box(
                    (
                        f"{E(ctx.author.display_name)} owns {str(userdata['treasure'][0])} "
                        f"normal, {str(userdata['treasure'][1])} rare and {str(userdata['treasure'][2])} epic chests."
                    ),
                    lang="css",
                )
            )
        if box_type == "normal":
            redux = [1, 0, 0]
        elif box_type == "rare":
            redux = [0, 1, 0]
        elif box_type == "epic":
            redux = [0, 0, 1]
        else:
            return await ctx.send(
                f"There is talk of a {box_type} treasure chest but nobody ever saw one."
            )
        treasure = userdata["treasure"][redux.index(1)]
        if treasure == 0:
            await ctx.send(
                f"{E(ctx.author.display_name)}, you have no {box_type} treasure chest to open."
            )
        else:
            item = await self._open_chest(ctx, ctx.author, box_type)  # returns item and msg
            async with self.config.user(ctx.author).all() as userinfo:
                userinfo["treasure"] = [x - y for x, y in zip(userdata["treasure"], redux)]
            if item[0]["equip"] == "sell":
                price = await self._sell(ctx.author, item[0])
                currency_name = await bank.get_currency_name(ctx.guild)
                if str(currency_name).startswith("<"):
                    currency_name = "credits"
                await item[1].edit(
                    content=(
                        box(
                            f"{E(ctx.author.display_name)} sold the {item[0]['itemname']} for {price} {currency_name}.",
                            lang="css",
                        )
                    )
                )
                await self._clear_react(item[1])
            elif item[0]["equip"] == "equip":
                equip = {"itemname": item[0]["itemname"], "item": item[0]["item"]}
                await self._equip_item(ctx, equip, False, item[1])
            else:
                async with self.config.user(ctx.author).all() as userinfo:
                    userinfo["items"]["backpack"].update({item[0]["itemname"]: item[0]["item"]})
                await item[1].edit(
                    content=(
                        box(
                            f"{E(ctx.author.display_name)} put the {item[0]['itemname']} into their backpack.",
                            lang="css",
                        )
                    )
                )
                await self._clear_react(item[1])

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    async def music(self, ctx):
        """[Bard Class Only] 

        This allows a Bard to add substantial diplomacy bonuses for one battle. 
        (1h cooldown)
        """

        userdata = await self.config.user(ctx.author).all()
        if userdata["class"]["name"] != "Bard":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{E(ctx.author.display_name)}, you need to be a Bard to do this."
            )
        else:
            if userdata["class"]["ability"] == True:
                return await ctx.send(f"{E(ctx.author.display_name)}, ability already in use.")
            async with self.config.user(ctx.author).all() as userdata:
                userdata["class"]["ability"] = True
        await ctx.send(f"♪♫♬ {bold(ctx.author.display_name)} is whipping up a performance. ♬♫♪")

    @commands.command(name="negaverse", aliases=["nv"])
    @commands.cooldown(rate=1, per=10, type=commands.BucketType.user)
    async def _negaverse(self, ctx, offering: int = None):
        """This will send you to fight a nega-member!

        `[p]negaverse offering`
        'offering' in this context is the amount of currency you are sacrificing for this fight.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        bal = await bank.get_balance(ctx.author)
        currency_name = await bank.get_currency_name(ctx.guild)

        if not offering:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                (
                    f"{E(ctx.author.display_name)}, you need to specify how many "
                    f"{currency_name} you are willing to offer to the gods for your success."
                )
            )
        if offering <= 500 or bal <= 500:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("The gods refuse your pitiful offering.")
        if offering > bal:
            offering = bal

        nv_msg = await ctx.send(
            (
                f"{E(ctx.author.display_name)}, this will cost you at least "
                f"{offering} {currency_name}.\nYou currently have {bal}. Do you want to proceed?"
            )
        )
        start_adding_reactions(nv_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(nv_msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=pred)

        if not pred.result:
            try:
                ctx.command.reset_cooldown(ctx)
                await nv_msg.edit(
                    content=f"{E(ctx.author.display_name)} decides against visiting the negaverse... for now."
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
            entry_msg = (
                "A swirling void slowly grows and you watch in horror as it rushes to "
                "wash over you, leaving you cold... and your coin pouch significantly lighter. "
                "The portal to the negaverse remains closed."
            )
            return await nv_msg.edit(content=entry_msg)
        else:
            entry_msg = (
                "Shadowy hands reach out to take your offering from you and a swirling "
                "black void slowly grows and engulfs you, transporting you to the negaverse."
            )
            await nv_msg.edit(content=entry_msg)
            await self._clear_react(nv_msg)
            await bank.withdraw_credits(ctx.author, offering)

        negachar = bold(f"Nega-{E(random.choice(ctx.message.guild.members).display_name)}")
        nega_msg = await ctx.send(
            f"{bold(ctx.author.display_name)} enters the negaverse and meets {negachar}."
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
                loss = "all of their"
            loss_msg = (
                f", losing {loss} {currency_name} as {negachar} rifled through their belongings"
            )
            await nega_msg.edit(
                content=(
                    f"{nega_msg.content}\n{bold(ctx.author.display_name)} "
                    f"fumbled and died to {negachar}'s savagery{loss_msg}."
                )
            )
        elif roll == 20:
            await nega_msg.edit(
                content=(
                    f"{nega_msg.content}\n{bold(ctx.author.display_name)} "
                    f"decapitated {negachar}. You gain {int(offering/xp_mod)} xp and take "
                    f"{offering} {currency_name} back from the shadowy corpse."
                )
            )
            await self._add_rewards(
                ctx, ctx.message.author, (int(offering / xp_mod)), offering, False
            )
        elif roll > versus:
            await nega_msg.edit(
                content=(
                    f"{nega_msg.content}\n{bold(ctx.author.display_name)} "
                    f"🎲({roll}) bravely defeated {negachar} 🎲({versus}). "
                    f"You gain {int(offering/xp_mod)} xp."
                )
            )
            await self._add_rewards(ctx, ctx.message.author, (int(offering / xp_mod)), 0, False)
        elif roll == versus:
            await nega_msg.edit(
                content=f"{nega_msg.content}\n{bold(ctx.author.display_name)} 🎲({roll}) almost killed {negachar} 🎲({versus})."
            )
        else:
            loss = round(offering * 0.8)
            try:
                await bank.withdraw_credits(ctx.author, loss)
                loss_msg = ""
            except ValueError:
                await bank.set_balance(ctx.author, 0)
                loss = "all of their"
            loss_msg = f", losing {loss} {currency_name} as {negachar} looted their backpack"
            await nega_msg.edit(
                content=f"{bold(ctx.author.display_name)} 🎲({roll}) was killed by {negachar} 🎲({versus}){loss_msg}."
            )

    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.user)
    async def pet(self, ctx, switch: str = None):
        """[Ranger Class Only] 

        This allows a Ranger to tame or set free a pet or send it foraging.
        (2h cooldown)
        `[p]pet`
        `[p]pet forage`
        `[p]pet free`
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        userdata = await self.config.user(ctx.author).all()
        if userdata["class"]["name"] != "Ranger":
            return await ctx.send(
                box(
                    f"{E(ctx.author.display_name)}, you need to be a Ranger to do this.",
                    lang="css",
                )
            )
        else:
            if switch == None or not userdata["class"]["ability"]:
                async with self.config.user(ctx.author).all() as userdata:
                    pet = await self._pet_switch(ctx, None)
                    if type(pet) is dict:
                        userdata["class"]["ability"] = True
                        userdata["class"]["pet"] = pet
                    else:
                        return
            elif switch == "forage":
                async with self.config.user(ctx.author).all() as userdata:
                    if userdata["class"]["forage"] <= time.time() - 7200:
                        item = await self._pet_switch(ctx, switch)
                        userdata["class"]["forage"] = time.time()
                        if item != None:
                            if item[0]["equip"] == "sell":
                                price = await self._sell(ctx.author, item[0])
                                currency_name = await bank.get_currency_name(ctx.guild)
                                if str(currency_name).startswith("<"):
                                    currency_name = "credits"
                                await item[1].edit(
                                    content=box(
                                        (
                                            f"{E(ctx.author.display_name)} sold the {item[0]['itemname']} "
                                            f"for {price} {currency_name}."
                                        ),
                                        lang="css",
                                    )
                                )
                            elif item[0]["equip"] == "equip":
                                equip = {"itemname": item[0]["itemname"], "item": item[0]["item"]}
                                await self._equip_item(ctx, equip, False, item[1])
                            else:
                                userdata["items"]["backpack"].update(
                                    {item[0]["itemname"]: item[0]["item"]}
                                )
                                await item[1].edit(
                                    content=box(
                                        f"{E(ctx.author.display_name)} put the {item[0]['itemname']} into the backpack.",
                                        lang="css",
                                    )
                                )
                    else:
                        cooldown_time = (userdata["class"]["forage"] + 7200) - time.time()
                        return await ctx.send(
                            "This command is on cooldown. Try again in {:g}s".format(cooldown_time)
                        )
            elif switch == "free":
                async with self.config.user(ctx.author).all() as userdata:
                    await self._pet_switch(ctx, switch)
                    userdata["class"]["ability"] == False

    async def _pet_switch(self, ctx, flag):
        async with self.config.user(ctx.author).all() as userdata:
            if flag == "free":
                if userdata["class"]["ability"] != False:
                    async with self.config.user(ctx.author).all() as userinfo:
                        userinfo["class"]["ability"] = False
                        userinfo["class"]["pet"] = {}
                    return await ctx.send(
                        box(
                            f"{E(ctx.author.display_name)} released their pet into the wild.",
                            lang="css",
                        )
                    )
                else:
                    ctx.command.reset_cooldown(ctx)
                    await ctx.send(
                        box(f"{E(ctx.author.display_name)}, you have no pet to release.")
                    )
            elif flag == "forage":
                return await self._open_chest(ctx, userdata["class"]["pet"]["name"], "pet")
            else:
                if userdata["class"]["ability"] == False:
                    fp = bundled_data_path(self) / "pets.json"
                    with fp.open("r") as f:
                        pets = json.load(f)
                    pet = random.choice(list(pets.keys()))
                    roll = random.randint(1, 20)
                    dipl_value = roll + userdata["cha"] + userdata["skill"]["cha"]

                    pet_msg = box(
                        f"{E(ctx.author.display_name)} is trying to tame a pet.", lang="css"
                    )
                    user_msg = await ctx.send(pet_msg)
                    await asyncio.sleep(2)
                    pet_msg2 = box(
                        f"{E(ctx.author.display_name)} started tracking a wild {pets[pet]['name']} with a roll of 🎲({roll}).",
                        lang="css",
                    )
                    await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}")
                    await asyncio.sleep(2)

                    if roll == 1:
                        bonus = "But they stepped on a twig and scared it away."
                    elif roll == 20:
                        bonus = "They happen to have its favorite food."
                        dipl_value += 10
                    else:
                        bonus = ""
                    if dipl_value > pets[pet]["cha"]:
                        pet_msg3 = box(
                            f"{bonus}\nThey successfully tamed the {pets[pet]['name']}.",
                            lang="css",
                        )
                        await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}")
                        return pets[pet]
                    else:
                        pet_msg3 = box(f"{bonus}\nThe {pets[pet]['name']} escaped.", lang="css")
                        await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}")
                else:
                    ctx.command.reset_cooldown(ctx)
                    await ctx.send(
                        box(
                            f"{E(ctx.author.display_name)}, you already have a pet. Try foraging ({ctx.prefix}pet forage).",
                            lang="css",
                        )
                    )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    async def rage(self, ctx):
        """[Berserker Class Only] 

        This allows a Berserker to add substantial attack bonuses for one battle. 
        (1h cooldown)
        """

        userdata = await self.config.user(ctx.author).all()
        if userdata["class"]["name"] != "Berserker":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{E(ctx.author.display_name)}, you need to be a Berserker to do this."
            )
        else:
            if userdata["class"]["ability"] == True:
                return await ctx.send(f"{E(ctx.author.display_name)}, ability already in use.")
            async with self.config.user(ctx.author).all() as userdata:
                userdata["class"]["ability"] = True
            await ctx.send(
                f"{bold(ctx.author.display_name)} is starting to froth at the mouth...🗯️"
            )

    @commands.command()
    async def skill(self, ctx, spend: str = None):
        """This allows you to spend skillpoints.

        `[p]skill attack/diplomacy`
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        userdata = await self.config.user(ctx.author).all()
        if userdata["skill"]["pool"] == 0:
            return await ctx.send(
                f"{E(ctx.author.display_name)}, you do not have unspent skillpoints."
            )
        if spend == None:
            await ctx.send(
                (
                    f"{E(ctx.author.display_name)}, you currently have {bold(str(userdata['skill']['pool']))} "
                    f"unspent skillpoints.\nIf you want to put them towards a permanent attack or diplomacy bonus, use "
                    f"`{ctx.prefix}skill attack` or `{ctx.prefix}skill diplomacy`"
                )
            )
        else:
            if spend not in ["attack", "diplomacy"]:
                return await ctx.send(f"Don't try to fool me! There is no such thing as {spend}.")
            elif spend == "attack":
                async with self.config.user(ctx.author).all() as userinfo:
                    userinfo["skill"]["pool"] -= 1
                    userinfo["skill"]["att"] += 1
            elif spend == "diplomacy":
                async with self.config.user(ctx.author).all() as userinfo:
                    userinfo["skill"]["pool"] -= 1
                    userinfo["skill"]["cha"] += 1
            await ctx.send(
                f"{E(ctx.author.display_name)}, you permanently raised your {spend} value by one."
            )

    @commands.command()
    async def stats(self, ctx, *, user: discord.Member = None):
        """This draws up a charsheet of you or an optionally specified member.

        `[p]stats @locastan`
        will bring up locastans stats.
        `[p]stats` without user will open your stats.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        if user is None:
            user = ctx.author
        if user.bot:
            return
        bal = await bank.get_balance(user)
        currency = await bank.get_currency_name(ctx.guild)
        userdata = await self.config.user(user).all()
        xp = round(userdata["exp"])
        lvl = userdata["lvl"]
        att = userdata["att"]
        satt = userdata["skill"]["att"]
        cha = userdata["cha"]
        scha = userdata["skill"]["cha"]
        pool = userdata["skill"]["pool"]
        equip = "Equipped Items: \n"
        i = iter(userdata["items"])
        for slot in i:
            if userdata["items"][slot] and slot != "backpack":
                item = list(userdata["items"][slot].keys())[0]
                info = userdata["items"][slot][item]
                if len(info["slot"]) == 1:
                    equip += f" - {item} - (ATT: {info['att']}) | DPL: {info['cha']}) [{info['slot'][0]} slot]\n"
                else:
                    equip += f" - {item} - (ATT: {info['att'] * 2}) | DPL: {info['cha'] * 2}) [two handed]\n"
                    next(i, None)
        next_lvl = int((lvl + 1) ** 4)
        if userdata["class"] != {} and "name" in userdata["class"]:
            class_desc = userdata["class"]["name"] + "\n\n" + userdata["class"]["desc"]
            if userdata["class"]["name"] == "Ranger":
                if not userdata["class"]["ability"]:
                    class_desc += "\n\n- Current pet: None"
                elif userdata["class"]["pet"]:
                    class_desc += f"\n\n- Current pet: {userdata['class']['pet']['name']}"
        else:
            class_desc = "Hero."

        header = box(f"[{E(user.display_name)}'s Character Sheet]", lang="css")
        mid = box(
            (
                f"A level {lvl} {class_desc} \n\n- ATTACK: {att} [+{satt}] - "
                f"DIPLOMACY: {cha} [+{scha}] -\n\n- Currency: {bal} \n- Experience: "
                f"{xp}/{next_lvl} \n- Unspent skillpoints: {pool}"
            ),
            lang="css",
        )
        equipped = box(equip, lang="css")
        await ctx.send(f"{header}{mid}{equipped}")

    @commands.command()
    async def unequip(self, ctx, item: str = "None"):
        """This stashes a specified equipped item into your backpack.

        `[p]unequip name of item`
        You can only have one of each uniquely named item in your backpack.
        """
        if not await self.allow_in_dm(ctx):
            return await ctx.send("This command is only available in a server on this bot.")
        await self._sub_unequip(ctx, item)

    async def _sub_unequip(self, ctx, item: str = "None"):
        user = ctx.author
        userdata = await self.config.user(ctx.author).all()
        equipped = {}

        for slot in userdata["items"]:
            if userdata["items"][slot] and slot != "backpack":
                async with self.config.user(user).all() as userupdate:
                    equipped.update(userupdate["items"][slot])

        if item == "None" or not any([x for x in equipped if item in x.lower()]):
            if item == "{.:'":
                return
            elif item == "None":
                return await ctx.send(
                    f"{E(ctx.author.display_name)}, please use an item name with this command."
                )
            else:
                return await ctx.send(
                    f"{E(ctx.author.display_name)}, you do not have an item matching {item} equipped."
                )
        else:
            lookup = list(x for x in equipped if item in x.lower())
            for olditem in lookup:
                # keep in mind that double handed items grant their bonus twice so they remove twice
                for slot in equipped[olditem].get("slot"):
                    async with self.config.user(user).all() as userinfo:
                        userinfo["items"][slot] = {}
                        userinfo["att"] -= int(equipped[olditem].get("att"))
                        userinfo["cha"] -= int(equipped[olditem].get("cha"))
                        userinfo["items"]["backpack"].update({olditem: equipped[olditem]})
                # TODO: Change data structure of items dict so you can have duplicate items because of key duplicate overwrite in dicts.
                msg = await ctx.send(
                    box(
                        f"{E(ctx.author.display_name)} removed the {olditem} and put it into their backpack.",
                        lang="css",
                    )
                )
            userdata = await self.config.user(ctx.author).all()
            stats_msg = box(
                (
                    f"{E(ctx.author.display_name)}'s new stats: Attack: {userdata['att']} "
                    f"[+{userdata['skill']['att']}], Diplomacy: {userdata['cha']} [+{userdata['skill']['cha']}]."
                ),
                lang="css",
            )
            await msg.edit(content=f"{msg.content}\n{stats_msg}")

    @commands.command(name="adventure", aliases=["a"])
    @commands.guild_only()
    @commands.cooldown(rate=1, per=125, type=commands.BucketType.guild)
    async def _adventure(self, ctx):
        """This will send you on an adventure!

        You play by reacting with the offered emojis.
        """

        userdata = await self.config.user(ctx.author).all()
        adventure_msg = f"You feel adventurous, {E(ctx.author.display_name)}?"

        reward, participants = await self._simple(ctx, adventure_msg)
        reward_copy = reward.copy()
        for userid, rewards in reward_copy.items():
            if not rewards:
                pass
            else:
                user = self.bot.get_user(userid)
                await self._add_rewards(
                    ctx, user, rewards["xp"], rewards["cp"], rewards["special"]
                )
            if participants:
                for user in participants:  # reset activated abilities
                    userdata = await self.config.user(user).all()
                    if "name" in userdata["class"]:
                        if userdata["class"]["name"] != "Ranger" and userdata["class"]["ability"]:
                            async with self.config.user(user).all() as userinfo:
                                userinfo["class"]["ability"] = False
                    self._rewards[user.id] = {}
        self._adventure_timer[ctx.guild.id] = 0
        self._adventure_userlist[ctx.guild.id] = {"fight": [], "talk": [], "pray": [], "run": []}
        self._challenge[ctx.guild.id] = None
        self._challenge_attrib[ctx.guild.id] = None
        self._participants[ctx.guild.id] = None
        self._rewards[ctx.guild.id] = None

    async def _simple(self, ctx, adventure_msg):
        text = ""
        monster_fp = bundled_data_path(self) / "monsters.json"
        with monster_fp.open("r") as f:
            monsters = json.load(f)
        attribs_fp = bundled_data_path(self) / "attribs.json"
        with attribs_fp.open("r") as f:
            attribs = json.load(f)
        self._challenge[ctx.guild.id] = random.choice(list(monsters.keys()))
        self._challenge_attrib[ctx.guild.id] = random.choice(list(attribs.keys()))
        challenge = self._challenge[ctx.guild.id]
        challenge_attrib = self._challenge_attrib[ctx.guild.id]
        adventure_time = time.time()
        await self._data_check(ctx)
        dragons_fp = bundled_data_path(self) / "dragons.json"
        with dragons_fp.open("r") as f:
            dragons = json.load(f)
        if challenge in dragons:
            self._adventure_timer[ctx.guild.id] = 120
            text = box("\n [Dragon Alarm!]", lang="css")
        elif challenge == "Basilisk":
            self._adventure_timer[ctx.guild.id] = 60
        else:
            challenge == self._challenge[ctx.guild.id]
            self._adventure_timer[ctx.guild.id] = 30

        locations_fp = bundled_data_path(self) / "locations.json"
        with locations_fp.open("r") as f:
            locations = json.load(f)
        raisins_fp = bundled_data_path(self) / "raisins.json"
        with raisins_fp.open("r") as f:
            raisins = json.load(f)
        adventure_msg = (
            f"{adventure_msg}{text}\n{random.choice(locations)}\n"
            f"**{E(ctx.author.display_name)}**{random.choice(raisins)}"
        )
        await self._choice(ctx, adventure_msg)
        rewards = self._rewards
        participants = self._participants[ctx.guild.id]
        return (rewards, participants)

    async def _choice(self, ctx, adventure_msg):
        challenge = self._challenge[ctx.guild.id]
        challenge_attrib = self._challenge_attrib[ctx.guild.id]
        threatee_fp = bundled_data_path(self) / "threatee.json"
        with threatee_fp.open("r") as f:
            threatee = json.load(f)

        dragon_text = (
            f"but **a{challenge_attrib} {challenge}** just landed in front of you glaring! \n\n"
            "What will you do and will other heroes be brave enough to help you?\n"
            "Heroes have 2 minutes to participate via reaction:"
        )
        basilisk_text = (
            f"but **a{challenge_attrib} {challenge}** stepped out looking around. \n\n"
            "What will you do and will other heroes help your cause?\n"
            "Heroes have 1 minute to participate via reaction:"
        )
        normal_text = (
            f"but **a{challenge_attrib} {challenge}** is guarding it with{random.choice(threatee)}. \n\n"
            "What will you do and will other heroes help your cause?\n"
            "Heroes have 30s to participate via reaction:"
        )

        await self._adv_countdown(ctx, self._adventure_timer[ctx.guild.id], "Time remaining: ")
        dragons_fp = bundled_data_path(self) / "dragons.json"
        with dragons_fp.open("r") as f:
            dragons = json.load(f)

        if challenge in dragons:
            adventure_msg = f"{adventure_msg}\n{dragon_text}"
            await menu(ctx, [adventure_msg], self._adventure_actions, None, 0, 120)

        elif challenge == "Basilisk":
            adventure_msg = f"{adventure_msg}\n{basilisk_text}"
            await menu(ctx, [adventure_msg], self._adventure_actions, None, 0, 60)
        else:
            adventure_msg = f"{adventure_msg}\n{normal_text}"
            await menu(ctx, [adventure_msg], self._adventure_actions, None, 0, 30)

    async def _fight(
        self,
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
        user: discord.User,
    ):
        if user.bot:
            pass
        else:
            check_other = ["talk", "pray", "run"]
            await self._adventure_check(
                check_other, "fight", ctx, pages, controls, message, page, timeout, emoji, user
            )

    async def _run(
        self,
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
        user: discord.User,
    ):
        if user.bot:
            pass
        else:
            check_other = ["talk", "pray", "fight"]
            await self._adventure_check(
                check_other, "run", ctx, pages, controls, message, page, timeout, emoji, user
            )

    async def _pray(
        self,
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
        user: discord.User,
    ):
        if user.bot:
            pass
        else:
            check_other = ["talk", "fight", "run"]
            await self._adventure_check(
                check_other, "pray", ctx, pages, controls, message, page, timeout, emoji, user
            )

    async def _talk(
        self,
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
        user: discord.User,
    ):
        if user.bot:
            pass
        else:
            check_other = ["fight", "pray", "run"]
            await self._adventure_check(
                check_other, "talk", ctx, pages, controls, message, page, timeout, emoji, user
            )

    async def _adventure_check(
        self, check_lists, call_from, ctx, pages, controls, message, page, timeout, emoji, user
    ):
        for x in check_lists:
            if user in self._adventure_userlist[user.guild.id][x]:
                symbol = self._adventure_controls[x]
                self._adventure_userlist[user.guild.id][x].remove(user)
                try:
                    await message.remove_reaction(symbol, user)
                except discord.errors.Forbidden:
                    pass
        if user not in self._adventure_userlist[user.guild.id][call_from]:
            self._adventure_userlist[user.guild.id][call_from].append(user)
        timeout = self._adventure_timer[user.guild.id]
        try:
            react, user = await ctx.bot.wait_for(
                "reaction_add",
                check=ReactionPredicate.with_emojis(tuple(controls.keys()), message),
                timeout=self._adventure_countdown[ctx.guild.id][2],
            )
        except asyncio.TimeoutError:
            return await self._result(ctx, pages, controls, message, page, timeout)
        return await controls[react.emoji](
            ctx, pages, controls, message, page, timeout, react.emoji, user
        )

    async def _result(
        self,
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
    ):
        calc_msg = await ctx.send("Calculating...")
        attack = 0
        diplomacy = 0
        fumblelist = []
        critlist = []
        failed = False
        people = (
            len(self._adventure_userlist[ctx.guild.id]["fight"])
            + len(self._adventure_userlist[ctx.guild.id]["talk"])
            + len(self._adventure_userlist[ctx.guild.id]["pray"])
        )

        try:
            await message.clear_reactions()
        except discord.errors.Forbidden:  # cannot remove all reactions
            for key in controls.keys():
                await message.remove_reaction(key, ctx.bot.user)

        fight_list = self._adventure_userlist[ctx.guild.id]["fight"]
        talk_list = self._adventure_userlist[ctx.guild.id]["talk"]
        pray_list = self._adventure_userlist[ctx.guild.id]["pray"]
        run_list = self._adventure_userlist[ctx.guild.id]["run"]

        attack, diplomacy, run_msg = await self.handle_run(ctx.guild.id, attack, diplomacy)
        failed = await self.handle_basilisk(ctx, failed)
        fumblelist, attack, diplomacy, pray_msg = await self.handle_pray(
            ctx.guild.id, fumblelist, attack, diplomacy
        )
        fumblelist, critlist, diplomacy, talk_msg = await self.handle_talk(
            ctx.guild.id, fumblelist, critlist, diplomacy
        )
        fumblelist, critlist, attack, fight_msg = await self.handle_fight(
            ctx.guild.id, fumblelist, critlist, attack
        )

        result_msg = run_msg + pray_msg + talk_msg + fight_msg

        challenge = self._challenge[ctx.guild.id]
        challenge_attrib = self._challenge_attrib[ctx.guild.id]
        monster_fp = bundled_data_path(self) / "monsters.json"
        with monster_fp.open("r") as f:
            monsters = json.load(f)
        attribs_fp = bundled_data_path(self) / "attribs.json"
        with attribs_fp.open("r") as f:
            attribs = json.load(f)

        strength = monsters[challenge]["str"] * attribs[challenge_attrib][0]
        dipl = monsters[challenge]["dipl"] * attribs[challenge_attrib][1]
        slain = attack >= strength
        persuaded = diplomacy >= dipl

        fight_name_list = []
        talk_name_list = []
        pray_name_list = []
        for user in fight_list:
            fight_name_list.append(E(user.display_name))
        for user in talk_list:
            talk_name_list.append(E(user.display_name))
        for user in pray_list:
            pray_name_list.append(E(user.display_name))

        fighters = " and ".join(
            [", ".join(fight_name_list[:-1]), fight_name_list[-1]]
            if len(fight_name_list) > 2
            else fight_name_list
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
            CR = strength + dipl
            treasure = [0, 0, 0]
            if (
                CR >= 80 or self._challenge[ctx.guild.id] == "Basilisk"
            ):  # rewards 50:50 rare:normal chest for killing something like the basilisk
                treasure = random.choice([[0, 1, 0], [1, 0, 0]])
            elif CR >= 180:  # rewards 50:50 epic:rare chest for killing hard stuff.
                treasure = random.choice([[0, 0, 1], [0, 1, 0]])
            dragons_fp = bundled_data_path(self) / "dragons.json"
            with dragons_fp.open("r") as f:
                dragons = json.load(f)
            if self._challenge[ctx.guild.id] in dragons:  # always rewards an epic chest.
                treasure[2] += 1
            if len(critlist) != 0:
                treasure[0] += 1
            if treasure == [0, 0, 0]:
                treasure = False
        if self._challenge[ctx.guild.id] == "Basilisk" and failed:
            self._participants[ctx.guild.id] = (
                fight_list + talk_list + pray_list + run_list + fumblelist
            )
            currency_name = await bank.get_currency_name(ctx.guild)
            repair_list = []
            for user in self._participants[ctx.guild.id]:
                bal = await bank.get_balance(user)
                loss = round(bal * 0.05)
                if bal > 500:
                    repair_list.append([user, loss])
                    await bank.withdraw_credits(user, loss)
                else:
                    pass
            loss_list = []
            if len(repair_list) > 0:
                for user, loss in repair_list:
                    loss_list.append(
                        f"{bold(E(user.display_name))} used {str(loss)} {currency_name}"
                    )
                result_msg += (
                    "The Basilisk's gaze turned everyone to stone."
                    f"\n{humanize_list(loss_list)} to repay a passing cleric that unfroze the group."
                )
            else:
                result_msg += "The Basilisk's gaze turned everyone to stone."

            return await ctx.send(msg)
        if self._challenge[ctx.guild.id] == "Basilisk" and not slain and not persuaded:
            self._participants[ctx.guild.id] = (
                fight_list + talk_list + pray_list + run_list + fumblelist
            )
            repair_list = []
            currency_name = await bank.get_currency_name(ctx.guild)
            for user in self._participants[ctx.guild.id]:
                bal = await bank.get_balance(user)
                loss = round(bal * 0.05)
                if bal > 500:
                    repair_list.append([user, loss])
                    await bank.withdraw_credits(user, loss)
                else:
                    pass
            loss_list = []
            if len(repair_list) > 0:
                for user, loss in repair_list:
                    loss_list.append(
                        f"{bold(E(user.display_name))} used {str(loss)} {currency_name}"
                    )
            result_msg += (
                "The mirror shield reflected the Basilisks gaze, but he still managed to kill you."
                f"\n{humanize_list(loss_list)} to repay a passing cleric that resurrected the group."
            )
        amount = (strength + dipl) * people
        if people == 1:
            if slain:
                text = f"{bold(fighters)} has slain the {self._challenge[ctx.guild.id]} in an epic battle!"
                text += await self._reward(
                    ctx, fight_list + pray_list, amount, round((attack / strength) * 0.2), treasure
                )

            if persuaded:
                text = (
                    f"{bold(talkers)} almost died in battle, but confounded "
                    f"the {self._challenge[ctx.guild.id]} in the last second."
                )
                text += await self._reward(
                    ctx, talk_list + pray_list, amount, round((diplomacy / dipl) * 0.2), treasure
                )

            if not slain and not persuaded:
                currency_name = await bank.get_currency_name(ctx.guild)
                repair_list = []
                users = fight_list + talk_list + pray_list + run_list + fumblelist
                for user in users:
                    bal = await bank.get_balance(user)
                    loss = round(bal * 0.05)
                    if bal > 500:
                        repair_list.append([user, loss])
                        await bank.withdraw_credits(user, loss)
                    else:
                        pass
                loss_list = []
                if len(repair_list) > 0:
                    for user, loss in repair_list:
                        loss_list.append(
                            f"{bold(E(user.display_name))} used {str(loss)} {currency_name}"
                        )
                repair_text = (
                    "" if not loss_list else f"{humanize_list(loss_list)} to repair their gear."
                )
                options = [
                    f"No amount of diplomacy or valiant fighting could save you.\n{repair_text}",
                    f"This challenge was too much for one hero.\n{repair_text}",
                    f"You tried your best, but the group couldn't succeed at their attempt.\n{repair_text}",
                ]
                text = random.choice(options)
        else:
            if slain and persuaded:
                if len(pray_list) > 0:
                    god = await self.config.god_name()
                    if await self.config.guild(ctx.guild).god_name():
                        god = await self.config.guild(ctx.guild).god_name()
                    text = (
                        f"{bold(fighters)} slayed the {self._challenge[ctx.guild.id]} "
                        f"in battle, while {bold(talkers)} distracted with flattery and "
                        f"{bold(preachermen)} aided in {god}'s name."
                    )
                else:
                    text = (
                        f"{bold(fighters)} slayed the {self._challenge[ctx.guild.id]} "
                        f"in battle, while {bold(talkers)} distracted with insults."
                    )
                text += await self._reward(
                    ctx,
                    fight_list + talk_list + pray_list,
                    amount,
                    round(((attack / strength) + (diplomacy / dipl)) * 0.2),
                    treasure,
                )

            if not slain and persuaded:
                if len(pray_list) > 0:
                    text = (
                        f"{bold(talkers)} talked the {self._challenge[ctx.guild.id]} "
                        f"down with {bold(preachermen)}'s blessing."
                    )
                else:
                    text = f"{bold(talkers)} talked the {self._challenge[ctx.guild.id]} down."
                text += await self._reward(
                    ctx, talk_list + pray_list, amount, round((diplomacy / dipl) * 0.2), treasure
                )

            if slain and not persuaded:
                if len(pray_list) > 0:
                    text = (
                        f"{bold(fighters)} killed the {self._challenge[ctx.guild.id]} "
                        f"in a most heroic battle with a little help from {bold(preachermen)}."
                    )
                else:
                    text = f"{bold(fighters)} killed the {self._challenge[ctx.guild.id]} in an epic fight."
                text += await self._reward(
                    ctx, fight_list + pray_list, amount, round((attack / strength) * 0.2), treasure
                )

            if not slain and not persuaded:
                currency_name = await bank.get_currency_name(ctx.guild)
                repair_list = []
                users = fight_list + talk_list + pray_list + run_list + fumblelist
                for user in users:
                    bal = await bank.get_balance(user)
                    loss = round(bal * 0.05)
                    if bal > 500:
                        repair_list.append([user, loss])
                        await bank.withdraw_credits(user, loss)
                    else:
                        pass
                loss_list = []
                if len(repair_list) > 0:
                    for user, loss in repair_list:
                        loss_list.append(
                            f"{bold(E(user.display_name))} used {str(loss)} {currency_name}"
                        )
                repair_text = (
                    "" if not loss_list else f"{humanize_list(loss_list)} to repair their gear."
                )
                options = [
                    f"No amount of diplomacy or valiant fighting could save you.\n{repair_text}",
                    f"This challenge was too much for the group.\n{repair_text}",
                    f"You tried your best, but couldn't succeed.\n{repair_text}",
                ]
                text = random.choice(options)

        await ctx.send(result_msg + "\n" + text)
        await self._data_check(ctx)
        self._participants[ctx.guild.id] = (
            fight_list + talk_list + pray_list + run_list + fumblelist
        )

    async def handle_run(self, guild_id, attack, diplomacy):
        runners = []
        msg = ""
        if len(list(self._adventure_userlist[guild_id]["run"])) != 0:
            for user in self._adventure_userlist[guild_id]["run"]:
                attack -= 1
                diplomacy -= 1
                runners.append(E(user.display_name))
            msg += f"{bold(humanize_list(runners))} just ran away.\n"
        return (attack, diplomacy, msg)

    async def handle_fight(self, guild_id, fumblelist, critlist, attack):
        if len(self._adventure_userlist[guild_id]["fight"]) >= 1:
            report = "Attack Party: "
            msg = ""
        else:
            return (fumblelist, critlist, attack, "")

        for user in self._adventure_userlist[guild_id]["fight"]:
            roll = random.randint(1, 20)
            userdata = await self.config.user(user).all()
            att_value = userdata["att"] + userdata["skill"]["att"]
            if roll == 1:
                msg += f"{bold(E(user.display_name))} fumbled the attack.\n"
                fumblelist.append(user)
                if userdata["class"]["name"] == "Berserker" and userdata["class"]["ability"]:
                    bonus = random.randint(5, 15)
                    attack += roll - bonus + att_value
                    report += f"| {bold(E(user.display_name))}: 🎲({roll}) +💥{bonus} +🗡{str(att_value)} | "
            elif roll == 20 or (
                userdata["class"]["name"] == "Berserker" and userdata["class"]["ability"]
            ):
                ability = ""
                if roll == 20:
                    msg += f"{bold(E(user.display_name))} landed a critical hit.\n"
                    critlist.append(user)
                if userdata["class"]["ability"]:
                    ability = "🗯️"
                bonus = random.randint(5, 15)
                attack += roll + bonus + att_value
                bonus = ability + str(bonus)
                report += (
                    f"| {bold(E(user.display_name))}: 🎲({roll}) +💥{bonus} +🗡{str(att_value)} | "
                )
            else:
                attack += roll + att_value
                report += f"| {bold(E(user.display_name))}: 🎲({roll}) +🗡{str(att_value)} | "
        msg = msg + report + "\n"
        for user in fumblelist:
            if user in self._adventure_userlist[guild_id]["fight"]:
                self._adventure_userlist[guild_id]["fight"].remove(user)
        return (fumblelist, critlist, attack, msg)

    async def handle_pray(self, guild_id, fumblelist, attack, diplomacy):
        all_lists = self._adventure_userlist[guild_id]
        talk_list = all_lists["talk"]
        pray_list = all_lists["pray"]
        fight_list = all_lists["fight"]
        god = await self.config.god_name()
        if await self.config.guild(self.bot.get_guild(guild_id)).god_name():
            god = await self.config.guild(ctx.guild).god_name()
        msg = ""
        for user in pray_list:
            userdata = await self.config.user(user).all()
            if userdata["class"]["name"] == "Cleric" and userdata["class"]["ability"]:
                roll = random.randint(1, 20)
                if len(fight_list + talk_list) == 0:
                    msg += f"{bold(E(user.display_name))} blessed like a madman but nobody was there to receive it.\n"

                if roll == 1:
                    attack -= 5 * len(fight_list)
                    diplomacy -= 5 * len(talk_list)
                    fumblelist.append(user)
                    msg += (
                        f"{bold(E(user.display_name))}'s sermon offended the mighty {god}. "
                        f"(-{5 * len(fight_list)}🗡/-{5 * len(talk_list)}🗨)\n"
                    )

                elif roll in range(2, 10):
                    attack += len(fight_list)
                    diplomacy += len(talk_list)
                    msg += (
                        f"{bold(E(user.display_name))} blessed you all in {god}'s name. "
                        f"(+{len(fight_list)}🗡/+{len(talk_list)}🗨)\n"
                    )

                elif roll in range(11, 19):
                    attack += 5 * len(fight_list)
                    diplomacy += 5 * len(talk_list)
                    msg += (
                        f"{bold(E(user.display_name))} blessed you all in {god}'s name. "
                        f"(+{5 * len(fight_list)}🗡/+{5 * len(talk_list)}🗨)\n"
                    )

                else:
                    attack += 10 * len(fight_list)
                    diplomacy += 10 * len(talk_list)
                    msg += (
                        f"{bold(E(user.display_name))} turned into an avatar of mighty {god}. "
                        f"(+{10 * len(fight_list)}🗡/+{10 * len(talk_list)}🗨)\n"
                    )
            else:
                roll = random.randint(1, 4)
                if len(fight_list + talk_list) == 0:
                    msg += f"{bold(E(user.display_name))} prayed like a madman but nobody else helped them.\n"

                if roll == 4:
                    attack += 10 * len(fight_list)
                    diplomacy += 10 * len(talk_list)
                    msg += (
                        f"{bold(E(user.display_name))}'s prayer called upon the mighty {god} to help you. "
                        f"(+{10 * len(fight_list)}🗡/+{10 * len(talk_list)}🗨)\n"
                    )
                else:
                    fumblelist.append(user)
                    msg += f"{bold(E(user.display_name))}'s prayers went unanswered.\n"
        for user in fumblelist:
            if user in pray_list:
                pray_list.remove(user)
        return (fumblelist, attack, diplomacy, msg)

    async def handle_talk(self, guild_id, fumblelist, critlist, diplomacy):
        if len(self._adventure_userlist[guild_id]["talk"]) >= 1:
            report = "Talking Party: "
            msg = ""
        else:
            return (fumblelist, critlist, diplomacy, "")
        for user in self._adventure_userlist[guild_id]["talk"]:
            userdata = await self.config.user(user).all()
            roll = random.randint(1, 20)
            dipl_value = userdata["cha"] + userdata["skill"]["cha"]
            if roll == 1:
                msg += f"{bold(E(user.display_name))} accidentally offended the enemy.\n"
                fumblelist.append(user)
                if userdata["class"]["name"] == "Bard" and userdata["class"]["ability"]:
                    bonus = random.randint(5, 15)
                    diplomacy += roll - bonus + dipl_value
                    report += f"| {bold(E(user.display_name))} 🎲({roll}) +💥{bonus} +🗨{str(dipl_value)} | "
            elif (
                roll == 20 or userdata["class"]["name"] == "Bard" and userdata["class"]["ability"]
            ):
                ability = ""
                if roll == 20:
                    msg += f"{bold(E(user.display_name))} made a compelling argument.\n"
                    critlist.append(user)
                if userdata["class"]["ability"]:
                    ability = "🎵"
                bonus = random.randint(5, 15)
                diplomacy += roll + bonus + dipl_value
                bonus = ability + str(bonus)
                report += (
                    f"| {bold(E(user.display_name))} 🎲({roll}) +💥{bonus} +🗨{str(dipl_value)} | "
                )
            else:
                diplomacy += roll + dipl_value
                report += f"| {bold(E(user.display_name))} 🎲({roll}) +🗨{str(dipl_value)} | "
        msg = msg + report + "\n"
        for user in fumblelist:
            if user in self._adventure_userlist[guild_id]["talk"]:
                self._adventure_userlist[guild_id]["talk"].remove(user)
        return (fumblelist, critlist, diplomacy, msg)

    async def handle_basilisk(self, ctx, failed):
        fight_list = self._adventure_userlist[ctx.guild.id]["fight"]
        talk_list = self._adventure_userlist[ctx.guild.id]["talk"]
        pray_list = self._adventure_userlist[ctx.guild.id]["pray"]
        if self._challenge[ctx.guild.id] == "Basilisk":
            failed = True
            for user in (
                fight_list + talk_list + pray_list
            ):  # check if any fighter has an equipped mirror shield to give them a chance.
                userinfo = await self.config.user(user).all()
                try:
                    if ".mirror_shield" in userinfo["items"]["left"]:
                        failed = False
                        break
                except KeyError:
                    continue
        else:
            failed = False
        return failed

    async def _add_rewards(self, ctx, user, exp, cp, special):
        async with self.config.user(user).all() as userdata:
            userdata["exp"] += exp
        member = ctx.guild.get_member(user.id)
        await bank.deposit_credits(member, cp)
        await self._level_up(ctx, user)
        if special != False:
            async with self.config.user(user).all() as userdata:
                userdata["treasure"] = [sum(x) for x in zip(userdata["treasure"], special)]

    async def _adv_countdown(
        self, ctx, seconds, title, loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> asyncio.Task:
        await self._data_check(ctx)

        async def adv_countdown():
            secondint = int(seconds)
            adv_end = self._get_epoch(secondint)
            message_adv = await ctx.send(f"⏳ [{title}] {self._remaining(adv_end)[0]}s")
            while True:
                timer, done, sremain = self._remaining(adv_end)
                self._adventure_countdown[ctx.guild.id] = timer, done, sremain
                if done:
                    await message_adv.delete()
                    break
                elif int(sremain) % 5 == 0 and not done:
                    await message_adv.edit(content=(f"⏳ [{title}] {self._remaining(adv_end)[0]}s"))
                await asyncio.sleep(1)

        if loop is None:
            loop = asyncio.get_event_loop()

        return loop.create_task(adv_countdown())

    def _build_bkpk_display(self, backpack):
        bkpk = self._sort_backpack(backpack)
        form_string = "Items in Backpack:"
        for slot_group in bkpk:
            slot_name = slot_group[0][1]["slot"]
            slot_name = slot_name[0] if len(slot_name) < 2 else "two handed"
            form_string += f"\n\n {slot_name.title()} slot"
            rjust = max([len(i[0]) for i in slot_group])
            for item in slot_group:
                form_string += (
                    f'\n  - {item[0]:<{rjust}} - (ATT: {item[1]["att"]} | DPL: {item[1]["cha"]})'
                )

        return form_string + "\n"

    async def _cart_countdown(
        self, ctx, seconds, title, loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> asyncio.Task:
        await self._data_check(ctx)

        async def cart_countdown():
            secondint = int(seconds)
            cart_end = self._get_epoch(secondint)
            message_cart = await ctx.send(f"⏳ [{title}] {self._remaining(cart_end)[0]}s")
            while True:
                timer, done, sremain = self._remaining(cart_end)
                self._trader_countdown[ctx.guild.id] = timer, done, sremain
                if done:
                    await message_cart.delete()
                    break
                if int(sremain) % 5 == 0:
                    await message_cart.edit(
                        content=(f"⏳ [{title}] {self._remaining(cart_end)[0]}s")
                    )
                await asyncio.sleep(1)

        if loop is None:
            loop = self.bot.loop

        return loop.create_task(cart_countdown())

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
            self._adventure_timer[ctx.guild.id]
        except KeyError:
            self._adventure_timer[ctx.guild.id] = 0
        try:
            self._adventure_userlist[ctx.guild.id]
        except KeyError:
            self._adventure_userlist[ctx.guild.id] = {
                "fight": [],
                "talk": [],
                "pray": [],
                "run": [],
            }
        try:
            self._challenge[ctx.guild.id]
        except KeyError:
            self._challenge[ctx.guild.id] = None
            self._challenge_attrib[ctx.guild.id] = None
        try:
            self._rewards[ctx.author.id]
        except KeyError:
            self._rewards[ctx.author.id] = {}
        try:
            self._participants[ctx.guild.id]
        except KeyError:
            self._participants[ctx.guild.id] = None
        try:
            self._trader_countdown[ctx.guild.id]
        except KeyError:
            self._trader_countdown[ctx.guild.id] = 0

    async def _equip_item(self, ctx, item, from_backpack, msg=None):
        if not msg:
            msg = await ctx.send("\u200b")
        async with self.config.user(ctx.author).all() as userdata:
            for slot in item["item"]["slot"]:
                if userdata["items"][slot] == {}:
                    userdata["items"][slot][item["itemname"]] = item["item"]
                    userdata["att"] += item["item"]["att"]
                    userdata["cha"] += item["item"]["cha"]
                    equip_msg = box(
                        f"{E(ctx.author.display_name)} equipped {item['itemname']} ({slot} slot).",
                        lang="css",
                    )
                    await msg.edit(content=equip_msg)
                else:
                    olditem = userdata["items"][slot]
                    for oslot in olditem[list(olditem.keys())[0]]["slot"]:
                        userdata["items"][oslot] = {}
                        userdata["att"] -= olditem[list(olditem.keys())[0]][
                            "att"
                        ]  # keep in mind that double handed items grant their bonus twice so they remove twice
                        userdata["cha"] -= olditem[list(olditem.keys())[0]]["cha"]
                    userdata["items"]["backpack"].update(olditem)
                    userdata["items"][slot][item["itemname"]] = item["item"]
                    userdata["att"] += item["item"]["att"]
                    userdata["cha"] += item["item"]["cha"]
                    equip_msg = box(
                        (
                            f"{E(ctx.author.display_name)} equipped {item['itemname']} "
                            f"({slot} slot) and put {list(olditem.keys())[0]} into their backpack."
                        ),
                        lang="css",
                    )
                    await msg.edit(content=equip_msg)
        if from_backpack:
            async with self.config.user(ctx.author).all() as userdata:
                del userdata["items"]["backpack"][item["itemname"]]
        userdata = await self.config.user(ctx.author).all()
        stats_msg = box(
            (
                f"{E(ctx.author.display_name)}'s new stats: Attack: {userdata['att']} "
                f"[+{userdata['skill']['att']}], Diplomacy: {userdata['cha']} [+{userdata['skill']['cha']}]."
            ),
            lang="css",
        )
        await msg.edit(content=f"{msg.content}\n{stats_msg}")

    @staticmethod
    def _get_epoch(seconds: int):
        epoch = time.time()
        epoch += seconds
        return epoch

    @staticmethod
    def _get_rarity(item):
        if item[0][0] == "[":  # epic
            return 0
        elif item[0][0] == ".":  # rare
            return 1
        else:
            return 2  # common / normal

    async def _level_up(self, ctx, user):
        userdata = await self.config.user(user).all()
        exp = userdata["exp"]
        lvl_start = userdata["lvl"]
        lvl_end = int(exp ** (1 / 4))

        if (
            lvl_start < lvl_end
        ):  # recalculate free skillpoint pool based on new level and already spent points.
            await ctx.send(f"{user.mention} is now level {lvl_end}!")
            async with self.config.user(user).all() as userdata:
                userdata["lvl"] = lvl_end
                userdata["skill"]["pool"] = int(lvl_end / 5) - (
                    userdata["skill"]["att"] + userdata["skill"]["cha"]
                )
            userdata = await self.config.user(user).all()
            if userdata["skill"]["pool"] > 0:
                await ctx.send(f"{E(user.display_name)}, you have skillpoints available.")

    async def on_message(self, message):
        if isinstance(message.channel, discord.abc.PrivateChannel):
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
                await self._trader(ctx)

    async def _open_chest(self, ctx, user, chest_type):
        if hasattr(user, "display_name"):
            chest_msg = (
                f"{E(user.display_name)} is opening a treasure chest. What riches lay inside?"
            )
        else:
            chest_msg = f"{E(ctx.author.display_name)}'s {user[:1] + user[1:]} is foraging for treasure. What will it find?"
        open_msg = await ctx.send(box(chest_msg, lang="css"))
        await asyncio.sleep(2)
        roll = random.randint(1, 100)

        common_fp = bundled_data_path(self) / "tr_common.json"
        with common_fp.open("r") as f:
            common = json.load(f)
        rare_fp = bundled_data_path(self) / "tr_rare.json"
        with rare_fp.open("r") as f:
            rare = json.load(f)
        epic_fp = bundled_data_path(self) / "tr_epic.json"
        with epic_fp.open("r") as f:
            unique = json.load(f)

        if chest_type == "pet":
            if roll <= 5:
                chance = unique
            elif roll > 5 and roll <= 25:
                chance = rare
            elif roll > 25 and roll <= 75:
                chance = common
            else:
                await open_msg.edit(
                    content=box(
                        f"{chest_msg}\nThe {user[:1] + user[1:]} found nothing of value.",
                        lang="css",
                    )
                )
                return None
        if chest_type == "normal":
            if roll <= 5:
                chance = unique
            elif roll > 5 and roll <= 25:
                chance = rare
            else:
                chance = common
        if chest_type == "rare":
            if roll <= 15:
                chance = unique
            elif roll > 15 and roll <= 45:
                chance = rare
            else:
                chance = common
        if chest_type == "epic":
            if roll <= 35:
                chance = unique
            else:
                chance = rare
        else:
            chance = common
        itemname = random.choice(list(chance.keys()))
        item = chance[itemname]
        if len(item["slot"]) == 2:  # two handed weapons add their bonuses twice
            hand = "two handed"
            att = item["att"] * 2
            cha = item["cha"] * 2
        else:
            if item["slot"][0] == "right" or item["slot"][0] == "left":
                hand = item["slot"][0] + " handed"
            else:
                hand = item["slot"][0] + " slot"
            att = item["att"]
            cha = item["cha"]
        if hasattr(user, "display_name"):
            chest_msg2 = f"{E(user.display_name)} found a {itemname}. (Attack: {str(att)}, Charisma: {str(cha)} [{hand}])"
            await open_msg.edit(
                content=box(
                    f"{chest_msg}\n{chest_msg2}\nDo you want to equip this item, put in your backpack, or sell this item?",
                    lang="css",
                )
            )
        else:
            chest_msg2 = f"The {user} found a {itemname}. (Attack: {str(att)}, Charisma: {str(cha)} [{hand}])"
            await open_msg.edit(
                content=box(
                    f"{chest_msg}\n{chest_msg2}\nDo you want to equip this item, put in your backpack, or sell this item?",
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
        react, user = await ctx.bot.wait_for("reaction_add", check=pred)
        await self._clear_react(open_msg)
        return (
            {"itemname": itemname, "item": item, "equip": self._treasure_controls[react.emoji]},
            open_msg,
        )

    @staticmethod
    def _remaining(epoch):
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

    async def _reward(self, ctx, userlist, amount, modif, special):
        if modif == 0:
            modif = 0.5
        xp = max(1, round(amount))
        cp = max(1, round(amount * modif))
        rewards_list = []
        phrase = ""
        for user in userlist:
            self._rewards[user.id] = {}
            userdata = await self.config.user(user).all()
            roll = random.randint(1, 5)
            if (
                roll == 5
                and userdata["class"]["name"] == "Ranger"
                and userdata["class"]["ability"]
            ):
                self._rewards[user.id]["xp"] = int(xp * userdata["class"]["pet"]["bonus"])
                self._rewards[user.id]["cp"] = int(cp * userdata["class"]["pet"]["bonus"])
                percent = round((userdata["class"]["pet"]["bonus"] - 1.0) * 100)
                phrase = (
                    f"\n{bold(E(user.display_name))} received a {bold(str(percent))}% "
                    f"reward bonus from their {userdata['class']['pet']['name']}."
                )

            else:
                self._rewards[user.id]["xp"] = xp
                self._rewards[user.id]["cp"] = cp
            if special != False:
                self._rewards[user.id]["special"] = special
            else:
                self._rewards[user.id]["special"] = False
            rewards_list.append(E(user.display_name))

        currency_name = await bank.get_currency_name(ctx.guild)
        to_reward = " and ".join(
            [", ".join(rewards_list[:-1]), rewards_list[-1]]
            if len(rewards_list) > 2
            else rewards_list
        )
        if len(userlist) == 1:
            word = "has"
        else:
            word = "have"
        if special != False and sum(special) == 1:
            types = [" normal", " rare", "n epic"]
            chest_type = types[special.index(1)]
            phrase += (
                f"\n{bold(to_reward)} {word} been awarded {xp} xp and found {cp} {currency_name}. "
                f"You also secured **a{chest_type} treasure chest**!"
            )
        elif special != False and sum(special) > 1:
            phrase += (
                f"\n{bold(to_reward)} {word} been awarded {xp} xp and found {cp} {currency_name}. "
                f"You also secured **several treasure chests**!"
            )
        else:
            phrase += (
                f"\n{bold(to_reward)} {word} been awarded {xp} xp and found {cp} {currency_name}."
            )
        return phrase

    @staticmethod
    async def _sell(user, item):
        if isinstance(item, tuple):
            thing = item[0]
        else:
            thing = item
        if "[" in thing["itemname"]:
            base = (500, 1000)
        elif "." in thing["itemname"]:
            base = (100, 500)
        else:
            base = (10, 200)
        price = random.randint(base[0], base[1]) * max(
            item["item"]["att"] + item["item"]["cha"], 1
        )
        await bank.deposit_credits(user, price)
        return price

    def _sort_backpack(self, backpack: dict):
        tmp = {}
        for item in backpack:
            slots = backpack[item]["slot"]
            if len(slots) == 1:
                slot_name = slots[0]
            else:
                slot_name = "two handed"

            if slot_name not in tmp:
                tmp[slot_name] = []
            tmp[slot_name].append((item, backpack[item]))

        final = []
        for idx, slot_name in enumerate(tmp.keys()):
            final.append(sorted(tmp[slot_name], key=self._get_rarity))

        final.sort(
            key=lambda i: self._order.index(i[0][1]["slot"][0])
            if len(i[0][1]["slot"]) == 1
            else self._order.index("two handed")
        )
        return final

    async def _trader(self, ctx):
        async def _handle_buy(itemindex, user, stock, msg):
            item = stock[itemindex]
            spender = user
            react = None
            currency_name = await bank.get_currency_name(ctx.guild)
            if await bank.can_spend(spender, int(item["price"])):
                await bank.withdraw_credits(spender, int(item["price"]))
                async with self.config.user(user).all() as userdata:
                    if "chest" in item["itemname"]:
                        if item["itemname"] == ".rare_chest":
                            userdata["treasure"][1] += 1
                        elif item["itemname"] == "[epic chest]":
                            userdata["treasure"][2] += 1
                        else:
                            userdata["treasure"][0] += 1
                    else:
                        userdata["items"]["backpack"].update({item["itemname"]: item["item"]})
                await ctx.send(
                    (
                        f"{E(user.display_name)} bought the {item['itemname']} for "
                        f"{str(item['price'])} {currency_name} and put it into their backpack."
                    )
                )
            else:
                currency_name = await bank.get_currency_name(ctx.guild)
                await ctx.send(f"{E(user.display_name)} does not have enough {currency_name}.")
            try:
                react, user = await ctx.bot.wait_for(
                    "reaction_add",
                    check=ReactionPredicate.with_emojis(tuple(controls.keys()), msg),
                    timeout=self._trader_countdown[ctx.guild.id][2],
                )
            except asyncio.TimeoutError:  # the timeout only applies if no reactions are made!
                try:
                    await msg.delete()
                except discord.errors.Forbidden:  # cannot remove all reactions
                    pass
            if react != None and user:
                await _handle_buy(controls[react.emoji], user, stock, msg)

        em_list = ReactionPredicate.NUMBER_EMOJIS[:5]
        react = False
        controls = {em_list[1]: 0, em_list[2]: 1, em_list[3]: 2, em_list[4]: 3}
        cart = await self.config.cart_name()
        if await self.config.guild(ctx.guild).cart_name():
            cart = await self.config.guild(cts.guild).cart_name()
        text = box(f"[{cart}'s brother is bringing the cart around!]", lang="css")
        if self._last_trade[ctx.guild.id] == 0:
            self._last_trade[ctx.guild.id] = time.time()
        elif (
            self._last_trade[ctx.guild.id] >= time.time() - 10800
        ):  # trader can return after 3 hours have passed since last visit.
            return  # silent return.
        self._last_trade[ctx.guild.id] = time.time()
        stock = await self._trader_get_items()
        currency_name = await bank.get_currency_name(ctx.guild)
        if str(currency_name).startswith("<"):
            currency_name = "credits"
        for index, item in enumerate(stock):
            item = stock[index]
            if "chest" not in item["itemname"]:
                if len(item["item"]["slot"]) == 2:  # two handed weapons add their bonuses twice
                    hand = "two handed"
                    att = item["item"]["att"] * 2
                    cha = item["item"]["cha"] * 2
                else:
                    if item["item"]["slot"][0] == "right" or item["item"]["slot"][0] == "left":
                        hand = item["item"]["slot"][0] + " handed"
                    else:
                        hand = item["item"]["slot"][0] + " slot"
                    att = item["item"]["att"]
                    cha = item["item"]["cha"]
                text += box(
                    (
                        f"\n[{str(index + 1)}] {item['itemname']} (Attack: {str(att)}, "
                        f"Charisma: {str(cha)} [{hand}]) for {item['price']} {currency_name}."
                    ),
                    lang="css",
                )
            else:
                text += box(
                    f"\n[{str(index + 1)}] {item['itemname']} for {item['price']} {currency_name}.",
                    lang="css",
                )
        text += "Do you want to buy any of these fine items? Tell me which one below:"
        msg = await ctx.send(text)
        start_adding_reactions(msg, controls.keys(), ctx.bot.loop)
        try:
            timeout = self._last_trade[ctx.guild.id] + 180 - time.time()
            if timeout <= 0:
                timeout = 0
            await self._cart_countdown(ctx, timeout, "The cart will leave in: ", ctx.bot.loop)
            react, user = await ctx.bot.wait_for(
                "reaction_add",
                check=ReactionPredicate.with_emojis(tuple(controls.keys()), msg),
                timeout=timeout,
            )
        except asyncio.TimeoutError:  # the timeout only applies if no reactions are made!
            try:
                await msg.delete()
            except discord.errors.Forbidden:  # cannot remove all reactions
                pass
        if react and user:
            await _handle_buy(controls[react.emoji], user, stock, msg)

    async def _trader_get_items(self):
        items = {}
        output = {}

        common_fp = bundled_data_path(self) / "tr_common.json"
        with common_fp.open("r") as f:
            common = json.load(f)
        rare_fp = bundled_data_path(self) / "tr_rare.json"
        with rare_fp.open("r") as f:
            rare = json.load(f)
        epic_fp = bundled_data_path(self) / "tr_epic.json"
        with epic_fp.open("r") as f:
            unique = json.load(f)

        chest_type = random.randint(1, 100)
        while len(items) < 4:
            chance = None
            roll = random.randint(1, 100)
            if chest_type <= 60:
                if roll <= 5:
                    chance = unique
                elif roll > 5 and roll <= 25:
                    chance = rare
                elif roll >= 90:
                    chest = [1, 0, 0]
                    types = ["normal chest", ".rare_chest", "[epic chest]"]
                    if "normal chest" not in items:
                        items.update(
                            {
                                "normal chest": {
                                    "itemname": "normal chest",
                                    "item": chest,
                                    "price": 2000,
                                }
                            }
                        )
                else:
                    chance = common
            elif chest_type <= 75:
                if roll <= 15:
                    chance = unique
                elif roll > 15 and roll <= 45:
                    chance = rare
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
                    chance = common
            elif chest_type <= 90:
                if roll <= 25:
                    chance = unique
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
                    chance = rare

            if chance != None:
                itemname = random.choice(list(chance.keys()))
                item = chance[itemname]
                if len(item["slot"]) == 2:  # two handed weapons add their bonuses twice
                    hand = "two handed"
                    att = item["att"] * 2
                    cha = item["cha"] * 2
                else:
                    att = item["att"]
                    cha = item["cha"]
                if "[" in itemname:
                    price = random.randint(1000, 2000) * max(att + cha, 1)
                elif "." in itemname:
                    price = random.randint(200, 1000) * max(att + cha, 1)
                else:
                    price = random.randint(10, 200) * max(att + cha, 1)
                if itemname not in items:
                    items.update({itemname: {"itemname": itemname, "item": item, "price": price}})

        for index, item in enumerate(items):
            output.update({index: items[item]})
        return output
