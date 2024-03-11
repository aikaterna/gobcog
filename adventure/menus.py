from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import discord
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, escape, humanize_number
from redbot.vendored.discord.ext import menus

from .bank import bank
from .charsheet import Character
from .helpers import is_dev, smart_embed

if TYPE_CHECKING:
    from .abc import AdventureMixin
    from .charsheet import BackpackTable

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
            description="```md\n{}``` ```md\n{}```".format(
                header,
                "\n".join(players),
            ),
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
        for position, (user_id, account_data) in enumerate(entries, start=start_position):
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
            description="```md\n{}``` ```md\n{}```".format(
                header,
                "\n".join(players),
            ),
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
        for position, (user_id, account_data) in enumerate(entries, start=start_position):
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
            description="```md\n{}``` ```md\n{}```".format(
                header,
                "\n".join(players),
            ),
        )
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


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
        for position, (user_id, account_data) in enumerate(entries, start=start_position):
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
            pound="#",
            name=_("Name"),
            score=_("Score"),
            bal_len=bal_len + 6,
            pound_len=pound_len + 3,
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


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int] = None,
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()


class _NavigateButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, emoji: Union[str, discord.PartialEmoji], direction: int):
        super().__init__(style=style, emoji=emoji)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        if self.direction == 0:
            self.view.current_page = 0
        elif self.direction == self.view.source.get_max_pages():
            self.view.current_page = self.view.source.get_max_pages() - 1
        else:
            self.view.current_page += self.direction
        try:
            page = await self.view.source.get_page(self.view.current_page)
        except IndexError:
            self.view.current_page = 0
            page = await self.view.source.get_page(self.view.current_page)
        kwargs = await self.view._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs)


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self._source = source
        self.page_start = kwargs.get("page_start", 0)
        self.current_page = self.page_start
        self.message = message
        self.forward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=1,
        )
        self.backward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=-1,
        )
        self.first_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=0,
        )
        self.last_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=self.source.get_max_pages(),
        )
        self.stop_button = StopButton(discord.ButtonStyle.red)
        self.add_item(self.stop_button)
        if self.source.is_paginating():
            self.add_item(self.first_button)
            self.add_item(self.backward_button)
            self.add_item(self.forward_button)
            self.add_item(self.last_button)

    async def on_timeout(self):
        if self.message is not None:
            await self.message.edit(view=None)

    @property
    def source(self):
        return self._source

    async def change_source(self, source: menus.PageSource, interaction: discord.Interaction):
        self._source = source
        self.current_page = 0
        if self.message is not None:
            await source._prepare_once()
            await self.show_page(0, interaction)

    async def update(self):
        """
        Define this here so that subclasses can utilize this hook
        and update the state of the view before sending.
        This is useful for modifying disabled buttons etc.

        This gets called after the page has been formatted.
        """
        pass

    async def start(
        self,
        ctx: Optional[commands.Context],
        *,
        wait=False,
        page: int = 0,
        interaction: Optional[discord.Interaction] = None,
    ):
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

        if ctx is not None:
            self.bot = ctx.bot
            self._author_id = ctx.author.id
        elif interaction is not None:
            self.bot = interaction.client
            self._author_id = interaction.user.id
        self.ctx = ctx
        msg = self.message
        if msg is None:
            self.message = await self.send_initial_message(ctx, page=page, interaction=interaction)
        if wait:
            return await self.wait()

    async def _get_kwargs_from_page(self, page: Any):
        value = await self.source.format_page(self, page)
        if isinstance(value, dict):
            value["view"] = self
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None, "view": self}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None, "view": self}
        return value

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self.source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.update()
        await interaction.response.edit_message(**kwargs)

    async def send_initial_message(
        self, ctx: Optional[commands.Context], page: int = 0, interaction: Optional[discord.Interaction] = None
    ):
        """

        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.

        This implementation shows the first page of the source.
        """
        self.current_page = page
        page = await self._source.get_page(page)
        kwargs = await self._get_kwargs_from_page(page)
        await self.update()
        if ctx is None and interaction is not None:
            await interaction.response.send_message(**kwargs)
            return await interaction.original_response()
        else:
            return await ctx.send(**kwargs)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id not in (*interaction.client.owner_ids, self._author_id):
            await interaction.response.send_message(_("You are not authorized to interact with this."), ephemeral=True)
            return False
        return True


class ScoreBoardMenu(BaseMenu):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        show_global: bool = False,
        current_scoreboard: str = "wins",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source=source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.show_global = show_global
        self._current = current_scoreboard

    async def update(self):
        buttons = {
            "wins": self.wins,
            "loses": self.losses,
            "fight": self.physical,
            "spell": self.magic,
            "talk": self.diplomacy,
            "pray": self.praying,
            "run": self.runner,
            "fumbles": self.fumble,
        }
        for button in buttons.values():
            button.disabled = False
        buttons[self._current].disabled = True

    @discord.ui.button(
        label=_("Wins"),
        style=discord.ButtonStyle.grey,
        emoji="\N{FACE WITH PARTY HORN AND PARTY HAT}",
        row=1,
        disabled=True,
    )
    async def wins(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "wins":
            await interaction.response.defer()
            # this deferal is unnecessary now since the buttons are just disabled
            # however, in the event that the button gets passed and the state is not
            # as we expect at least try not to send the user an interaction failed message
            return
        self._current = "wins"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Losses"), style=discord.ButtonStyle.grey, emoji="\N{FIRE}", row=1)
    async def losses(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "loses":
            await interaction.response.defer()
            return
        self._current = "loses"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Physical"), style=discord.ButtonStyle.grey, emoji="\N{DAGGER KNIFE}", row=1)
    async def physical(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """stops the pagination session."""
        if self._current == "fight":
            await interaction.response.defer()
            return
        self._current = "fight"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Magic"), style=discord.ButtonStyle.grey, emoji="\N{SPARKLES}", row=1)
    async def magic(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "spell":
            await interaction.response.defer()
            return
        self._current = "spell"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Charisma"), style=discord.ButtonStyle.grey, emoji="\N{LEFT SPEECH BUBBLE}", row=1)
    async def diplomacy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "talk":
            await interaction.response.defer()
            return
        self._current = "talk"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Pray"), style=discord.ButtonStyle.grey, emoji="\N{PERSON WITH FOLDED HANDS}", row=2)
    async def praying(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "pray":
            await interaction.response.defer()
            return
        self._current = "pray"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Run"), style=discord.ButtonStyle.grey, emoji="\N{RUNNER}", row=2)
    async def runner(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "run":
            await interaction.response.defer()
            return
        self._current = "run"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )

    @discord.ui.button(label=_("Fumbles"), style=discord.ButtonStyle.grey, emoji="\N{EXCLAMATION QUESTION MARK}", row=2)
    async def fumble(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "fumbles":
            await interaction.response.defer()
            return
        self._current = "fumbles"
        rebirth_sorted = await self.cog.get_global_scoreboard(
            guild=self.ctx.guild if not self.show_global else None, keyword=self._current
        )
        await self.change_source(
            source=ScoreboardSource(entries=rebirth_sorted, stat=self._current), interaction=interaction
        )


class LeaderboardMenu(BaseMenu):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
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

    async def update(self):
        buttons = {"leaderboard": self.home, "economy": self.economy}
        for button in buttons.values():
            button.disabled = False
        buttons[self._current].disabled = True

    def _unified_bank(self):
        return not self.cog._separate_economy

    @discord.ui.button(
        label=_("Leaderboard"),
        style=discord.ButtonStyle.grey,
        emoji="\N{CHART WITH UPWARDS TREND}",
        row=1,
        disabled=True,
    )
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "leaderboard":
            await interaction.response.defer()
            return
        self._current = "leaderboard"
        rebirth_sorted = await self.cog.get_leaderboard(guild=self.ctx.guild if not self.show_global else None)
        await self.change_source(source=LeaderboardSource(entries=rebirth_sorted), interaction=interaction)

    @discord.ui.button(label=_("Economy"), style=discord.ButtonStyle.grey, emoji="\N{MONEY WITH WINGS}", row=1)
    async def economy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._current == "economy":
            await interaction.response.defer()
            return
        self._current = "economy"
        bank_sorted = await bank.get_leaderboard(
            guild=self.ctx.guild if not self.show_global else None, _forced=self._unified_bank()
        )
        await self.change_source(source=EconomySource(entries=bank_sorted), interaction=interaction)


class BackpackSelectEquip(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption], placeholder: str, max_values: Optional[int] = None):
        self.view: BackpackMenu
        super().__init__(min_values=1, max_values=max_values or len(options), options=options, placeholder=placeholder)
        self.selected_items = []

    async def equip_items(self, interaction: discord.Interaction):
        if self.view.cog.in_adventure(self.view.ctx):
            return await smart_embed(
                message=_("You tried to equip an item but the monster ahead of you commands your attention."),
                ephemeral=True,
                interaction=interaction,
            )
        equip_msg = ""
        await interaction.response.defer()
        async with self.view.cog.get_lock(self.view.ctx.author):
            for item_index in self.values:
                equip_item = self.view.source.current_table.items[int(item_index)]
                try:
                    c = await Character.from_json(
                        self.view.ctx, self.view.cog.config, self.view.ctx.author, self.view.cog._daily_bonus
                    )
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    return
                equiplevel = c.equip_level(equip_item)
                if is_dev(self.view.ctx.author):  # FIXME:
                    equiplevel = 0

                if not c.can_equip(equip_item):
                    equip_msg += _("You need to be level `{level}` to equip {item}.").format(
                        level=equiplevel, item=equip_item.ansi
                    )
                    equip_msg += "\n\n"
                    continue

                equip = c.backpack.get(equip_item.name)
                if equip:
                    slot = equip.slot
                    put = getattr(c, equip.slot.char_slot)
                    equip_msg += _("{author} equipped {item} ({slot} slot)").format(
                        author=escape(self.view.ctx.author.display_name),
                        item=equip.as_ansi(),
                        slot=slot.get_name(),
                    )
                    if put:
                        equip_msg += " " + _("and put {put} into their backpack").format(
                            author=escape(self.view.ctx.author.display_name),
                            item=equip.as_ansi(),
                            slot=slot,
                            put=getattr(c, equip.slot.char_slot).as_ansi(),
                        )
                    c = await c.equip_item(equip, True, is_dev(self.view.ctx.author))  # FIXME:
                    await self.view.cog.config.user(self.view.ctx.author).set(
                        await c.to_json(self.view.ctx, self.view.cog.config)
                    )
                equip_msg += ".\n\n"
        await smart_embed(message=box(equip_msg, lang="ansi"), interaction=interaction)

    async def forge_items(self, interaction: discord.Interaction):
        for item_index in self.values:
            item = self.view.source.current_table.items[int(item_index)]
            if item in self.view.selected_items and item.owned < 2:
                return await smart_embed(
                    message=_("You can't make items out of thin air like that! This is a duplicate."),
                    interaction=interaction,
                    ephemeral=True,
                )
            self.view.selected_items.append(item)
        page = await self.view.source.get_page(self.view.current_page)
        kwargs = await self.view._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs)
        if len(self.view.selected_items) >= 2:
            self.view.stop()

    async def callback(self, interaction: discord.Interaction):
        if self.view.tinker_forge:
            return await self.forge_items(interaction)
        await self.equip_items(interaction)


class BackpackSource(menus.ListPageSource):
    def __init__(self, entries: List[BackpackTable]):
        super().__init__(entries, per_page=1)
        self.current_table = entries[0]
        self.select_options = [
            discord.SelectOption(label=str(item), value=i, description=item.stat_str(), emoji=item.rarity.emoji)
            for i, item in enumerate(self.current_table.items)
        ]

    def is_paginating(self):
        return True

    async def format_page(self, view: BackpackMenu, page: BackpackTable):
        self.current_table = page
        self.select_options = [
            discord.SelectOption(label=str(item), value=i, description=item.stat_str(), emoji=item.rarity.emoji)
            for i, item in enumerate(self.current_table.items)
        ]
        ret = str(page)

        if view.tinker_forge and view.selected_items:
            items = view.selected_items
            ret += box(_("Selected Items:\n{items}").format(items="\n".join([i.as_ansi() for i in items])), lang="ansi")
        return ret


class BackpackMenu(BaseMenu):
    def __init__(
        self,
        source: BackpackSource,
        help_command: commands.Command,
        cog: AdventureMixin,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        tinker_forge: bool = False,
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
        self.equip_select = None
        self.tinker_forge = tinker_forge

        self.cog = cog
        self.selected_items = []

    def _modify_select(self):
        if self.equip_select is not None:
            self.remove_item(self.equip_select)
        if getattr(self.source, "select_options", None):
            max_values = 1 if self.tinker_forge else None
            placeholder = _("Forge") if self.tinker_forge else _("Equip")
            self.equip_select = BackpackSelectEquip(self.source.select_options, placeholder, max_values)
            self.add_item(self.equip_select)

    async def _get_kwargs_from_page(self, page: Any):
        ret = await super()._get_kwargs_from_page(page)
        self._modify_select()
        return ret

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16}", row=1)
    async def send_help(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Sends help for the provided command."""
        await interaction.response.defer()
        await self.ctx.send_help(self.__help_command)
