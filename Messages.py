# text details: https://wiki.cloudmodding.com/oot/Text_Format

import random
from TextBox import line_wrap

TEXT_START = 0x92D000
ENG_TEXT_SIZE_LIMIT = 0x39000
JPN_TEXT_SIZE_LIMIT = 0x3A150

JPN_TABLE_START = 0xB808AC
ENG_TABLE_START = 0xB849EC
CREDITS_TABLE_START = 0xB88C0C

JPN_TABLE_SIZE = ENG_TABLE_START - JPN_TABLE_START
ENG_TABLE_SIZE = CREDITS_TABLE_START - ENG_TABLE_START

EXTENDED_TABLE_START = JPN_TABLE_START # start writing entries to the jp table instead of english for more space
EXTENDED_TABLE_SIZE = JPN_TABLE_SIZE + ENG_TABLE_SIZE # 0x8360 bytes, 4204 entries

# name of type, followed by number of additional bytes to read, follwed by a function that prints the code
CONTROL_CODES = {
    0x00: ('pad', 0, lambda _: '<pad>' ),
    0x01: ('line-break', 0, lambda _: '\n' ),
    0x02: ('end', 0, lambda _: '' ),
    0x04: ('box-break', 0, lambda _: '\n▼\n' ),
    0x05: ('color', 1, lambda d: '<color ' + "{:02x}".format(d) + '>' ),
    0x06: ('gap', 1, lambda d: '<' + str(d) + 'px gap>' ),
    0x07: ('goto', 2, lambda d: '<goto ' + "{:04x}".format(d) + '>' ),
    0x08: ('instant', 0, lambda _: '<allow instant text>' ),
    0x09: ('un-instant', 0, lambda _: '<disallow instant text>' ),
    0x0A: ('keep-open', 0, lambda _: '<keep open>' ),
    0x0B: ('event', 0, lambda _: '<event>' ),
    0x0C: ('box-break-delay', 1, lambda d: '\n▼<wait ' + str(d) + ' frames>\n' ),
    0x0E: ('fade-out', 1, lambda d: '<fade after ' + str(d) + ' frames?>' ),
    0x0F: ('name', 0, lambda _: '<name>' ),
    0x10: ('ocarina', 0, lambda _: '<ocarina>' ),
    0x12: ('sound', 2, lambda d: '<play SFX ' + "{:04x}".format(d) + '>' ),
    0x13: ('icon', 1, lambda d: '<icon ' + "{:02x}".format(d) + '>' ),
    0x14: ('speed', 1, lambda d: '<delay each character by ' + str(d) + ' frames>' ),
    0x15: ('background', 3, lambda d: '<set background to ' + "{:06x}".format(d) + '>' ),
    0x16: ('marathon', 0, lambda _: '<marathon time>' ),
    0x17: ('race', 0, lambda _: '<race time>' ),
    0x18: ('points', 0, lambda _: '<points>' ),
    0x19: ('skulltula', 0, lambda _: '<skulltula count>' ),
    0x1A: ('unskippable', 0, lambda _: '<text is unskippable>' ),
    0x1B: ('two-choice', 0, lambda _: '<start two choice>' ),
    0x1C: ('three-choice', 0, lambda _: '<start three choice>' ),
    0x1D: ('fish', 0, lambda _: '<fish weight>' ),
    0x1E: ('high-score', 1, lambda d: '<high-score ' + "{:02x}".format(d) + '>' ),
    0x1F: ('time', 0, lambda _: '<current time>' ),
}

SPECIAL_CHARACTERS = {
    0x96: 'é',
    0x9F: '[A]',
    0xA0: '[B]',
    0xA1: '[C]',
    0xA2: '[L]',
    0xA3: '[R]',
    0xA4: '[Z]',
    0xA5: '[C Up]',
    0xA6: '[C Down]',
    0xA7: '[C Left]',
    0xA8: '[C Right]',
    0xA9: '[Triangle]',
    0xAA: '[Control Stick]',
}

GOSSIP_STONE_MESSAGES = list( range(0x0401, 0x04FF) ) # ids of the actual hints
GOSSIP_STONE_MESSAGES += [0x2053, 0x2054] # shared initial stone messages
TEMPLE_HINTS_MESSAGES = [0x7057, 0x707A] # dungeon reward hints from the temple of time pedestal
LIGHT_ARROW_HINT = [0x70CC] # ganondorf's light arrow hint line
GS_TOKEN_MESSAGES = [0x00B4, 0x00B5] # Get Gold Skulltula Token messages
ERROR_MESSAGE = 0x0001

# messages for shorter item messages
# ids are in the space freed up by move_shop_item_messages()
ITEM_MESSAGES = {
    0x0001: "\x08\x06\x30\x05\x41TEXT ID ERROR!\x05\x40",
    0x9001: "\x08\x13\x2DYou borrowed a \x05\x41Collector's Edition Infinity Stone\x05\x40!\x01You're reminded of MvCI\x01and now you're sad.",
    0x0002: "\x08\x13\x2FYou returned the Pocket Cock\x01and got \x05\x41Covid Chicken\x05\x40 in return!\x04\x08\x13\x2FThe Chinese smile on\x01your misfortune.",
    0x0003: "\x08\x13\x30You got a \x05\x41Hallucinogenic Mushroom\x05\x40!\x01Take it to\x01see Geno in Smash.",
    0x0004: "\x08\x13\x31You received a \x05\x41Cum Rag\x05\x40!\x01It may be useful for something...\x01Hurry to the Lost Woods!",
    0x0005: "\x08\x13\x32You returned the Cum Rag \x01and got \x05\x41Bone-Saw\x05\x40!\x01Bone-Saw is ready!",
    0x0007: "\x08\x13\x48You got a \x01\x05\x41Dime Bag\x05\x40.\x01This bag sells for\x05\x4610\x05\x40\x01dollars.",
    0x0008: "\x08\x13\x33You traded the Bone-Saw \x01for a \x05\x41Moron Sword\x05\x40!\x01Visit Big-moron to get it repaired!",
    0x0009: "\x08\x13\x34You checked in the Broken \x01Moron Sword and received a \x01\x05\x41Viagra Prescription\x05\x40!\x01Go see King Zora!",
    0x000A: "\x08\x13\x37The Moron Sword...\x01You got a \x05\x41Claim Check \x05\x40for it!\x01It'll probably bounce.",
    0x000B: "\x08\x13\x2EYou got a \x05\x41Pocket Cock, \x05\x40one\x01of Anju's prized secrets! It fits \x01snugly in your pocket.",
    0x000C: "\x08\x13\x3DYou got the \x05\x41Big Moron Sword\x05\x40!\x01This blade was forged by a \x01dumb fuck and will probably break!",
    0x000D: "\x08\x13\x35You used the Viagra Prescription and\x01received a \x05\x41Gay Frog\x05\x40!\x01It reeks of chemicals and\x01agenda.",
    0x000E: "\x08\x13\x36You traded the Gay Frog \x01for the \x05\x41Bottled Cum\x05\x40!\x01Hurry! Take them to Biggoron!",
    0x0010: "\x08\x13\x25You borrowed a \x05\x41Boner Mask\x05\x40.\x01You feel like Jew Wario while you\x01wear this mask!",
    0x0011: "\x08\x13\x26You borrowed a \x05\x41Cosby Mask\x05\x40\x01Decide that you want it\x04\x08\x13\x26more than you are\x01afraid of it.",
    0x0012: "\x08\x13\x24You borrowed a \x05\x41Renamon Mask\x05\x40.\x01You'll be a popular guy with\x01this mask on!",
    0x0013: "\x08\x13\x27You borrowed a \x05\x41Bunny Suit\x05\x40.\x01leotard and stockings not\x01included!",
    0x0014: "\x08\x13\x28You borrowed a \x05\x41Genetic Mistake Mask\x05\x40.\x01It will make your head look\x01stupid, though.",
    0x0015: "\x08\x13\x29You borrowed a \x05\x41Fish Mask\x05\x40.\x01With this mask, you can\x01fuck Ruto!",
    0x0016: "\x08\x13\x2AYou borrowed a \x05\x41Pakistan Mask\x05\x40.\x01This mask will make it difficult\x01to get around airports.",
    0x0017: "\x08\x13\x2BYou borrowed a \x05\x41Mask of Truth\x05\x40.\x01Jews did 9/11.",
    0x0030: "\x08\x13\x06You found the \x05\x41Fairy Cumshot\x05\x40!",
    0x0031: "\x08\x13\x03I saw Tay at a grocery store in\x01Los Angeles yesterday.\x01I told her how cool it was to\x04\x08\x13\x03meet her in person, but I\x01didn't want to be a douche\x01and bother her and\x04\x08\x13\x03ask her for photos\x01 or anything. She said,\x01\"Oh, like you're doing now?\"\x04\x08\x13\x03 I was taken aback,\x01and all I could say was\x01\"Huh?\" but she kept cutting me off\x04\x08\x13\x03and going \"huh? huh? huh?\"\x01and closing her hand shut in front\x01 of my face. I walked \x04\x08\x13\x03away and continued with\x01my shopping, and I heard\x01her chuckle as I walked off.\x04\x08\x13\x03When I came to pay for my stuff\x01up front I saw her trying to walk\x01out the doors with\x04\x08\x13\x03like fifteen Milky Ways\x04\x08\x13\x03in her hands without paying.\x01The guy at the counter\x01was very nice about\x04\x08\x13\x03it and professional, and was like\x01 \"Mam, you need to pay for those\x01first.\" At first she kept pretending\x04\x08\x13\x03to be tired and not hear him,\x01 but eventually turned back around\x01and brought them to the counter.\x04\x08\x13\x03When he took one of the bars\x01and started scanning it multiple times,\x01 she stopped her and told her\x04\x08\x13\x03to scan them each individually\x01\"to prevent any electrical infetterence,\"\x01and then turned around and\x04\x08\x13\x03winked at me. I don't even think that's a\x01 word. After he scanned each bar\x01and put them in a bag and\x04\x08\x13\x03started to say the price,\x01she kept interrupting\x01him by yawning really loudly.",
    0x0032: "\x08\x13\x02You got \x05\x41IED's\x05\x40!\x01This will put you on\x01a watch list.",
    0x0033: "\x08\x13\x09You got \x05\x41Suicide Bomber Rats\x05\x40!",
    0x0034: "\x08\x13\x01You got \x05\x41Deez Nuts Nigga\x05\x40!",
    0x0035: "\x08\x13\x0EYou found the \x05\x41I can't think of anything\x05\x40!",
    0x0036: "\x08\x13\x0AYou found the \x05\x41Cumshot\x05\x40!\x01It's a spring-loaded sperm that\x01you can cast out to spurge things.",
    0x0037: "\x08\x13\x00You got a \x05\x41Blunt\x05\x40!",
    0x0038: "\x08\x13\x11You found the \x05\x41Hammer\x05\x40!\x01This ordinary tool is considered\x01sacred to Gorons.",
    0x0039: "\x08\x13\x0FYou found the \x05\x41Lens of Truth\x05\x40!\x01Cum stains are hidden\x01everywhere!",
    0x003A: "\x08\x13\x08You found the \x05\x41Rape Whistle\x05\x40!\x01Hopefully you won't need it...",
    0x003C: "\x08\x13\x67You received the \x05\x41Hot\x01Medallion\x05\x40!\x01Fuck Gorons.",
    0x003D: "\x08\x13\x68You received the \x05\x43Wet\x01Medallion\x05\x40!\x01Remember how these were\x01were supposed to do things?",
    0x003E: "\x08\x13\x66You received the \x05\x42Lugi's Mansion\x01Medallion\x05\x40!\x01Game of the year edition.",
    0x003F: "\x08\x13\x69You received the \x05\x46Mosque\x01Medallion\x05\x40!\x01Why are we like this?",
    0x0040: "\x08\x13\x6BYou received the \x05\x44Vanilla\x01Medallion\x05\x40!\x01Your partner is disappointed.",
    0x0041: "\x08\x13\x6AYou received the \x05\x45BDSM Dungeon\x01Medallion\x05\x40!\x01I tried ripping a\x0150 Shades of Grey line\x04\x08\x13\x6Bbut all of them suck so\x01I'm not writing anything\x01lewd on this one.",
    0x0042: "\x08\x13\x14You got an \x05\x41Empty Bottle of Gin\x05\x40!\x01A grim reminder of\x01your crippling alchoholism.",
    0x0043: "\x08\x13\x15You got a \x05\x41Red Potion\x05\x40!\x01I was just following orders.",
    0x0044: "\x08\x13\x16You got a \x05\x42Green Potion\x05\x40!\x01e621.net",
    0x0045: "\x08\x13\x17You got a \x05\x43Blue Potion\x05\x40!\x01Stop! Stop!\x01He's already dead...",
    0x0046: "\x08\x13\x18You caught a \x05\x41Fairy\x05\x40 in a bottle!\x01This is an executive decision.",
    0x0047: "\x08\x13\x19You got a \x05\x41Fish\x05\x40!\x01I can fit an entire mango in my ass.",
    0x0048: "\x08\x13\x10You got a \x05\x41Magic Bean\x05\x40!\x01A fun theater snack",
    0x9048: "\x08\x13\x10You got a \x05\x41Pack of Magic Beans\x05\x40!\x01Packed for movie theater\x01convenience.",
    0x004A: "\x08\x13\x07You received the\x01\x05\x41Reverse Rape Whistle\x05\x40!\x01Use it for a good time.",
    0x004B: "\x08\x13\x3DYou got the \x05\x42Diet Moron Sword\x05\x40!\x01No, it's not the good one.",
    0x004C: "\x08\x13\x3EYou got a \x05\x44Naruto Shield\x05\x40!",
    0x004D: "\x08\x13\x3FLoli and Clyde:\x01A romance novel written by\x01pedophiles, for pedophiles.",
    0x004E: "\x08\x13\x40You found the \x05\x44ISIS Banner\x05\x40!\x01Use this to oppress women\x01and freedom.",
    0x004F: "\x08\x13\x0BYou found the \x05\x41Double Cumshot\x05\x40!\x01It's an upgraded Cumshot.\x01It has \x05\x41twice\x05\x40 the volume!",
    0x0050: "\x08\x13\x42You got a \x05\x41Moron Tunic\x05\x40!\x01They're all savages so it's\x01impossible to believe they made this.",
    0x0051: "\x08\x13\x43You got a \x05\x43Fedora Tunic\x05\x40!\x01At least it's not ice arrows.",
    0x0052: "\x08\x05\x40THAT IS SOOO COOOOOL!!! :D",
    0x0053: "\x08\x13\x45You got the \x05\x41Iron Boots\x05\x40!\x01Wouldn't it be funny to know\x01what it's like to be fat?",
    0x0054: "\x08\x13\x46Why does Grunty own Egypt?",
    0x0055: "\x08You got a \x05\x45Valentine Card\x05\x40!",
    0x0056: "\x08\x13\x4BDid you know\x01every 60 seconds in Africa,\x01a minute passes.\x04\x08\x13\x48Together we can stop this.",
    0x0057: "\x08\x13\x4CIt's tail time!",
    0x0058: "\x08\x13\x4DYou found a \x05\x41Marijuana Stash\x05\x40!\x01You found \x05\x4110 Ounces\x05\x40 inside... lit!",
    0x0059: "\x08\x13\x4EYou got a \x05\x41Big Marijuana Stash\x05\x40!\x01Don't smoke it all at once!",
    0x005A: "\x08\x13\x4FYou got the \x01\x05\x41Biggest Marijuana Stash\x05\x40!",
    0x005B: "\x08\x13\x51You found the \x05\x43Silver Gauntlets\x05\x40!\x01Geno is never getting in Smash.",
    0x005C: "\x08\x13\x52You found the \x05\x43Golden Gauntlets\x05\x40!\x01Seriously, he's not getting in.",
    0x005D: "\x08\x13\x1CNote to self:\x01Don't drink tap water\x01at Jerry Garcia's.",
    0x005E: "\x08\x13\x56You got a \x05\x43Big Pay\x05\x40!\x01Now you can hold\x01up to \x05\x46200\x05\x40 \x05\x46Rupees\x05\x40.",
    0x005F: "\x08\x13\x57You got a \x05\x43Biggest Pays\x05\x40!\x01Now you can hold\x01up to \x05\x46500\x05\x40 \x05\x46Rupees\x05\x40.",
    0x0060: "\x08\x13\x77You found a \x05\x41Small Key\x05\x40!\x01Don't use it to free the Gorons.",
    0x0066: "\x08\x13\x76You found the \x05\x41Court Order Restriction\x05\x40!\x01You're no longer allowed\x01within \x05\x46500\x05\x41 meters\x04\x08\x13\x76of schools or parks.",
    0x0067: "\x08\x13\x75You found the \x05\x41Compass\x05\x40!\x04\x08\x13\x75...\x04\x08\x13\x75...\x04\x08\x13\x75...\x04\x08\x13\x75...\x04\x08\x13\x75...\x04\x08\x13\x75...\x04\x08\x13\x75...\x04\x08\x13\x75Jews did 9/11",
    0x0068: "\x08\x13\x6FI would really prefer if you'd be quiet.",
    0x0069: "\x08\x13\x23You received\x01\x05\x41Zelda's Restraining Order\x05\x40!\x01You should find a good lawyer.",
    0x006C: "\x08\x13\x49Your \x05\x41Dime Bag \x01\x05\x40has become bigger!\x01Now it's a dub!",
    0x006F: "\x08You got a \x05\x42Dollar Menu\x05\x40!\x01Great value for your dollar.",
    0x0070: "\x08\x13\x04You got the\x01\x05\x41Cherry Popsicle\x05\x40!\x01Use it to groom lolis.",
    0x0071: "\x08\x13\x0CYou got the\x01\x05\x43Blue Raspberry Popsicle\x05\x40!\x01Use it to groom shotas.",
    0x0072: "\x08\x13\x12You got the\x01\x05\x44Piss Popsicle\x05\x40!\x01You sick fuck!",
    0x0073: "\x08\x06\x28You have learned the\x01\x06\x2F\x05\x42Woodfall Wrong Warp\x05\x40!",
    0x0074: "\x08\x06\x28You have learned the\x01\x06\x37\x05\x41Snowfall Wrong Warp\x05\x40!",
    0x0075: "\x08\x06\x28You have learned the\x01\x06\x29\x05\x43Great Bay Wrong Warp\x05\x40!",
    0x0076: "\x08\x06\x28You have learned the\x01\x06\x2D\x05\x46Arbiter's Grounds\x01Wrong Warp\x05\x40!",
    0x0077: "\x08\x06\x28You have learned the\x01\x06\x28\x05\x45Ikana Canyon Wrong Warp\x05\x40!",
    0x0078: "\x08\x06\x28You have learned the\x01\x06\x32\x05\x44Unfinished Content Wrong Warp\x05\x40!",
    0x0079: "\x08\x13\x50You got the \x05\x41Moron's Bracelet\x05\x40!\x01You feel retarded but stronger.",
    0x007A: "\x08\x13\x1DYou put a \x05\x41Chinaman\x05\x40in the bottle!\x01These will help\x01destroy environments.",
    0x007B: "\x08\x13\x70You obtained the \x05\x41Al-Queda \x01Membership Card\x05\x40!\x01This directly links you to 9/11.",
    0x0080: "\x08\x13\x6CYou got the \x05\x42Chaos Emeralds\x05\x40!\x01.",
    0x0081: "\x08\x13\x6DYou obtained the \x05\x41Gorons Stole This\x05\x40!\x01It reeks of Goron filth.",
    0x0082: "\x08\x13\x6EYou obtained \x05\x43Fedora's Sapphire\x05\x40!\x01You feel euphoric!",
    0x0090: "\x08\x13\x00Now you can pick up \x01many \x05\x41Blunts\x05\x40!\x01You can carry up to \x05\x4620\x05\x40 of them!",
    0x0091: "\x08\x13\x00You can now pick up \x01even more \x05\x41Blunts\x05\x40!\x01You can carry up to \x05\x4630\x05\x40 of them!",
    0x0097: "\x08\x13\x20You caught \x05\x41Little Chungus\x05\x40 in a bottle!",
    0x0098: "\x08\x13\x1AYou got \x05\x41Pon Pon Milk\x05\x40!\x01Why aren't you listening to Pon Pon?",
    0x0099: "\x08\x13\x1BYou found \x05\x41Ruto's Fan Fiction\x05\x40\x01in a bottle!\x01HE'S MINE!! MERCO'S MINE!\x04\x08\x13\x1BSHMINE! AND NO ONE CAN HAVE HIM!\x01BWAHAHAHAHAHAHA!!!....*ahem*",
    0x9099: "\x08\x13\x1BYou found \x05\x41Ruto's Fan Fiction\x05\x40\x01in a bottle!\x01HE'S MINE!! MERCO'S MINE!\x04\x08\x13\x1BSHMINE! AND NO ONE CAN HAVE HIM!\x01BWAHAHAHAHAHAHA!!!....*ahem*",
    0x009A: "\x08\x13\x21You got a \x05\x41Vibe Egg\x05\x40!\x01Feels like there's something\x01moving inside!",
    0x00A4: "\x08\x13\x3BYou got the \x05\x42Kokiri Sword\x05\x40!\x01Use it to murder them.\x01All of them.\x04\x08\x13\x3BWho are they going to\x01tell, the Deku Tree?",
    0x00A7: "\x08\x13\x01Now you can carry\x01many \x05\x41XD\x05\x40!\x01You can hold up to \x05\x4669\x05\x40 XD!",
    0x00A8: "\x08\x13\x01You can now carry even\x01more \x05\x41XD\x05\x40! You can carry\x01up to \x05\x46420\x05\x41 \x05\x40XD!",
    0x00AD: "\x08\x13\x05You got \x05\x41Din's Feet\x05\x40!\x01Perfection!",
    0x00AE: "\x08\x13\x0DYou got \x05\x42Farore's Ass\x05\x40!\x01Nice...",
    0x00AF: "\x08\x13\x13You got \x05\x43Nayru's Tits\x05\x40!\x01Pleb taste if I say so.",
    0x00B4: "\x08You got a \x05\x41Loonie\x05\x40!\x01You've collected \x05\x41\x19\x05\x40 tokens in total.",
    0x00B5: "\x08You destroyed a \x05\x41Gold Skulltula\x05\x40.\x01You got a token proving you \x01destroyed it!", #Unused
    0x00C2: "\x08\x13\x73You got a \x05\x41Piece of Heart\x05\x40!\x01God is dead. God wemains dead.\x01And we have kiwwed him.",
    0x00C3: "\x08\x13\x73You got a \x05\x41Piece of Heart\x05\x40!\x01How shaww we comfowt ouwsewves,\x01the mwuwdewews of aww\x01mwuwdewews?",
    0x00C4: "\x08\x13\x73You got a \x05\x41Piece of Heart\x05\x40!\x01What was howiest and mwightiest\x01of aww that the wowwd\x01has owned has bwed to death\x01 undew ouw knives.",
    0x00C5: "\x08\x13\x73You got a \x05\x41Piece of Heart\x05\x40!\x01Who wiww wipe this bwood\x01off us?",
    0x00C6: "\x08\x13\x72You got a \x05\x41Heart Container\x05\x40!\x01What watew is thewe to\x01cwean ouwsewves?",
    0x00C7: "\x08\x13\x74You got the \x05\x41Boss Key\x05\x40!\x01zfg1 doesn't require this\x01but you do.",
    0x9002: "\x08\x01\x05\x43rip pogchamp\x05\x40...\x04\x08",
    0x00CC: "\x08You got \x05\x435 Dollars\x05\x40!",
    0x00CD: "\x08\x13\x53You got the \x05\x43Silver Anal Bead\x05\x40!",
    0x00CE: "\x08\x13\x54You got the \x05\x43Golden Anal Bead\x05\x40!",
    0x00D1: "\x08\x06\x14You've learned \x01\x05\x42Song of Healing Backwards\x05\x40!",
    0x00D2: "\x08\x06\x11You've learned \x05\x41Horse Cock\x05\x40!",
    0x00D3: "\x08\x06\x0BYou've learned the \x05\x46Pun Song\x05\x40!",
    0x00D4: "\x08\x06\x15POMF =3",
    0x00D5: "\x08\x06\x05It's not fun if it's voluntary.",
    0x00D6: "\x08My parents don't know\x01what to do with me.",
    0x00DC: "\x08\x13\x58Fuck you,\x04\x08\x13\x58God bless.",
    0x00DD: "\x08You mastered the secret sword\x01technique of the \x05\x41Bey Blade\x05\x40!",
    0x00E4: "\x08LIGHT PUNCH! MEDIUM PUNCH!\x01LIGHT KICK! HEAVY PUNCH!\x04\x08HOLD DIAGONAL WHICH EVER\x01WAY YOU'RE GOING!",
    0x00E5: "\x08Your \x05\x44defensive power\x05\x40 is enhanced!\x01Easy mode is now selectable.",
    0x00E6: "\x08You got a \x05\x46Useless\x05\x40!",
    0x00E8: "\x08WHAT YA DOING MOTHA FUCKER!\x01OH! OH! HOW'S IT TASTE!?\x01KEEP THE RHYTHM UP!",
    0x00E9: "\x08Your defensive power has been\x01enhanced! Easy mode is now selectable.",
    0x00F0: "\x08YOU ONLY HIT X MOTHA FUCKIN UP\x01YOU CAN'T DO IT ON THE GROUND\x01MOTHA FUCKER!\x04\x08THAT SHIT DON'T WORK!",
    0x00F1: "\x08LET'S START THIS MOTHA FUCKA OFF RIGHT!\x01AHHH! AHHH! OHHH OHH!\x01DROPPED THAT SHIT!",
    0x00F2: "\x08You got \x05\x43200 Dollars\x05\x40!\x01Just from selling one foot pic!",
    0x00F9: "\x08\x13\x1EYou put a \x05\x41Big Chungus \x05\x40in a bottle!\x01Let's sell it at the \x05\x41Chungus Shop\x05\x40!\x01Something good might happen!",
    0x9003: "\x08You found a piece of the \x05\x41Cut Content\x05\x40!",
}

KEYSANITY_MESSAGES = {
    0x001C: "\x13\x74\x08You got the \x05\x41Boss Key\x05\x40\x01for the \x05\x41Grunty's Volcano\x05\x40!\x09",
    0x0006: "\x13\x74\x08You got the \x05\x41Boss Key\x05\x40\x01for the \x05\x42Lugi's Mansion\x05\x40!\x09",
    0x001D: "\x13\x74\x08You got the \x05\x41Boss Key\x05\x40\x01for the \x05\x43Wet Dry World\x05\x40!\x09",
    0x001E: "\x13\x74\x08You got the \x05\x41Boss Key\x05\x40\x01for the \x05\x46Mosque\x05\x40!\x09",
    0x002A: "\x13\x74\x08You got the \x05\x41Boss Key\x05\x40\x01for the \x05\x45Guro Dungeon\x05\x40!\x09",
    0x0061: "\x13\x74\x08You got the \x05\x41Boss Key\x05\x40\x01for \x05\x41Gabon's Castle\x05\x40!\x09",
    0x0062: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x42Biggorn Cock Sleeve\x05\x40!\x09",
    0x0063: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for \x05\x41Dodong's Cavern\x05\x40!\x09",
    0x0064: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for \x05\x43Best Vore\x05\x40!\x09",
    0x0065: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x42Lugi's Mansion\x05\x40!\x09",
    0x007C: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x41Grunty's Volcano\x05\x40!\x09",
    0x007D: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x43Wet Dry World\x05\x40!\x09",
    0x007E: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x46Mosque\x05\x40!\x09",
    0x007F: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x45Guro Dungeon\x05\x40!\x09",
    0x0087: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x44Cirno Cavern\x05\x40!\x09",
    0x0088: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x42Biggoron Cock Sleeve\x05\x40!\x09",
    0x0089: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for \x05\x41Dodong's Cavern\x05\x40!\x09",
    0x008A: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for \x05\x43Best Vore\x05\x40!\x09",
    0x008B: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x42Lugi's Mansion\x05\x40!\x09",
    0x008C: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x41Grunty's Volcano\x05\x40!\x09",
    0x008E: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x43Wet Dry World\x05\x40!\x09",
    0x008F: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x46Mosque\x05\x40!\x09",
    0x0092: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x44Cirno Cavern\x05\x40!\x09",
    0x0093: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x42Lugi's Mansion\x05\x40!\x09",
    0x0094: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x41Grunty's Volcano\x05\x40!\x09",
    0x0095: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x43Wet Dry World\x05\x40!\x09",
    0x009B: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x45Breath of the Wild\x05\x40!\x09",
    0x009F: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x46ISIS Training Ground\x05\x40!\x09",
    0x00A0: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x46Muslim Fortress\x05\x40!\x09",
    0x00A1: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for \x05\x41Gabon's Castle\x05\x40!\x09",
    0x00A2: "\x13\x75\x08You found the \x05\x41Compass\x05\x40\x01for the \x05\x45Breath of the Wild\x05\x40!\x09",
    0x00A3: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x45Guro Dungeon\x05\x40!\x09",
    0x00A5: "\x13\x76\x08You found the \x05\x41Dungeon Map\x05\x40\x01for the \x05\x45Breath of the Wild\x05\x40!\x09",
    0x00A6: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x46Mosque\x05\x40!\x09",
    0x00A9: "\x13\x77\x08You found a \x05\x41Small Key\x05\x40\x01for the \x05\x45Guro Dungeon\x05\x40!\x09",
}

MISC_MESSAGES = {
    0x507B: (bytearray(
            b"\x08I tell you, I saw him!\x04" \
            b"\x08I saw the ghostly figure of Damp\x96\x01" \
            b"the gravekeeper sinking into\x01" \
            b"his grave. It looked like he was\x01" \
            b"holding some kind of \x05\x41treasure\x05\x40!\x02"
            ), None),
    0x0422: ("They say that once \x05\x41Morpha's Curse\x05\x40\x01is lifted, striking \x05\x42this stone\x05\x40 can\x01shift the tides of \x05\x44Lake Hylia\x05\x40.\x02", 0x23),
    0x401C: ("Please find my dear \05\x41Princess Ruto\x05\x40\x01immediately... Zora!\x12\x68\x7A", 0x23),
    0x9100: ("I am out of goods now.\x01Sorry!\x04The mark that will lead you to\x01the Spirit Temple is the \x05\x41flag on\x01the left \x05\x40outside the shop.\x01Be seeing you!\x02", 0x00)
}


# convert byte array to an integer
def bytes_to_int(bytes, signed=False):
    return int.from_bytes(bytes, byteorder='big', signed=signed)


# convert int to an array of bytes of the given width
def int_to_bytes(num, width, signed=False):
    return int.to_bytes(num, width, byteorder='big', signed=signed)


def display_code_list(codes):
    message = ""
    for code in codes:
        message += str(code)
    return message


def parse_control_codes(text):
    if isinstance(text, list):
        bytes = text
    elif isinstance(text, bytearray):
        bytes = list(text)
    else:
        bytes = list(text.encode('utf-8'))

    text_codes = []
    index = 0
    while index < len(bytes):
        next_char = bytes[index]
        data = 0
        index += 1
        if next_char in CONTROL_CODES:
            extra_bytes = CONTROL_CODES[next_char][1]
            if extra_bytes > 0:
                data = bytes_to_int(bytes[index : index + extra_bytes])
                index += extra_bytes
        text_code = Text_Code(next_char, data)
        text_codes.append(text_code)
        if text_code.code == 0x02:  # message end code
            break

    return text_codes


# holds a single character or control code of a string
class Text_Code():

    def display(self):
        if self.code in CONTROL_CODES:
            return CONTROL_CODES[self.code][2](self.data)
        elif self.code in SPECIAL_CHARACTERS:
            return SPECIAL_CHARACTERS[self.code]
        elif self.code >= 0x7F:
            return '?'
        else:
            return chr(self.code)

    def get_python_string(self):
        if self.code in CONTROL_CODES:
            ret = ''
            subdata = self.data
            for _ in range(0, CONTROL_CODES[self.code][1]):
                ret = ('\\x%02X' % (subdata & 0xFF)) + ret
                subdata = subdata >> 8
            ret = '\\x%02X' % self.code + ret
            return ret
        elif self.code in SPECIAL_CHARACTERS:
            return '\\x%02X' % self.code
        elif self.code >= 0x7F:
            return '?'
        else:
            return chr(self.code)

    def get_string(self):
        if self.code in CONTROL_CODES:
            ret = ''
            subdata = self.data
            for _ in range(0, CONTROL_CODES[self.code][1]):
                ret = chr(subdata & 0xFF) + ret
                subdata = subdata >> 8
            ret = chr(self.code) + ret
            return ret
        else:
            return chr(self.code)

    # writes the code to the given offset, and returns the offset of the next byte
    def size(self):
        size = 1
        if self.code in CONTROL_CODES:
            size += CONTROL_CODES[self.code][1]
        return size

    # writes the code to the given offset, and returns the offset of the next byte
    def write(self, rom, offset):
        rom.write_byte(TEXT_START + offset, self.code)

        extra_bytes = 0
        if self.code in CONTROL_CODES:
            extra_bytes = CONTROL_CODES[self.code][1]
            bytes_to_write = int_to_bytes(self.data, extra_bytes)
            rom.write_bytes(TEXT_START + offset + 1, bytes_to_write)

        return offset + 1 + extra_bytes

    def __init__(self, code, data):
        self.code = code
        if code in CONTROL_CODES:
            self.type = CONTROL_CODES[code][0]
        else:
            self.type = 'character'
        self.data = data

    __str__ = __repr__ = display

# holds a single message, and all its data
class Message():

    def display(self):
        meta_data = ["#" + str(self.index),
         "ID: 0x" + "{:04x}".format(self.id),
         "Offset: 0x" + "{:06x}".format(self.offset),
         "Length: 0x" + "{:04x}".format(self.unpadded_length) + "/0x" + "{:04x}".format(self.length),
         "Box Type: " + str(self.box_type),
         "Postion: " + str(self.position)]
        return ', '.join(meta_data) + '\n' + self.text

    def get_python_string(self):
        ret = ''
        for code in self.text_codes:
            ret = ret + code.get_python_string()
        return ret

    # check if this is an unused message that just contains it's own id as text
    def is_id_message(self):
        if self.unpadded_length == 5:
            for i in range(4):
                code = self.text_codes[i].code
                if not (code in range(ord('0'),ord('9')+1) or code in range(ord('A'),ord('F')+1) or code in range(ord('a'),ord('f')+1) ):
                    return False
            return True
        return False


    def parse_text(self):
        self.text_codes = parse_control_codes(self.raw_text)

        index = 0
        for text_code in self.text_codes:
            index += text_code.size()
            if text_code.code == 0x02: # message end code
                break
            if text_code.code == 0x07: # goto
                self.has_goto = True
                self.ending = text_code
            if text_code.code == 0x0A: # keep-open
                self.has_keep_open = True
                self.ending = text_code
            if text_code.code == 0x0B: # event
                self.has_event = True
                self.ending = text_code
            if text_code.code == 0x0E: # fade out
                self.has_fade = True
                self.ending = text_code
            if text_code.code == 0x10: # ocarina
                self.has_ocarina = True
                self.ending = text_code
            if text_code.code == 0x1B: # two choice
                self.has_two_choice = True
            if text_code.code == 0x1C: # three choice
                self.has_three_choice = True
        self.text = display_code_list(self.text_codes)
        self.unpadded_length = index

    def is_basic(self):
        return not (self.has_goto or self.has_keep_open or self.has_event or self.has_fade or self.has_ocarina or self.has_two_choice or self.has_three_choice)


    # computes the size of a message, including padding
    def size(self):
        size = 0

        for code in self.text_codes:
            size += code.size()

        size = (size + 3) & -4 # align to nearest 4 bytes

        return size
    
    # applies whatever transformations we want to the dialogs
    def transform(self, replace_ending=False, ending=None, always_allow_skip=True, speed_up_text=True):

        ending_codes = [0x02, 0x07, 0x0A, 0x0B, 0x0E, 0x10]
        box_breaks = [0x04, 0x0C]
        slows_text = [0x08, 0x09, 0x14]

        text_codes = []

        # # speed the text
        if speed_up_text:
            text_codes.append(Text_Code(0x08, 0)) # allow instant

        # write the message
        for code in self.text_codes:
            # ignore ending codes if it's going to be replaced
            if replace_ending and code.code in ending_codes:
                pass
            # ignore the "make unskippable flag"
            elif always_allow_skip and code.code == 0x1A:
                pass
            # ignore anything that slows down text
            elif speed_up_text and code.code in slows_text:
                pass
            elif speed_up_text and code.code in box_breaks:
                # some special cases for text that needs to be on a timer
                if (self.id == 0x605A or  # twinrova transformation
                    self.id == 0x706C or  # raru ending text
                    self.id == 0x70DD or  # ganondorf ending text
                    self.id == 0x7070):   # zelda ending text
                    text_codes.append(code)
                    text_codes.append(Text_Code(0x08, 0)) # allow instant
                else:
                    text_codes.append(Text_Code(0x04, 0)) # un-delayed break
                    text_codes.append(Text_Code(0x08, 0)) # allow instant
            else:
                text_codes.append(code)

        if replace_ending:
            if ending:
                if speed_up_text and ending.code == 0x10: # ocarina
                    text_codes.append(Text_Code(0x09, 0)) # disallow instant text
                text_codes.append(ending) # write special ending
            text_codes.append(Text_Code(0x02, 0)) # write end code

        self.text_codes = text_codes

        
    # writes a Message back into the rom, using the given index and offset to update the table
    # returns the offset of the next message
    def write(self, rom, index, offset):

        # construct the table entry
        id_bytes = int_to_bytes(self.id, 2)
        offset_bytes = int_to_bytes(offset, 3)
        entry = id_bytes + bytes([self.opts, 0x00, 0x07]) + offset_bytes
        # write it back
        entry_offset = EXTENDED_TABLE_START + 8 * index
        rom.write_bytes(entry_offset, entry)

        for code in self.text_codes:
            offset = code.write(rom, offset)

        while offset % 4 > 0:
            offset = Text_Code(0x00, 0).write(rom, offset) # pad to 4 byte align

        return offset


    def __init__(self, raw_text, index, id, opts, offset, length):

        self.raw_text = raw_text

        self.index = index
        self.id = id
        self.opts = opts  # Textbox type and y position
        self.box_type = (self.opts & 0xF0) >> 4
        self.position = (self.opts & 0x0F)
        self.offset = offset
        self.length = length

        self.has_goto = False
        self.has_keep_open = False
        self.has_event = False
        self.has_fade = False
        self.has_ocarina = False
        self.has_two_choice = False
        self.has_three_choice = False
        self.ending = None

        self.parse_text()

    # read a single message from rom
    @classmethod
    def from_rom(cls, rom, index):

        entry_offset = ENG_TABLE_START + 8 * index
        entry = rom.read_bytes(entry_offset, 8)
        next = rom.read_bytes(entry_offset + 8, 8)

        id = bytes_to_int(entry[0:2])
        opts = entry[2]
        offset = bytes_to_int(entry[5:8])
        length = bytes_to_int(next[5:8]) - offset

        raw_text = rom.read_bytes(TEXT_START + offset, length)

        return cls(raw_text, index, id, opts, offset, length)

    @classmethod
    def from_string(cls, text, id=0, opts=0x00):
        bytes = list(text.encode('utf-8')) + [0x02]

        return cls(bytes, 0, id, opts, 0, len(bytes) + 1)

    @classmethod
    def from_bytearray(cls, bytearray, id=0, opts=0x00):
        bytes = list(bytearray) + [0x02]

        return cls(bytes, 0, id, opts, 0, len(bytes) + 1)

    __str__ = __repr__ = display

# wrapper for updating the text of a message, given its message id
# if the id does not exist in the list, then it will add it
def update_message_by_id(messages, id, text, opts=None):
    # get the message index
    index = next( (m.index for m in messages if m.id == id), -1)
    # update if it was found
    if index >= 0:
        update_message_by_index(messages, index, text, opts)
    else:
        add_message(messages, text, id, opts)

# Gets the message by its ID. Returns None if the index does not exist
def get_message_by_id(messages, id):
    # get the message index
    index = next( (m.index for m in messages if m.id == id), -1)
    if index >= 0:
        return messages[index]
    else:
        return None

# wrapper for updating the text of a message, given its index in the list
def update_message_by_index(messages, index, text, opts=None):
    if opts is None:
        opts = messages[index].opts

    if isinstance(text, bytearray):
        messages[index] = Message.from_bytearray(text, messages[index].id, opts)
    else:
        messages[index] = Message.from_string(text, messages[index].id, opts)
    messages[index].index = index

# wrapper for adding a string message to a list of messages
def add_message(messages, text, id=0, opts=0x00):
    if isinstance(text, bytearray):
        messages.append( Message.from_bytearray(text, id, opts) )
    else:
        messages.append( Message.from_string(text, id, opts) )
    messages[-1].index = len(messages) - 1

# holds a row in the shop item table (which contains pointers to the description and purchase messages)
class Shop_Item():

    def display(self):
        meta_data = ["#" + str(self.index),
         "Item: 0x" + "{:04x}".format(self.get_item_id),
         "Price: " + str(self.price),
         "Amount: " + str(self.pieces),
         "Object: 0x" + "{:04x}".format(self.object),
         "Model: 0x" + "{:04x}".format(self.model),
         "Description: 0x" + "{:04x}".format(self.description_message),
         "Purchase: 0x" + "{:04x}".format(self.purchase_message),]
        func_data = [
         "func1: 0x" + "{:08x}".format(self.func1),
         "func2: 0x" + "{:08x}".format(self.func2),
         "func3: 0x" + "{:08x}".format(self.func3),
         "func4: 0x" + "{:08x}".format(self.func4),]
        return ', '.join(meta_data) + '\n' + ', '.join(func_data)

    # write the shop item back
    def write(self, rom, shop_table_address, index):

        entry_offset = shop_table_address + 0x20 * index

        bytes = []
        bytes += int_to_bytes(self.object, 2)
        bytes += int_to_bytes(self.model, 2)
        bytes += int_to_bytes(self.func1, 4)
        bytes += int_to_bytes(self.price, 2)
        bytes += int_to_bytes(self.pieces, 2)
        bytes += int_to_bytes(self.description_message, 2)
        bytes += int_to_bytes(self.purchase_message, 2)
        bytes += [0x00, 0x00]
        bytes += int_to_bytes(self.get_item_id, 2)
        bytes += int_to_bytes(self.func2, 4)
        bytes += int_to_bytes(self.func3, 4)
        bytes += int_to_bytes(self.func4, 4)

        rom.write_bytes(entry_offset, bytes)

    # read a single message
    def __init__(self, rom, shop_table_address, index):

        entry_offset = shop_table_address + 0x20 * index
        entry = rom.read_bytes(entry_offset, 0x20)

        self.index = index
        self.object = bytes_to_int(entry[0x00:0x02])
        self.model = bytes_to_int(entry[0x02:0x04])
        self.func1 = bytes_to_int(entry[0x04:0x08])
        self.price = bytes_to_int(entry[0x08:0x0A])
        self.pieces = bytes_to_int(entry[0x0A:0x0C])
        self.description_message = bytes_to_int(entry[0x0C:0x0E])
        self.purchase_message = bytes_to_int(entry[0x0E:0x10])
        # 0x10-0x11 is always 0000 padded apparently
        self.get_item_id = bytes_to_int(entry[0x12:0x14])
        self.func2 = bytes_to_int(entry[0x14:0x18])
        self.func3 = bytes_to_int(entry[0x18:0x1C])
        self.func4 = bytes_to_int(entry[0x1C:0x20])

    __str__ = __repr__ = display

# reads each of the shop items
def read_shop_items(rom, shop_table_address):
    shop_items = []

    for index in range(0, 100):
        shop_items.append( Shop_Item(rom, shop_table_address, index) )

    return shop_items

# writes each of the shop item back into rom
def write_shop_items(rom, shop_table_address, shop_items):
    for s in shop_items:
        s.write(rom, shop_table_address, s.index)

# these are unused shop items, and contain text ids that are used elsewhere, and should not be moved
SHOP_ITEM_EXCEPTIONS = [0x0A, 0x0B, 0x11, 0x12, 0x13, 0x14, 0x29]

# returns a set of all message ids used for shop items
def get_shop_message_id_set(shop_items):
    ids = set()
    for shop in shop_items:
        if shop.index not in SHOP_ITEM_EXCEPTIONS:
            ids.add(shop.description_message)
            ids.add(shop.purchase_message)
    return ids

# remove all messages that easy to tell are unused to create space in the message index table
def remove_unused_messages(messages):
    messages[:] = [m for m in messages if not m.is_id_message()]
    for index, m in enumerate(messages):
        m.index = index

# takes all messages used for shop items, and moves messages from the 00xx range into the unused 80xx range
def move_shop_item_messages(messages, shop_items):
    # checks if a message id is in the item message range
    def is_in_item_range(id):
        bytes = int_to_bytes(id, 2)
        return bytes[0] == 0x00
    # get the ids we want to move
    ids = set( id for id in get_shop_message_id_set(shop_items) if is_in_item_range(id) )
    # update them in the message list
    for id in ids:
        # should be a singleton list, but in case something funky is going on, handle it as a list regardless
        relevant_messages = [message for message in messages if message.id == id]
        if len(relevant_messages) >= 2:
            raise(TypeError("duplicate id in move_shop_item_messages"))

        for message in relevant_messages:
            message.id |= 0x8000
    # update them in the shop item list
    for shop in shop_items:
        if is_in_item_range(shop.description_message):
            shop.description_message |= 0x8000
        if is_in_item_range(shop.purchase_message):
            shop.purchase_message |= 0x8000

def make_player_message(text):
    player_text = '\x05\x42\x0F\x05\x40'
    pronoun_mapping = {
        "You have ": player_text + " ",
        "You are ":  player_text + " is ",
        "You've ":   player_text + " ",
        "Your ":     player_text + "'s ",
        "You ":      player_text + " ",

        "you have ": player_text + " ",
        "you are ":  player_text + " is ",
        "you've ":   player_text + " ",
        "your ":     player_text + "'s ",
        "you ":      player_text + " ",
    }

    verb_mapping = {
        'obtained ': 'got ',
        'received ': 'got ',
        'learned ':  'got ',
        'borrowed ': 'got ',
        'found ':    'got ',
    }

    new_text = text

    # Replace the first instance of a 'You' with the player name
    lower_text = text.lower()
    you_index = lower_text.find('you')
    if you_index != -1:
        for find_text, replace_text in pronoun_mapping.items():
            # if the index do not match, then it is not the first 'You'
            if text.find(find_text) == you_index:
                new_text = new_text.replace(find_text, replace_text, 1)
                break

    # because names are longer, we shorten the verbs to they fit in the textboxes better
    for find_text, replace_text in verb_mapping.items():
        new_text = new_text.replace(find_text, replace_text)

    wrapped_text = line_wrap(new_text, False, False, False)
    if wrapped_text != new_text:
        new_text = line_wrap(new_text, True, True, False)

    return new_text


# reduce item message sizes and add new item messages
# make sure to call this AFTER move_shop_item_messages()
def update_item_messages(messages, world):
    new_item_messages = {**ITEM_MESSAGES, **KEYSANITY_MESSAGES}
    for id, text in new_item_messages.items():
        if world.world_count > 1:
            update_message_by_id(messages, id, make_player_message(text), 0x23)
        else:
            update_message_by_id(messages, id, text, 0x23)

    for id, (text, opt) in MISC_MESSAGES.items():
        update_message_by_id(messages, id, text, opt)


# run all keysanity related patching to add messages for dungeon specific items
def add_item_messages(messages, shop_items, world):
    move_shop_item_messages(messages, shop_items)
    update_item_messages(messages, world)


# reads each of the game's messages into a list of Message objects
def read_messages(rom):
    table_offset = ENG_TABLE_START
    index = 0
    messages = []
    while True:
        entry = rom.read_bytes(table_offset, 8)
        id = bytes_to_int(entry[0:2])

        if id == 0xFFFD:
            table_offset += 8
            continue # this is only here to give an ending offset
        if id == 0xFFFF:
            break # this marks the end of the table

        messages.append( Message.from_rom(rom, index) )

        index += 1
        table_offset += 8

    return messages

# write the messages back
def repack_messages(rom, messages, permutation=None, always_allow_skip=True, speed_up_text=True):

    rom.update_dmadata_record(TEXT_START, TEXT_START, TEXT_START + ENG_TEXT_SIZE_LIMIT)

    if permutation is None:
        permutation = range(len(messages))

    # repack messages
    offset = 0
    text_size_limit = ENG_TEXT_SIZE_LIMIT

    for old_index, new_index in enumerate(permutation):
        old_message = messages[old_index]
        new_message = messages[new_index]
        remember_id = new_message.id
        new_message.id = old_message.id

        # modify message, making it represent how we want it to be written
        new_message.transform(True, old_message.ending, always_allow_skip, speed_up_text)

        # actually write the message
        offset = new_message.write(rom, old_index, offset)

        new_message.id = remember_id

    # raise an exception if too much is written
    # we raise it at the end so that we know how much overflow there is
    if offset > text_size_limit:
        raise(TypeError("Message Text table is too large: 0x" + "{:x}".format(offset) + " written / 0x" + "{:x}".format(ENG_TEXT_SIZE_LIMIT) + " allowed."))

    # end the table
    table_index = len(messages)
    entry = bytes([0xFF, 0xFD, 0x00, 0x00, 0x07]) + int_to_bytes(offset, 3)
    entry_offset = EXTENDED_TABLE_START + 8 * table_index
    rom.write_bytes(entry_offset, entry)
    table_index += 1
    entry_offset = EXTENDED_TABLE_START + 8 * table_index
    if 8 * (table_index + 1) > EXTENDED_TABLE_SIZE:
        raise(TypeError("Message ID table is too large: 0x" + "{:x}".format(8 * (table_index + 1)) + " written / 0x" + "{:x}".format(EXTENDED_TABLE_SIZE) + " allowed."))
    rom.write_bytes(entry_offset, [0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

# shuffles the messages in the game, making sure to keep various message types in their own group
def shuffle_messages(messages, except_hints=True, always_allow_skip=True):

    permutation = [i for i, _ in enumerate(messages)]

    def is_exempt(m):
        hint_ids = (
            GOSSIP_STONE_MESSAGES + TEMPLE_HINTS_MESSAGES + LIGHT_ARROW_HINT +
            list(KEYSANITY_MESSAGES.keys()) + shuffle_messages.shop_item_messages
        )
        shuffle_exempt = [
            0x208D,         # "One more lap!" for Cow in House race.
        ]
        is_hint = (except_hints and m.id in hint_ids)
        is_error_message = (m.id == ERROR_MESSAGE)
        is_shuffle_exempt = (m.id in shuffle_exempt)
        return (is_hint or is_error_message or m.is_id_message() or is_shuffle_exempt)

    have_goto         = list( filter(lambda m: not is_exempt(m) and m.has_goto,         messages) )
    have_keep_open    = list( filter(lambda m: not is_exempt(m) and m.has_keep_open,    messages) )
    have_event        = list( filter(lambda m: not is_exempt(m) and m.has_event,        messages) )
    have_fade         = list( filter(lambda m: not is_exempt(m) and m.has_fade,         messages) )
    have_ocarina      = list( filter(lambda m: not is_exempt(m) and m.has_ocarina,      messages) )
    have_two_choice   = list( filter(lambda m: not is_exempt(m) and m.has_two_choice,   messages) )
    have_three_choice = list( filter(lambda m: not is_exempt(m) and m.has_three_choice, messages) )
    basic_messages    = list( filter(lambda m: not is_exempt(m) and m.is_basic(),       messages) )


    def shuffle_group(group):
        group_permutation = [i for i, _ in enumerate(group)]
        random.shuffle(group_permutation)

        for index_from, index_to in enumerate(group_permutation):
            permutation[group[index_to].index] = group[index_from].index

    # need to use 'list' to force 'map' to actually run through
    list( map( shuffle_group, [
        have_goto + have_keep_open + have_event + have_fade + basic_messages,
        have_ocarina,
        have_two_choice,
        have_three_choice,
    ]))

    return permutation
