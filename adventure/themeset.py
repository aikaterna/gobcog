# -*- coding: utf-8 -*-
import logging
import os

import discord
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator

from .abc import AdventureMixin
from .converters import ThemeSetMonterConverter, ThemeSetPetConverter
from .helpers import smart_embed
from .menus import BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class ThemesetCommands(AdventureMixin):
    """This class will handle setting themes for adventure"""

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def themeset(self, ctx: commands.Context):
        """[Admin] Modify themes."""

    @commands.is_owner()
    @themeset.group(name="add")
    async def themeset_add(self, ctx: commands.Context):
        """[Owner] Add/Update objects in the specified theme."""

    @themeset_add.command(name="monster")
    async def themeset_add_monster(self, ctx: commands.Context, *, theme_data: ThemeSetMonterConverter):
        """[Owner] Add/Update a monster object in the specified theme.

        Usage: `[p]themeset add monster theme++name++hp++dipl++pdef++mdef++cdef++boss++image`
        """
        assert isinstance(theme_data, dict)
        theme = theme_data.pop("theme", None)
        if theme != "default" and theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        updated = False
        monster = theme_data.pop("name", None)
        async with self.config.themes.all() as config_data:
            if theme not in config_data:
                config_data[theme] = {"monsters": {}}
            if "monsters" not in config_data[theme]:
                config_data[theme]["monsters"] = {}
            if monster in config_data[theme]["monsters"]:
                updated = True
            config_data[theme]["monsters"][monster] = theme_data
        image = theme_data.pop("image", None)
        text = _(
            "Monster: `{monster}` has been {status} the `{theme}` theme\n"
            "```ini\n"
            "HP:                  [{hp}]\n"
            "Diplomacy:           [{dipl}]\n"
            "Physical defence:    [{pdef}]\n"
            "Magical defence:     [{mdef}]\n"
            "Persuasion defence:  [{cdef}]\n"
            "Is a boss:           [{boss}]```"
        ).format(
            monster=monster,
            theme=theme,
            status=_("added to") if not updated else _("updated in"),
            **theme_data,
        )

        embed = discord.Embed(description=text, colour=await ctx.embed_colour())
        embed.set_image(url=image)
        await ctx.send(embed=embed)

    @themeset_add.command(name="pet")
    async def themeset_add_pet(self, ctx: commands.Context, *, pet_data: ThemeSetPetConverter):
        """[Owner] Add/Update a pet object in the specified theme.

        Usage: `[p]themeset add pet theme++name++bonus_multiplier++required_cha++crit_chance++always_crit`
        """
        assert isinstance(pet_data, dict)
        theme = pet_data.pop("theme", None)
        if theme != "default" and theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        updated = False
        pet = pet_data.pop("name", None)
        async with self.config.themes.all() as config_data:
            if theme not in config_data:
                config_data[theme] = {"pet": {}}
            if "pet" not in config_data[theme]:
                config_data[theme]["pet"] = {}
            if pet in config_data[theme]["pet"]:
                updated = True
            config_data[theme]["pet"][pet] = pet_data

        pet_bonuses = pet_data.pop("bonuses", {})
        text = _(
            "Pet: `{pet}` has been {status} the `{theme}` theme\n"
            "```ini\n"
            "Bonus Multiplier:  [{bonus}]\n"
            "Required Charisma: [{cha}]\n"
            "Pet always crits:  [{always}]\n"
            "Critical Chance:   [{crit}/100]```"
        ).format(
            pet=pet,
            theme=theme,
            status=_("added to") if not updated else _("updated in"),
            **pet_data,
            **pet_bonuses,
        )

        embed = discord.Embed(description=text, colour=await ctx.embed_colour())
        await ctx.send(embed=embed)

    @commands.is_owner()
    @themeset.group(name="delete", aliases=["del", "rem", "remove"])
    async def themeset_delete(self, ctx: commands.Context):
        """[Owner] Remove objects in the specified theme."""

    @themeset_delete.command(name="monster")
    async def themeset_delete_monster(self, ctx: commands.Context, theme: str, *, monster: str):
        """[Owner] Remove a monster object in the specified theme."""
        if theme != "default" and theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        async with self.config.themes.all() as config_data:
            if theme not in config_data:
                config_data[theme] = {"monsters": {}}
            if "monsters" not in config_data[theme]:
                config_data[theme]["monsters"] = {}
            if monster in config_data[theme]["monsters"]:
                del config_data[theme]["monsters"][monster]
            else:
                text = _("Monster: `{monster}` does not exist in `{theme}` theme").format(monster=monster, theme=theme)
                await smart_embed(ctx, text)
                return

        text = _("Monster: `{monster}` has been deleted from the `{theme}` theme").format(monster=monster, theme=theme)
        await smart_embed(ctx, text)

    @themeset_delete.command(name="pet")
    async def themeset_delete_pet(self, ctx: commands.Context, theme: str, *, pet: str):
        """[Owner] Remove a pet object in the specified theme."""
        if theme != "default" and theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        async with self.config.themes.all() as config_data:
            if theme not in config_data:
                config_data[theme] = {"pet": {}}
            if "pet" not in config_data[theme]:
                config_data[theme]["pet"] = {}
            if pet in config_data[theme]["pet"]:
                del config_data[theme]["pet"][pet]
            else:
                text = _("Pet: `{pet}` does not exist in `{theme}` theme").format(pet=pet, theme=theme)
                await smart_embed(ctx, text)
                return

        text = _("Pet: `{pet}` has been deleted from the `{theme}` theme").format(pet=pet, theme=theme)
        await smart_embed(ctx, text)

    @themeset.group(name="list", aliases=["show"])
    async def themeset_list(self, ctx: commands.Context):
        """[Admin] Show custom objects in the specified theme."""

    @themeset_list.command(name="monster")
    async def themeset_list_monster(self, ctx: commands.Context, *, theme: str):
        """[Admin] Show monster objects in the specified theme."""
        if theme != "default" and theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        async with self.config.themes.all() as config_data:
            if theme not in config_data:
                return await smart_embed(ctx, _("No custom monsters exist in this theme"))
            monster_data = config_data.get(theme, {}).get("monsters", {})
        embed_list = []
        for monster, monster_stats in monster_data.items():
            image = monster_stats.get("image")
            monster_stats["cdef"] = monster_stats.get("cdef", 1.0)
            text = _(
                "```ini\n"
                "HP:                  [{hp}]\n"
                "Diplomacy:           [{dipl}]\n"
                "Physical defence:    [{pdef}]\n"
                "Magical defence:     [{mdef}]\n"
                "Persuasion defence:  [{cdef}]\n"
                "Is a boss:           [{boss}]```"
            ).format(**monster_stats)
            embed = discord.Embed(title=monster, description=text)
            embed.set_image(url=image)
            embed_list.append(embed)
        if embed_list:
            await BaseMenu(
                source=SimpleSource(embed_list),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)

    @themeset_list.command(name="pet")
    async def themeset_list_pet(self, ctx: commands.Context, *, theme: str):
        """[Admin] Show pet objects in the specified theme."""
        if theme != "default" and theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        async with self.config.themes.all() as config_data:
            if theme not in config_data:
                return await smart_embed(ctx, _("No custom monsters exist in this theme"))
            monster_data = config_data.get(theme, {}).get("pet", {})
        embed_list = []
        for pet, pet_stats in monster_data.items():
            pet_bonuses = pet_stats.pop("bonuses", {})
            text = _(
                "```ini\n"
                "Bonus Multiplier:  [{bonus}]\n"
                "Required Charisma: [{cha}]\n"
                "Pet always crits:  [{always}]\n"
                "Critical Chance:   [{crit}/100]```"
            ).format(theme=theme, **pet_stats, **pet_bonuses)
            embed = discord.Embed(title=pet, description=text)
            embed_list.append(embed)
        if embed_list:
            await BaseMenu(
                source=SimpleSource(embed_list),
                delete_message_after=True,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)
