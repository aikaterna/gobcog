# -*- coding: utf-8 -*-
import logging
from datetime import date
from typing import List

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter

from .abc import AdventureMixin
from .helpers import smart_embed
from .menus import (
    BaseMenu,
    LeaderboardMenu,
    LeaderboardSource,
    NVScoreboardSource,
    ScoreBoardMenu,
    ScoreboardSource,
    WeeklyScoreboardSource,
)

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class LeaderboardCommands(AdventureMixin):
    """This class will handle generating and posting leaerboard information"""

    async def get_leaderboard(self, positions: int = None, guild: discord.Guild = None) -> List[tuple]:
        """Gets the Adventure's leaderboard.

        Parameters
        ----------
        positions : `int`
            The number of positions to get
        guild : discord.Guild
            The guild to get the leaderboard of. If this
            is provided, get only guild members on the leaderboard

        Returns
        -------
        `list` of `tuple`
            The sorted leaderboard in the form of :code:`(user_id, raw_account)`
        """
        raw_accounts = await self.config.all_users()
        if guild is not None:
            tmp = raw_accounts.copy()
            for acc in tmp:
                if not guild.get_member(acc):
                    del raw_accounts[acc]
        raw_accounts_new = {}
        async for (k, v) in AsyncIter(raw_accounts.items(), steps=100):
            user_data = {}
            for item in ["lvl", "rebirths", "set_items"]:
                if item not in v:
                    v.update({item: 0})
            for (vk, vi) in v.items():
                if vk in ["lvl", "rebirths", "set_items"]:
                    user_data.update({vk: vi})

            if user_data:
                user_data = {k: user_data}
            raw_accounts_new.update(user_data)
        sorted_acc = sorted(
            raw_accounts_new.items(),
            key=lambda x: (x[1].get("rebirths", 0), x[1].get("lvl", 1), x[1].get("set_items", 0)),
            reverse=True,
        )
        if positions is None:
            return sorted_acc
        else:
            return sorted_acc[:positions]

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.guild_only()
    async def aleaderboard(self, ctx: commands.Context, show_global: bool = False):
        """Print the leaderboard."""
        guild = ctx.guild
        rebirth_sorted = await self.get_leaderboard(guild=guild if not show_global else None)
        if rebirth_sorted:
            await LeaderboardMenu(
                source=LeaderboardSource(entries=rebirth_sorted),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
                cog=self,
                show_global=show_global,
            ).start(ctx=ctx)
        else:
            await smart_embed(ctx, _("There are no adventurers in the server."))

    async def get_global_scoreboard(
        self, positions: int = None, guild: discord.Guild = None, keyword: str = None
    ) -> List[tuple]:
        """Gets the bank's leaderboard.

        Parameters
        ----------
        positions : `int`
            The number of positions to get
        guild : discord.Guild
            The guild to get the leaderboard of. If this
            is provided, get only guild members on the leaderboard

        Returns
        -------
        `list` of `tuple`
            The sorted leaderboard in the form of :code:`(user_id, raw_account)`

        Raises
        ------
        TypeError
            If the bank is guild-specific and no guild was specified
        """
        if keyword is None:
            keyword = "wins"
        raw_accounts = await self.config.all_users()
        if guild is not None:
            tmp = raw_accounts.copy()
            for acc in tmp:
                if not guild.get_member(acc):
                    del raw_accounts[acc]
        raw_accounts_new = {}
        async for (k, v) in AsyncIter(raw_accounts.items(), steps=200):
            user_data = {}
            for item in ["adventures", "rebirths"]:
                if item not in v:
                    if item == "adventures":
                        v.update({item: {keyword: 0}})
                    else:
                        v.update({item: 0})

            for (vk, vi) in v.items():
                if vk in ["rebirths"]:
                    user_data.update({vk: vi})
                elif vk in ["adventures"]:
                    for (s, sv) in vi.items():
                        if s == keyword:
                            user_data.update(vi)

            if user_data:
                user_data = {k: user_data}
            raw_accounts_new.update(user_data)

        sorted_acc = sorted(
            raw_accounts_new.items(),
            key=lambda x: (x[1].get(keyword, 0), x[1].get("rebirths", 0)),
            reverse=True,
        )
        if positions is None:
            return sorted_acc
        else:
            return sorted_acc[:positions]

    async def get_global_negaverse_scoreboard(self, positions: int = None, guild: discord.Guild = None) -> List[tuple]:
        """Gets the bank's leaderboard.

        Parameters
        ----------
        positions : `int`
            The number of positions to get
        guild : discord.Guild
            The guild to get the leaderboard of. If this
            is provided, get only guild members on the leaderboard

        Returns
        -------
        `list` of `tuple`
            The sorted leaderboard in the form of :code:`(user_id, raw_account)`

        Raises
        ------
        TypeError
            If the bank is guild-specific and no guild was specified
        """
        raw_accounts = await self.config.all_users()
        if guild is not None:
            tmp = raw_accounts.copy()
            for acc in tmp:
                if not guild.get_member(acc):
                    del raw_accounts[acc]
        raw_accounts_new = {}
        async for (k, v) in AsyncIter(raw_accounts.items(), steps=200):
            user_data = {}
            for (vk, vi) in v.items():
                if vk in ["nega"]:
                    for (s, sv) in vi.items():
                        user_data.update(vi)

            if user_data:
                user_data = {k: user_data}
            raw_accounts_new.update(user_data)

        sorted_acc = sorted(
            raw_accounts_new.items(),
            key=lambda x: (x[1].get("wins", 0), x[1].get("loses", 0)),
            reverse=True,
        )
        if positions is None:
            return sorted_acc
        else:
            return sorted_acc[:positions]

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.guild_only()
    async def scoreboard(self, ctx: commands.Context, show_global: bool = False):
        """Print the scoreboard."""

        rebirth_sorted = await self.get_global_scoreboard(guild=ctx.guild if not show_global else None, keyword="wins")
        if rebirth_sorted:
            await ScoreBoardMenu(
                source=ScoreboardSource(entries=rebirth_sorted, stat="wins"),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
                cog=self,
                show_global=show_global,
            ).start(ctx=ctx)
        else:
            await smart_embed(ctx, _("There are no adventurers in the server."))

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.guild_only()
    async def nvsb(self, ctx: commands.Context, show_global: bool = False):
        """Print the negaverse scoreboard."""
        guild = ctx.guild
        rebirth_sorted = await self.get_global_negaverse_scoreboard(guild=guild if not show_global else None)
        if rebirth_sorted:
            await BaseMenu(
                source=NVScoreboardSource(entries=rebirth_sorted),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)
        else:
            await smart_embed(ctx, _("There are no adventurers in the server."))

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.guild_only()
    async def wscoreboard(self, ctx: commands.Context, show_global: bool = False):
        """Print the weekly scoreboard."""

        stats = "adventures"
        guild = ctx.guild
        adventures = await self.get_weekly_scoreboard(guild=guild if not show_global else None)
        if adventures:
            await BaseMenu(
                source=WeeklyScoreboardSource(entries=adventures, stat=stats.lower()),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)
        else:
            await smart_embed(ctx, _("No stats to show for this week."))

    async def get_weekly_scoreboard(self, positions: int = None, guild: discord.Guild = None) -> List[tuple]:
        """Gets the bank's leaderboard.

        Parameters
        ----------
        positions : `int`
            The number of positions to get
        guild : discord.Guild
            The guild to get the leaderboard of. If this
            is provided, get only guild members on the leaderboard

        Returns
        -------
        `list` of `tuple`
            The sorted leaderboard in the form of :code:`(user_id, raw_account)`

        Raises
        ------
        TypeError
            If the bank is guild-specific and no guild was specified
        """
        current_week = date.today().isocalendar()[1]
        keyword = "adventures"
        raw_accounts = await self.config.all_users()
        if guild is not None:
            tmp = raw_accounts.copy()
            for acc in tmp:
                if not guild.get_member(acc):
                    del raw_accounts[acc]
        raw_accounts_new = {}
        async for (k, v) in AsyncIter(raw_accounts.items(), steps=200):
            user_data = {}
            for item in ["weekly_score"]:
                if item not in v:
                    if item == "weekly_score":
                        v.update({item: {keyword: 0, "rebirths": 0}})

            for (vk, vi) in v.items():
                if vk in ["weekly_score"]:
                    if vi.get("week", -1) == current_week:
                        for (s, sv) in vi.items():
                            if s in [keyword]:
                                user_data.update(vi)

            if user_data:
                user_data = {k: user_data}
            raw_accounts_new.update(user_data)

        sorted_acc = sorted(
            raw_accounts_new.items(),
            key=lambda x: (x[1].get(keyword, 0), x[1].get("rebirths", 0)),
            reverse=True,
        )
        if positions is None:
            return sorted_acc
        else:
            return sorted_acc[:positions]
