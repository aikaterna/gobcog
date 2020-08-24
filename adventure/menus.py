from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import discord
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape, humanize_number
from redbot.vendored.discord.ext import menus

from . import bank

_ = Translator("Adventure", __file__)
log = logging.getLogger("red.cogs.adventure.menus")


class LeaderboardSource(menus.ListPageSource):
    def __init__(self, entries: List[Tuple[int, Dict]]):
        super().__init__(entries, per_page=10)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        rebirth_len = len(humanize_number(entries[0][1]["rebirths"]))
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        rebirth_len = (len("Rebirths") if len("Rebirths") > rebirth_len else rebirth_len) + 2
        set_piece_len = len("Set Pieces") + 2
        level_len = len("Level") + 2
        header = (
            f"{'#':{pos_len}}{'Rebirths':{rebirth_len}}"
            f"{'Level':{level_len}}{'Set Pieces':{set_piece_len}}{'Adventurer':2}"
        )
        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for position, acc in enumerate(entries, start=start_position):
            user_id = acc[0]
            account_data = acc[1]
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = f"{user_id}"
                else:
                    username = user.name
            username = escape(username, formatting=True)

            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            rebirths = humanize_number(account_data["rebirths"])
            set_items = humanize_number(account_data["set_items"])
            level = humanize_number(account_data["lvl"])
            data = (
                f"{f'{pos_str}.':{pos_len}}"
                f"{rebirths:{rebirth_len}}"
                f"{level:{level_len}}"
                f"{set_items:{set_piece_len}}"
                f"{username}"
            )
            players.append(data)

        embed = discord.Embed(
            title="Adventure Leaderboard",
            color=await menu.ctx.embed_color(),
            description="```md\n{}``` ```md\n{}```".format(header, "\n".join(players),),
        )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class WeeklyScoreboardSource(menus.ListPageSource):
    def __init__(self, entries: List[Tuple[int, Dict]], stat: Optional[str] = None):
        super().__init__(entries, per_page=10)
        self._stat = stat or "wins"

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        stats_len = len(humanize_number(entries[0][1][self._stat])) + 3
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        stats_plural = self._stat if self._stat.endswith("s") else f"{self._stat}s"
        stats_len = (len(stats_plural) if len(stats_plural) > stats_len else stats_len) + 2
        rebirth_len = len("Rebirths") + 2
        header = f"{'#':{pos_len}}{stats_plural.title().ljust(stats_len)}{'Rebirths':{rebirth_len}}{'Adventurer':2}"
        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for (position, (user_id, account_data)) in enumerate(entries, start=start_position):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name
            username = escape(str(username), formatting=True)
            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            rebirths = humanize_number(account_data["rebirths"])
            stats_value = humanize_number(account_data[self._stat.lower()])

            data = f"{f'{pos_str}.':{pos_len}}" f"{stats_value:{stats_len}}" f"{rebirths:{rebirth_len}}" f"{username}"
            players.append(data)

        embed = discord.Embed(
            title=f"Adventure Weekly Scoreboard",
            color=await menu.ctx.embed_color(),
            description="```md\n{}``` ```md\n{}```".format(header, "\n".join(players),),
        )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class ScoreboardSource(WeeklyScoreboardSource):
    def __init__(self, entries: List[Tuple[int, Dict]], stat: Optional[str] = None):
        super().__init__(entries)
        self._stat = stat or "wins"
        self._legend = None

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        if self._legend is None:
            self._legend = (
                "React with the following to go to the specified filter:\n"
                "\N{FACE WITH PARTY HORN AND PARTY HAT}: Win scoreboard\n"
                "\N{FIRE}: Loss scoreboard\n"
                "\N{DAGGER KNIFE}: Physical attack scoreboard\n"
                "\N{SPARKLES}: Magic attack scoreboard\n"
                "\N{LEFT SPEECH BUBBLE}: Diplomacy scoreboard\n"
                "\N{PERSON WITH FOLDED HANDS}: Pray scoreboard\n"
                "\N{RUNNER}: Run scoreboard\n"
                "\N{EXCLAMATION QUESTION MARK}: Fumble scoreboard\n"
            )
        stats_len = len(humanize_number(entries[0][1][self._stat])) + 3
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        stats_plural = self._stat if self._stat.endswith("s") else f"{self._stat}s"
        stats_len = (len(stats_plural) if len(stats_plural) > stats_len else stats_len) + 2
        rebirth_len = len("Rebirths") + 2
        header = f"{'#':{pos_len}}{stats_plural.title().ljust(stats_len)}{'Rebirths':{rebirth_len}}{'Adventurer':2}"
        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for (position, (user_id, account_data)) in enumerate(entries, start=start_position):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name
            username = escape(str(username), formatting=True)
            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            rebirths = humanize_number(account_data["rebirths"])
            stats_value = humanize_number(account_data[self._stat.lower()])

            data = f"{f'{pos_str}.':{pos_len}}" f"{stats_value:{stats_len}}" f"{rebirths:{rebirth_len}}" f"{username}"
            players.append(data)

        embed = discord.Embed(
            title=f"Adventure {self._stat.title()} Scoreboard",
            color=await menu.ctx.embed_color(),
            description="```md\n{}``` ```md\n{}```".format(header, "\n".join(players),),
        )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return {"embed": embed, "content": self._legend}


class NVScoreboardSource(WeeklyScoreboardSource):
    def __init__(self, entries: List[Tuple[int, Dict]], stat: Optional[str] = None):
        super().__init__(entries)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[int, Dict]]):
        ctx = menu.ctx
        loses_len = max(len(humanize_number(entries[0][1]["loses"])) + 3, 8)
        win_len = max(len(humanize_number(entries[0][1]["wins"])) + 3, 6)
        xp__len = max(len(humanize_number(entries[0][1]["xp__earnings"])) + 3, 8)
        gold__len = max(len(humanize_number(entries[0][1]["gold__losses"])) + 3, 12)
        start_position = (menu.current_page * self.per_page) + 1
        pos_len = len(str(start_position + 9)) + 2
        header = (
            f"{'#':{pos_len}}{'Wins':{win_len}}"
            f"{'Losses':{loses_len}}{'XP Won':{xp__len}}{'Gold Spent':{gold__len}}{'Adventurer':2}"
        )

        author = ctx.author

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None

        players = []
        for (position, (user_id, account_data)) in enumerate(entries, start=start_position):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name

            username = escape(str(username), formatting=True)
            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = position
            loses = humanize_number(account_data["loses"])
            wins = humanize_number(account_data["wins"])
            xp__earnings = humanize_number(account_data["xp__earnings"])
            gold__losses = humanize_number(account_data["gold__losses"])

            data = (
                f"{f'{pos_str}.':{pos_len}} "
                f"{wins:{win_len}} "
                f"{loses:{loses_len}} "
                f"{xp__earnings:{xp__len}} "
                f"{gold__losses:{gold__len}} "
                f"{username}"
            )
            players.append(data)
        msg = "Adventure Negaverse Scoreboard\n```md\n{}``` ```md\n{}``````md\n{}```".format(
            header, "\n".join(players), f"Page {menu.current_page + 1}/{self.get_max_pages()}"
        )
        return msg


class SimpleSource(menus.ListPageSource):
    def __init__(self, entries: List[str, discord.Embed]):
        super().__init__(entries, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page: Union[str, discord.Embed]):
        return page


class EconomySource(menus.ListPageSource):
    def __init__(self, entries: List[Tuple[str, Dict[str, Any]]]):
        super().__init__(entries, per_page=10)
        self._total_balance_unified = None
        self._total_balance_sep = None
        self.author_position = None

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, entries: List[Tuple[str, Dict[str, Any]]]) -> discord.Embed:
        guild = menu.ctx.guild
        author = menu.ctx.author
        position = (menu.current_page * self.per_page) + 1
        bal_len = len(humanize_number(entries[0][1]["balance"]))
        pound_len = len(str(position + 9))
        user_bal = await bank.get_balance(menu.ctx.author, _forced=not menu.ctx.cog._separate_economy)
        if self.author_position is None:
            self.author_position = await bank.get_leaderboard_position(menu.ctx.author)
        header_primary = "{pound:{pound_len}}{score:{bal_len}}{name:2}\n".format(
            pound="#", name=_("Name"), score=_("Score"), bal_len=bal_len + 6, pound_len=pound_len + 3,
        )
        header = ""
        if menu.ctx.cog._separate_economy:
            if self._total_balance_sep is None:
                accounts = await bank._config.all_users()
                overall = 0
                for key, value in accounts.items():
                    overall += value["balance"]
                self._total_balance_sep = overall
            _total_balance = self._total_balance_sep
        else:
            if self._total_balance_unified is None:
                accounts = await bank._get_config(_forced=True).all_users()
                overall = 0
                for key, value in accounts.items():
                    overall += value["balance"]
                self._total_balance_unified = overall
            _total_balance = self._total_balance_unified
        percent = round((int(user_bal) / _total_balance * 100), 3)
        for position, acc in enumerate(entries, start=position):
            user_id = acc[0]
            account_data = acc[1]
            balance = account_data["balance"]
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None
            if member is not None:
                username = member.display_name
            else:
                user = menu.ctx.bot.get_user(user_id)
                if user is None:
                    username = f"{user_id}"
                else:
                    username = user.name
            username = escape(username, formatting=True)
            balance = humanize_number(balance)

            if acc[0] != author.id:
                header += f"{f'{humanize_number(position)}.': <{pound_len + 2}} {balance: <{bal_len + 5}} {username}\n"
            else:
                header += (
                    f"{f'{humanize_number(position)}.': <{pound_len + 2}} "
                    f"{balance: <{bal_len + 5}} "
                    f"<<{username}>>\n"
                )
        if self.author_position is not None:
            embed = discord.Embed(
                title="Adventure Economy Leaderboard\nYou are currently # {}/{}".format(
                    self.author_position, len(self.entries)
                ),
                color=await menu.ctx.embed_color(),
                description="```md\n{}``` ```md\n{}``` ```py\nTotal bank amount {}\nYou have {}% of the total amount!```".format(
                    header_primary, header, humanize_number(_total_balance), percent
                ),
            )
        else:
            embed = discord.Embed(
                title="Adventure Economy Leaderboard\n",
                color=await menu.ctx.embed_color(),
                description="```md\n{}``` ```md\n{}``` ```py\nTotal bank amount {}\nYou have {}% of the total amount!```".format(
                    header_primary, header, humanize_number(_total_balance), percent
                ),
            )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")

        return embed


class BaseMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.__tasks = self._Menu__tasks

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

    async def start(self, ctx, *, channel=None, wait=False, page: int = 0):
        """
        Starts the interactive menu session.

        Parameters
        -----------
        ctx: :class:`Context`
            The invocation context to use.
        channel: :class:`discord.abc.Messageable`
            The messageable to send the message to. If not given
            then it defaults to the channel in the context.
        wait: :class:`bool`
            Whether to wait until the menu is completed before
            returning back to the caller.

        Raises
        -------
        MenuError
            An error happened when verifying permissions.
        discord.HTTPException
            Adding a reaction failed.
        """

        # Clear the buttons cache and re-compute if possible.
        try:
            del self.buttons
        except AttributeError:
            pass

        self.bot = bot = ctx.bot
        self.ctx = ctx
        self._author_id = ctx.author.id
        channel = channel or ctx.channel
        is_guild = isinstance(channel, discord.abc.GuildChannel)
        me = ctx.guild.me if is_guild else ctx.bot.user
        permissions = channel.permissions_for(me)
        self.__me = discord.Object(id=me.id)
        self._verify_permissions(ctx, channel, permissions)
        self._event.clear()
        msg = self.message
        if msg is None:
            self.message = msg = await self.send_initial_message(ctx, channel, page=page)
        if self.should_add_reactions():
            # Start the task first so we can listen to reactions before doing anything
            for task in self.__tasks:
                task.cancel()
            self.__tasks.clear()

            self._running = True
            self.__tasks.append(bot.loop.create_task(self._internal_loop()))

            if self.should_add_reactions():

                async def add_reactions_task():
                    for emoji in self.buttons:
                        await msg.add_reaction(emoji)

                self.__tasks.append(bot.loop.create_task(add_reactions_task()))

            if wait:
                await self._event.wait()

    async def send_initial_message(self, ctx: commands.Context, channel: discord.abc.Messageable, page: int = 0):
        """

        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.

        This implementation shows the first page of the source.
        """
        self.current_page = page
        page = await self._source.get_page(page)
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (*self.bot.owner_ids, self._author_id):
            return False
        return payload.emoji in self.buttons

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
        skip_if=_skip_single_arrows,
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
        skip_if=_skip_single_arrows,
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()


class ScoreBoardMenu(BaseMenu, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        show_global: bool = False,
        current_scoreboard: str = "wins",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.show_global = show_global
        self._current = current_scoreboard

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    @menus.button("\N{FACE WITH PARTY HORN AND PARTY HAT}")
    async def wins(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "wins":
            return
        self._current = "wins"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button("\N{FIRE}")
    async def losses(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "loses":
            return
        self._current = "loses"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button("\N{DAGGER KNIFE}")
    async def physical(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        if self._current == "fight":
            return
        self._current = "fight"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button("\N{SPARKLES}")
    async def magic(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "spell":
            return
        self._current = "spell"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button("\N{LEFT SPEECH BUBBLE}")
    async def diplomacy(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "talk":
            return
        self._current = "talk"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button("\N{PERSON WITH FOLDED HANDS}")
    async def praying(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "pray":
            return
        self._current = "pray"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button("\N{RUNNER}")
    async def runner(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "run":
            return
        self._current = "run"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button("\N{EXCLAMATION QUESTION MARK}")
    async def fumble(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "fumbles":
            return
        self._current = "fumbles"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(source=ScoreboardSource(entries=rebirth_sorted, stat=self._current))

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}", skip_if=_skip_single_arrows,
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}", skip_if=_skip_single_arrows,
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)


class LeaderboardMenu(BaseMenu, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        show_global: bool = False,
        current_scoreboard: str = "leaderboard",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.show_global = show_global
        self._current = current_scoreboard

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()

        if max_pages is None:
            return True
        return max_pages <= 2

    def _unified_bank(self):
        return not self.cog._separate_economy

    @menus.button("\N{CHART WITH UPWARDS TREND}")
    async def home(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "leaderboard":
            return
        self._current = "leaderboard"
        rebirth_sorted = await self.cog.get_leaderboard(guild=self.ctx.guild if not self.show_global else None)
        await self.change_source(source=LeaderboardSource(entries=rebirth_sorted))

    @menus.button("\N{MONEY WITH WINGS}")
    async def economy(self, payload: discord.RawReactionActionEvent) -> None:
        if self._current == "economy":
            return
        self._current = "economy"
        bank_sorted = await bank.get_leaderboard(
            guild=self.ctx.guild if not self.show_global else None, _forced=self._unified_bank()
        )
        await self.change_source(source=EconomySource(entries=bank_sorted))

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}", skip_if=_skip_single_arrows,
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}", skip_if=_skip_single_arrows,
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)


class BackpackMenu(BaseMenu, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        help_command: commands.Command,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.__help_command = help_command

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (*self.bot.owner_ids, self._author_id):
            return False
        return payload.emoji in self.buttons

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
        skip_if=_skip_single_arrows,
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
        skip_if=_skip_single_arrows,
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()

    @menus.button("\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16}")
    async def send_help(self, payload: discord.RawReactionActionEvent) -> None:
        """Sends help for the provided command."""
        await self.ctx.send_help(self.__help_command)
        self.delete_message_after = True
        self.stop()
