# Main Arguments
**--slot** - Accepts multiple slots (use quotes if there are spaces in a slot name).<br />
**--rarity** - Accepts multiple rarities.<br />
**--set** - Accepts multiple sets (use quotes if there are spaces in the set name).<br />
**--equip** - If used will only show equippable items.<br />
**--diff** - If used will show the stat delta compared to what you currently have equipped (Only works on `[p]cbackpack show`).<br />
**--except** - If used will show everything that does not match the specified query.<br />
**--match** - Accepts a string, no quotes are needed. Will attempt to match items to this string.<br />
**--no-match** - Opposite of `--no-match`<br />
**--icase** - If `--match` or `--no-match` and `--icase` are used, matches will not be case sensitive.<br />

######For the following arguments: <br />
- These arguments accept 1 or 2 numbers. If 1 is passed it is treated as an equal match, if 2 then it is a range.<br />
  - **--str**<br />
  - **--int**<br />
  - **--cha**<br />
  - **--luc**<br />
  - **--dex**<br />
  - **--lvl**<br />
  - **--deg** (Only works on `[p]cbackpack show`)<br />
  
## Example usage
- `[p]cbackpack show --equip --lvl >50`
  - Will show only items that you are able to equip which have level higher than 50. 
- `[p]cbackpack sell --slot head charm --rarity legendary ascended --no-match celestial --icase --lvl >50 <100`
  - Will sell all legendary and ascended items in the head and charm slot that do not have the word "celestial" in them and that their level is between 51 and 99
- `[p]cbackpack show --except --str >50`
  - Will show all items that have less than 50 str points
- `[p]cbackpack show --except --no-match celestial`  
  - Will Show every item that have "celestial" in the name (Case sensitive as `--icase` was not used)