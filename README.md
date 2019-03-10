Hello! You found the adventure page!

This cog was originally made by locastan and can be found at the fork link above.


This version is significantly different internally and features:

* Using Config for data management and more atomic user attribute saving
* Expanded mob/monster list for a stat and monster combo of over 2,800 possibilities
* Added 300% more gear possibilities
* Doubled the amount of item slots
* The game can be played on multiple servers at once


Things I would like to improve in the future, or will very gladly welcome PRs on:

* End of game HP display (show total groups’ hit vs mob points, for both str and cha)
* Make it so that the backpack can hold more than 1x of each item (double items overwrite)
* Trade unopened loot boxes between players
* Add alternate stats like dexterity/agility that would affect things like critical chance (and revamping the entire system to accept and use other stats like that)
* Add player races (gives permanent bonus that scales with level for 1-5 additional points in a stat)
* Revamp calculations for player 1-20 rolls during adventure to mitigate stat bloat at the higher end of the game (currently managed through a very wide range of mobs with varying str/hp values)

If you have something you would like to request for this cog, PLEASE OPEN AN ISSUE HERE AND DESCRIBE IT. I will not be taking requests for this via DMs or Discord messages. This cog is also on hold for improvements authored by me until I have more time for it, but nothing wrong with writing something yourself and PRing it!

# Introduction to Adventure! 

Start an adventure do `[p]adventure` and anyone can choose 🗡 to attack the monster, 🗨 to talk with the monster, 🛐 to pray to the god Herbert (Customizable per server for admins or globally for bot owner) for help, or 🏃‍♀️ to run away from the monster. The more people helping the easier it is to defeat the monster and acquire its loot.

To start an adventure type `[p]adventure` and everyone can join in.
Classes can be chosen at level 10 and you can choose between Tinkerer, Berserker, Cleric, Ranger and Bard using `[p]heroclass`. 

Tinkerers can forge two different items into a device bound to their very soul.Use the forge command.
Berserkers have the option to rage and add big bonuses to attacks, but fumbles hurt. Use the rage command when attacking in an adventure.
Clerics can bless the entire group when praying. Use the bless command when fighting in an adventure.
Rangers can gain a special pet, which can find items and give reward bonuses. Use the pet command to see pet options.
Bards can perform to aid their comrades in diplomacy. Use the music command when being diplomatic in an adventure.

Occasionally you will earn loot chests from the monsters use `[p]loot <rarity>` to open them and become stronger. 

Sometimes a cart will stroll past offering new items for players to buy, this is setup through `[p]adventureset cart <#channel>`.

To view your stats and equipment do `[p]stats` and `[p]backpack`.

You can use earned credits to enter the negaverse and fight a nega version of someone on this server to earn more experience points and level up faster using `[p]negaverse <number_of_credits>`

```css
[epic items look like this]
.rare_items_look_like_this
normal items look like this
```

Note: some commands can be done in DM with the bot instead if the bot has a global bank and you want to take your time reviewing your stats/equipment or open loot chests.
