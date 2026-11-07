// 由 `tools/generate_entity_name_table.py` 从 `tools/entity_name_source.txt` 生成 —— **不要手改**。

#include "program/entity_name_table.hpp"

namespace isaac::runtime {
namespace {

// 名字块：每条名字后跟 `'\0'`。写法用字符串字面量拼接而不是显式字符表 ——
// 可读性差一点点，但每条名字在数组里占的字节数有确定公式（`len(名字) + 1`：
// 只有显式的分隔 `\0`）。注意相邻的字符串字面量在 C++ 里先拼接，
// 隐式结尾 `\0` 只有整串末尾一个、不是每片一个 —— 这一点算错过一次，
// 后果是第一条之外的名字下标全部偏大、`GetEntityTypeByName` 恒返回 0。
// 声明的大小 = 内容字节数 + 1：C++ 不允许丢掉字面量的隐式结尾 `\0`，
// 所以尾后多一格（内容 13313、声明 13314）。
constexpr char kEntityNameBlob[13314] = {
    "1UP\0"
    "\?\?\?\0"
    "\?\?\? (Alt)\0"
    "\?\?\?'s Only Friend\0"
    "Abel\0"
    "Abyss Locust\0"
    "Acid Baby\0"
    "Angel\0"
    "Angelic Baby\0"
    "Angelic Prism\0"
    "Angry Fly\0"
    "Anima Chain\0"
    "Attack Fly\0"
    "BBF\0"
    "Baby\0"
    "Baby Long Legs\0"
    "Baby Plum (familiar)\0"
    "Backdrop Decoration\0"
    "Background (Beast)\0"
    "Background (Death)\0"
    "Background (Famine)\0"
    "Background (Pestilence)\0"
    "Background (War)\0"
    "Bag of Crafting\0"
    "Ball of Bandages L1\0"
    "Ball of Bandages L2\0"
    "Ball of Bandages L3\0"
    "Ball of Bandages L4\0"
    "Balloon Tear\0"
    "Bar Particle\0"
    "Battery Bum\0"
    "Battery up\0"
    "Beast Rock Projectile\0"
    "Beast Soul\0"
    "Beetle\0"
    "Beggar\0"
    "Begotten\0"
    "Begotten Chain\0"
    "Belial Tear\0"
    "Best Bud\0"
    "Beths Heart\0"
    "Big Bomb\0"
    "Big Bone\0"
    "Big Chest\0"
    "Big Chubby\0"
    "Big Fan\0"
    "Big Hole\0"
    "Big Horn\0"
    "Big Horn Hand\0"
    "Big Horn Hole Helper\0"
    "Big Knife Projectile\0"
    "Big Poison Bomb\0"
    "Big Poop Nugget\0"
    "Big Rock Explosion\0"
    "Big Rock Wave\0"
    "Big Spider\0"
    "Big Water Splash\0"
    "Bird Cage\0"
    "Bishop Shield\0"
    "Black Bony\0"
    "Black Globin\0"
    "Black Globin's Body\0"
    "Black Globin's Head\0"
    "Black Heart\0"
    "Black Maw\0"
    "Black Rune\0"
    "Black Tooth Tear\0"
    "BlackHole\0"
    "BlackHoleRay\0"
    "Blastocyst\0"
    "Blastocyst Medium\0"
    "Blastocyst Small\0"
    "Blended Heart\0"
    "Blind Bat\0"
    "Blind Creep\0"
    "Blister\0"
    "Bloat Eye\0"
    "Blood Baby\0"
    "Blood Donation Machine\0"
    "Blood Drop\0"
    "Blood Explosion\0"
    "Blood Gush\0"
    "Blood Oath\0"
    "Blood Particle\0"
    "Blood Puppy\0"
    "Blood Splat\0"
    "Blood Tear\0"
    "Bloodshot Eye\0"
    "Bloody Key Tear\0"
    "Bloody Sad Bomb\0"
    "Blubber\0"
    "Blue Baby Soul\0"
    "Blue Boil\0"
    "Blue Conjoined Fatty\0"
    "Blue Fire Place\0"
    "Blue Flame\0"
    "Blue Gaper\0"
    "Blue Spider\0"
    "Bob's Brain\0"
    "Bobby Bomb\0"
    "Bobs Head Tear\0"
    "Boil\0"
    "Boiled Baby\0"
    "Bomb\0"
    "Bomb Bag\0"
    "Bomb Balloon Tear\0"
    "Bomb Bum\0"
    "Bomb Chest\0"
    "Bomb Crater\0"
    "Bomb Explosion\0"
    "Bone Club\0"
    "Bone Heart\0"
    "Bone Knight\0"
    "Bone Orbital\0"
    "Bone Scythe\0"
    "Bone Spur\0"
    "Bone Tear\0"
    "Bone Trap\0"
    "Bony\0"
    "Booger Tear\0"
    "Boom Fly\0"
    "Boomerang\0"
    "Bot Fly\0"
    "Bouncing Impact\0"
    "Box Buddy\0"
    "Brain\0"
    "Breath of Life Halo\0"
    "Brimstone Ball\0"
    "Brimstone Balloon Tear\0"
    "Brimstone Bomb\0"
    "Brimstone Head\0"
    "Brimstone Impact\0"
    "Brimstone Impact CageVis\0"
    "Brimstone Swirl\0"
    "Broken Gaping Maw\0"
    "Broken Shovel\0"
    "Broken Shovel Shadow\0"
    "Brother Bobby\0"
    "Brown Cloud\0"
    "Brown Creep\0"
    "Brown Nugget\0"
    "Brownie\0"
    "Brownie Corn\0"
    "Bullet Poof\0"
    "Bullet Poof (Static)\0"
    "Bum Fiend\0"
    "Bumbo\0"
    "Butt Bomb\0"
    "Butterfly\0"
    "Buttlicker\0"
    "C.H.A.D.\0"
    "Cain's Eye\0"
    "Camillo Jr.\0"
    "Canary\0"
    "Card Against Humanity\0"
    "Censer\0"
    "Chain Gib\0"
    "Chain Lightning\0"
    "Challenge Trophy\0"
    "Chance Card\0"
    "Chaos Card Tear\0"
    "Charged Baby\0"
    "Charged Key\0"
    "Charger\0"
    "Chest\0"
    "Chimera (body)\0"
    "Chimera (head)\0"
    "Chub\0"
    "Chubber\0"
    "Chubber Projectile\0"
    "Cleaver Slash\0"
    "Clot\0"
    "Clotty\0"
    "Clutch Orbital\0"
    "Coal\0"
    "Cod Worm\0"
    "Coin Particle\0"
    "Coin Projectile\0"
    "Coin Tear\0"
    "Collectible\0"
    "Colostomia Puddle\0"
    "Confessional\0"
    "Conjoined Fatty\0"
    "Conjoined Spitty\0"
    "Conquest\0"
    "Constant Stone Shooter\0"
    "Coplayer\0"
    "Corn\0"
    "Corn Mine\0"
    "Corn Projectile\0"
    "Couch\0"
    "Crack The Sky\0"
    "Cracked Orb Poof\0"
    "Crackwave\0"
    "Crane Game\0"
    "Crazy Long Legs\0"
    "Credit Card\0"
    "Creep (Black)\0"
    "Creep (Green)\0"
    "Creep (Red)\0"
    "Creep (Static)\0"
    "Creep (White)\0"
    "Creep (Yellow)\0"
    "Crispy\0"
    "Cross Stone Shooter\0"
    "Cross Stone Shooter (always on)\0"
    "Cross Stoney\0"
    "Cube Baby\0"
    "Cube of Meat L1\0"
    "Cube of Meat L2\0"
    "Cube of Meat L3\0"
    "Cube of Meat L4\0"
    "Curse Halo\0"
    "Cyclopia\0"
    "Daddy Long Legs\0"
    "Daddys Foot\0"
    "Damocles\0"
    "Dangle\0"
    "Dank Charger\0"
    "Dank Death's Head\0"
    "Dank Globin\0"
    "Dank Squirt\0"
    "Dark Arts Halo\0"
    "Dark Ball\0"
    "Dark Ball Smoke Particle\0"
    "Dark Bum\0"
    "Dark Esau's Pit\0"
    "Dark Matter Tear\0"
    "Dark One\0"
    "Dark Snare\0"
    "Dart Fly\0"
    "Dead Bird\0"
    "Dead Bird (permanent)\0"
    "Dead Cat\0"
    "Death\0"
    "Death Horse\0"
    "Death Scythe\0"
    "Death Skull\0"
    "Death without horse\0"
    "Death's Head\0"
    "Decap Attack\0"
    "Decoy\0"
    "Deep Gaper\0"
    "Delirium\0"
    "Demon Baby\0"
    "Depression\0"
    "Devil\0"
    "Devil Beggar\0"
    "Diamond Particle\0"
    "Diamond Tear\0"
    "Dice Room Floor\0"
    "Dice Shard\0"
    "Dime\0"
    "Dinga\0"
    "Dingle\0"
    "Dip\0"
    "Dip Familiar\0"
    "Dip Familiar (Brownie)\0"
    "Dip Familiar (black)\0"
    "Dip Familiar (corny)\0"
    "Dip Familiar (flaming)\0"
    "Dip Familiar (gold)\0"
    "Dip Familiar (rainbow)\0"
    "Dip Familiar (red)\0"
    "Dip Familiar (stinky)\0"
    "Dip Familiar (stone)\0"
    "Dip Familiar (white)\0"
    "Dirt Patch\0"
    "Dirt Pile\0"
    "Distant Admiration\0"
    "Divine Intervention\0"
    "Dogma Angel\0"
    "Dogma Angel Baby\0"
    "Dogma Blackhole\0"
    "Dogma Debris\0"
    "Dogma Orb\0"
    "Dogma's TV\0"
    "Donation Machine\0"
    "Donkey Jawbone\0"
    "Door Outline\0"
    "Dople\0"
    "Double Bomb\0"
    "Double Penny\0"
    "Double Vis\0"
    "Dr. Fetus Rocket\0"
    "Dr. Fetus Target\0"
    "Drowned Boom Fly\0"
    "Drowned Charger\0"
    "Drowned Hive\0"
    "Dry Baby\0"
    "Dukie\0"
    "Dummy\0"
    "Dust Cloud\0"
    "Egg Tear\0"
    "Ember Particle\0"
    "Embryo\0"
    "Emergency Contact\0"
    "Enemy Brimstone Swirl\0"
    "Enemy Ghost\0"
    "Enemy Soul\0"
    "Enemy Soul (Belial)\0"
    "Envy\0"
    "Envy (big)\0"
    "Envy (medium)\0"
    "Envy (small)\0"
    "Eraser Tear\0"
    "Error Room Keeper\0"
    "Esau Jr.\0"
    "Eternal Chest\0"
    "Eternal Fly\0"
    "Eves Bird Foot\0"
    "Evil Eye\0"
    "Evil Twin\0"
    "Evis Guts\0"
    "Explosion Wave\0"
    "Explosivo Tear\0"
    "Eye\0"
    "Eyeball Projectile\0"
    "Fallen Gabriel\0"
    "Fallen Uriel\0"
    "Falling Ember\0"
    "Famine\0"
    "Fart\0"
    "Fart Ring\0"
    "Farting Baby\0"
    "Fartwave\0"
    "Fat Bat\0"
    "Fat Sack\0"
    "Fate's Reward\0"
    "Fatty\0"
    "Feather Projectile\0"
    "Fetus Tear\0"
    "Finger!\0"
    "Fire\0"
    "Fire Jet\0"
    "Fire Jet (purple)\0"
    "Fire Place\0"
    "Fire Tear\0"
    "Fire Wave\0"
    "Fireworks\0"
    "Fissure Spawner\0"
    "Fist Tear\0"
    "Fistula\0"
    "Fistula Medium\0"
    "Fistula Small\0"
    "Fistuloid\0"
    "Flaming Fatty\0"
    "Flaming Gaper\0"
    "Flaming Hopper\0"
    "Flesh Death's Head\0"
    "Flesh Mobile Host\0"
    "Floating Knight\0"
    "Fly\0"
    "Fly Explosion\0"
    "Fly Orbital\0"
    "Foreigner\0"
    "Forever Alone\0"
    "Forgotten Body\0"
    "Forgotten Chain\0"
    "Forgotten Soul\0"
    "Forgotten Soul Poof\0"
    "Fortune Telling Machine\0"
    "Fred\0"
    "Freezer Baby\0"
    "Friend Zone\0"
    "Friendly ball\0"
    "Frowning Gaper\0"
    "Frozen Enemy\0"
    "Fruity Plum\0"
    "Full Fly\0"
    "Full Key\0"
    "Full Knife\0"
    "GB Bug\0"
    "Gabriel\0"
    "Gaper\0"
    "Gaping Maw\0"
    "Gazing Globin\0"
    "Gemini\0"
    "Gemini Baby\0"
    "Gemini Familiar\0"
    "Generic Prop\0"
    "Generic Tracer\0"
    "Ghost Baby\0"
    "Gideon Attract Ring\0"
    "Gideon Attract Trail\0"
    "Giga Bomb\0"
    "Giga Rocket\0"
    "Gish\0"
    "Glaucoma Blood Tear\0"
    "Glaucoma Tear\0"
    "Glitter Bomb\0"
    "Globin\0"
    "Gluttony\0"
    "God's Flesh Blood Tear\0"
    "God's Flesh Tear\0"
    "Gold Heart\0"
    "Golden Bomb\0"
    "Golden Key\0"
    "Golden Troll Bomb\0"
    "Grab Bag\0"
    "Great Gideon (defeated)\0"
    "Greed\0"
    "Greed Donation Machine\0"
    "Greed Gaper\0"
    "Grid Projectile\0"
    "Grid Projectile Helper\0"
    "Grid Tear\0"
    "Ground Glow\0"
    "Grub\0"
    "Guardian Angel\0"
    "Guillotine\0"
    "Guppys Hair Ball\0"
    "Gurdy\0"
    "Gurdy Jr.\0"
    "Gurgle\0"
    "Gurgling\0"
    "Gurgling (boss)\0"
    "Gush\0"
    "Gusher\0"
    "Gut\0"
    "Guts\0"
    "Gutted Fatty Eye\0"
    "HP up\0"
    "Haemolacria Trail\0"
    "Half Sack\0"
    "Hallowed Ground\0"
    "Halo\0"
    "Hanger\0"
    "Harlequin Baby\0"
    "Haunt\0"
    "Haunted Chest\0"
    "Head Projectile\0"
    "Headless Baby\0"
    "Headless Horseman\0"
    "Headless Horsemans Head\0"
    "Heart\0"
    "Heart (double)\0"
    "Heart (eternal)\0"
    "Heart (half soul)\0"
    "Heart (half)\0"
    "Heart (soul)\0"
    "Heart of Infamy\0"
    "Heaven Door\0"
    "Hell Game\0"
    "Heretic Pentagram\0"
    "Hive\0"
    "Holy Card\0"
    "Holy Leech\0"
    "Holy Water\0"
    "Homunculus\0"
    "Homunculus Cord\0"
    "Hopper\0"
    "Horf\0"
    "Hornfel Decoy\0"
    "Hornfel Door\0"
    "Hornfel Room Controller\0"
    "Host\0"
    "Hot Bomb\0"
    "Hungry Soul\0"
    "Hungry Tear\0"
    "Hush\0"
    "Hush (Skinless)\0"
    "Hush Ashes\0"
    "Hush Fly\0"
    "Hush Laser\0"
    "Hush Laser Up\0"
    "Hush Projectile\0"
    "Hushy\0"
    "I.Blob\0"
    "Ice Tear\0"
    "Imp\0"
    "Impact\0"
    "Incubus\0"
    "Intruder\0"
    "Isaac\0"
    "Isaac (secret)\0"
    "Isaac's Bed\0"
    "Isaac's Carpet\0"
    "Isaac's Heart\0"
    "Isaacs Body\0"
    "Isaacs Head\0"
    "It Lives\0"
    "Item Wisp Familiar\0"
    "Jaw Bone\0"
    "Juicy Sack\0"
    "Kamikaze Leech\0"
    "Keeper\0"
    "Key\0"
    "Key Bum\0"
    "Key Master\0"
    "Key Piece 1\0"
    "Key Piece 2\0"
    "Key Ring\0"
    "Key Tear\0"
    "Kineti Beam\0"
    "King Baby\0"
    "Knife Piece 1\0"
    "Knife Piece 2\0"
    "Knife Piece 3\0"
    "Knight\0"
    "Krampus\0"
    "Ladder\0"
    "Lamb Body\0"
    "Large Blood Explosion\0"
    "Larry Jr.\0"
    "Laser (Beast)\0"
    "Laser (Brimtech)\0"
    "Laser (Electric)\0"
    "Laser (Giant Brimtech)\0"
    "Laser (Giant Red)\0"
    "Laser (Light Beam)\0"
    "Laser (Pride)\0"
    "Laser (Shoop da Whoop)\0"
    "Laser (Thick Brown)\0"
    "Laser (Thick Dark)\0"
    "Laser (Thick Red)\0"
    "Laser (Thicker Brimtech)\0"
    "Laser (Thicker Red)\0"
    "Laser (Thin Red)\0"
    "Laser Impact\0"
    "Lava Projectile\0"
    "Lava Spawner\0"
    "Leaper\0"
    "Leech\0"
    "Leech Explosion\0"
    "Lemon Mishap\0"
    "Lemon Party\0"
    "Leper\0"
    "Leper (stage 2)\0"
    "Leper (stage 3)\0"
    "Leper (stage 4)\0"
    "Leper Flesh\0"
    "Leprocy\0"
    "Light\0"
    "Light Ring\0"
    "Lil Abaddon\0"
    "Lil Chest\0"
    "Lil Dumpy\0"
    "Lil Ghost\0"
    "Lil Gurdy\0"
    "Lil Harbingers\0"
    "Lil Loki\0"
    "Lil Monstro\0"
    "Lil Portal\0"
    "Lil Spewer\0"
    "Lil' Battery\0"
    "Lil' Brimstone\0"
    "Lil' Haunt\0"
    "Liquid Poop Creep\0"
    "Little C.H.A.D.\0"
    "Little Chubby\0"
    "Little Gish\0"
    "Little Horn\0"
    "Little Steve\0"
    "Locked Chest\0"
    "Loki\0"
    "Lokii\0"
    "Lost Fly\0"
    "Lost Soul\0"
    "Lucky Penny\0"
    "Lump\0"
    "Lust\0"
    "Maggot\0"
    "Maggot Explosion\0"
    "Magic Card\0"
    "Mama Gurdy\0"
    "Mama Gurdy Left Hand\0"
    "Mama Gurdy Right Hand\0"
    "Mama Guts\0"
    "Mama Mega Explosion\0"
    "Mask\0"
    "Mask of Infamy\0"
    "Maw\0"
    "Meat Projectile\0"
    "Meatball\0"
    "Mega Chest\0"
    "Mega Clotty\0"
    "Mega Fatty\0"
    "Mega Maw\0"
    "Mega Satan\0"
    "Mega Satan 2\0"
    "Mega Satan 2's Left Hand\0"
    "Mega Satan 2's Right Hand\0"
    "Mega Satan's Left Hand\0"
    "Mega Satan's Right Hand\0"
    "Megatroll Bomb\0"
    "MemBrain\0"
    "Menorah\0"
    "Metallic Tear\0"
    "Milk Puddle\0"
    "Milk!\0"
    "Mimic Chest\0"
    "Minecart\0"
    "Minisaac\0"
    "Ministro\0"
    "Mist\0"
    "Mobile Host\0"
    "Mom\0"
    "Mom Foot Stomp\0"
    "Mom Stomp\0"
    "Mom's Chest\0"
    "Mom's Dead Hand\0"
    "Mom's Dresser\0"
    "Mom's Dressing Table\0"
    "Mom's Hand\0"
    "Mom's Hand (Emergency Contact)\0"
    "Mom's Heart\0"
    "Mom's Razor\0"
    "Mom's Vanity\0"
    "Moms Guts\0"
    "Moms Knife\0"
    "Mongo Baby\0"
    "Monstrance Halo\0"
    "Monstro\0"
    "Monstro II\0"
    "Monstros Tooth\0"
    "Moter\0"
    "Mother 2\0"
    "Mother Ball\0"
    "Mother Ball (Medium)\0"
    "Mother Ball (Small)\0"
    "Mother Shockwave\0"
    "Mother Tracer\0"
    "Mother Worm\0"
    "Movable TNT\0"
    "Movable TNT (Mine Crafter)\0"
    "Moveable Blue Fireplace\0"
    "Moveable Fireplace\0"
    "Moveable Purple Fireplace\0"
    "Mr. Fred\0"
    "Mr. Maw Body\0"
    "Mr. Maw Head\0"
    "Mr. Maw Neck\0"
    "Mr. Me!\0"
    "Mr. Mega Bomb\0"
    "Mr. Mine\0"
    "Mr. Mine Neck\0"
    "Mr. Red Maw Body\0"
    "Mr. Red Maw Head\0"
    "Mulliboom\0"
    "Mulligan\0"
    "Mulligoon\0"
    "Multidimensional Baby\0"
    "Multidimensional Tear\0"
    "Mushroom\0"
    "My Shadow\0"
    "Mysterious Tear\0"
    "Mystery Egg\0"
    "Mystery Sack\0"
    "Nail Blood Tear\0"
    "Nail Particle\0"
    "Nail Tear\0"
    "Needle Tear\0"
    "Nerve Ending\0"
    "Nerve Ending 2\0"
    "Nest\0"
    "Nickel\0"
    "Night Crawler\0"
    "Notched Axe\0"
    "Nulls\0"
    "Obsessed Fan\0"
    "Occult Target\0"
    "Old Chest\0"
    "One Tooth\0"
    "Oob\0"
    "Pacer\0"
    "Pale Fatty\0"
    "Papa Fly\0"
    "Para-Bite\0"
    "Paschal Candle\0"
    "Pedestal Ripple\0"
    "Peep\0"
    "Peep Eye\0"
    "Peepers Eye\0"
    "Peepers Other Eye\0"
    "Peeping Fatty Eye\0"
    "Penny\0"
    "Pentagram (Black Powder)\0"
    "Pestilence\0"
    "Pickup Ghost\0"
    "Pill Black-Yellow\0"
    "Pill Blue-Blue\0"
    "Pill Blue-Cadetblue\0"
    "Pill Dots-Red\0"
    "Pill Dots-White\0"
    "Pill Orange-Orange\0"
    "Pill Pink-Red\0"
    "Pill White-Azure\0"
    "Pill White-Black\0"
    "Pill White-Blue\0"
    "Pill White-White\0"
    "Pill White-Yellow\0"
    "Pill Yellow-Orange\0"
    "Pin\0"
    "Pitfall\0"
    "Player\0"
    "Player Creep (Black Powder)\0"
    "Player Creep (Black)\0"
    "Player Creep (Holy Water)\0"
    "Player Creep (Red)\0"
    "Player Creep (White)\0"
    "Player Creep Holy Water Trail\0"
    "Pointy Rib\0"
    "Poison Bomb\0"
    "Poison Mind\0"
    "Poky\0"
    "Polycephalus\0"
    "Poof01\0"
    "Poof02\0"
    "Poof04\0"
    "Poop\0"
    "Poop Explosion\0"
    "Poop Nugget\0"
    "Poop Particle\0"
    "Pooter\0"
    "Pop Blood Tear\0"
    "Pop Tear\0"
    "Portal\0"
    "Portal Teleport\0"
    "Pride\0"
    "Projectile\0"
    "Psy Fly\0"
    "Psy Tumor\0"
    "Psychic Horf\0"
    "Psychic Maw\0"
    "Puke Projectile\0"
    "Pulling Effect\0"
    "Punching Bag\0"
    "Pupula Blood Tear\0"
    "Pupula Tear\0"
    "Purgatory Rift\0"
    "Purgatory Soul\0"
    "Purple Ball\0"
    "Purple Fire Place\0"
    "Purple Fire Projectile\0"
    "Quake Grimace\0"
    "Rag Man\0"
    "Rag Man's Head\0"
    "Rag Mega\0"
    "Rag Mega's Rebirth Pillar\0"
    "Rag man's Rag Ling\0"
    "Rage Creep\0"
    "Raglich Arm\0"
    "Ragling\0"
    "Rain Drop\0"
    "Rainbow Baby\0"
    "Razor Tear\0"
    "Red Boom Fly\0"
    "Red Chest\0"
    "Red Fire Place\0"
    "Red Flame\0"
    "Red Ghost\0"
    "Red Host\0"
    "Red Maw\0"
    "Redemption\0"
    "Reverse Explosion\0"
    "Reverse Explosion Debris\0"
    "Rift\0"
    "Ring Fly\0"
    "Ripple Poof\0"
    "Robo-Baby\0"
    "Robo-Baby 2.0\0"
    "Rock Explosion\0"
    "Rock Particle\0"
    "Rock Projectile\0"
    "Rock Tear\0"
    "Rock Tear Poof\0"
    "Rocket\0"
    "Rotgut (heart)\0"
    "Rotgut (maggot)\0"
    "Rotten Baby\0"
    "Rotten Beggar\0"
    "Rotty\0"
    "Round Worm\0"
    "Roundy\0"
    "Rune Bag\0"
    "Rune#1\0"
    "Rune#2\0"
    "Sack\0"
    "Sack of Pennies\0"
    "Sack of Sacks\0"
    "Sacrificial Dagger\0"
    "Sad Bomb\0"
    "Samson's Chains\0"
    "Satan\0"
    "Satan Stomp\0"
    "Saturnus Halo\0"
    "Scared Heart\0"
    "Scarred Double Vis\0"
    "Scarred Guts\0"
    "Scarred Para-Bite\0"
    "Scissors\0"
    "Scolex\0"
    "Scythe Break\0"
    "Scythe Tear\0"
    "Secret Room Keeper\0"
    "Selfless Knight\0"
    "Seraphim\0"
    "Shade\0"
    "Shell Game\0"
    "Shockwave (Directional)\0"
    "Shockwave (Radial)\0"
    "Shockwave (Random)\0"
    "Shockwave Ring\0"
    "Shockwave Trail\0"
    "Shoop Impact\0"
    "Shop Item\0"
    "Shop Restock Machine\0"
    "Shop Spikes\0"
    "Shopkeeper\0"
    "Singe's Ball\0"
    "Siren Charm Effect\0"
    "Siren Charm Glow\0"
    "Siren Helper\0"
    "Siren Helper Projectile\0"
    "Siren Minion\0"
    "Siren Ring\0"
    "Siren's Skull\0"
    "Sissy Longlegs\0"
    "Sister Maggy\0"
    "Sisters Vis\0"
    "Skinny\0"
    "Slide\0"
    "Slipped Rib\0"
    "Slippery Brown Creep\0"
    "Slippery Brown Creep (growing)\0"
    "Slot Machine\0"
    "Sloth\0"
    "Small Baby Long Legs\0"
    "Small Bomb\0"
    "Small Crazy Long Legs\0"
    "Small Hole\0"
    "Small Rocket\0"
    "Small Water Ripple\0"
    "Smart Fly\0"
    "Smoke Cloud\0"
    "Soul Sucker\0"
    "Spawner\0"
    "Spear of destiny\0"
    "Special Secret Room Keeper\0"
    "Special Shopkeeper\0"
    "Spider\0"
    "Spider Baby\0"
    "Spider Explosion\0"
    "Spider Mod\0"
    "Spidermod Text\0"
    "Spike Effect\0"
    "Spiked Chest\0"
    "Spin to Win\0"
    "Spirit Sword\0"
    "Spit\0"
    "Spitty\0"
    "Splasher\0"
    "Spore Tear\0"
    "Sprinkler\0"
    "Sprite Trail\0"
    "Squirt\0"
    "Stairway\0"
    "Stalactite\0"
    "Star of Bethlehem\0"
    "Static Halo\0"
    "Static Halo (Prerendered)\0"
    "Static Splash\0"
    "Static Splash 2\0"
    "Steven\0"
    "Steven Baby\0"
    "Steven Projectile\0"
    "Sticky Nickel\0"
    "Stitches\0"
    "Stone Eye\0"
    "Stone Grimace\0"
    "Stone Tear\0"
    "Stoney\0"
    "Succubus\0"
    "Sucker\0"
    "Suction Pitfall\0"
    "Suit Card\0"
    "Sumptorium\0"
    "Super Bum\0"
    "Super Envy\0"
    "Super Envy (big)\0"
    "Super Envy (medium)\0"
    "Super Envy (small)\0"
    "Super Gluttony\0"
    "Super Greed\0"
    "Super Lust\0"
    "Super Pooter\0"
    "Super Pride\0"
    "Super Sloth\0"
    "Super Wrath\0"
    "Swarm\0"
    "Swarm Fly Orbital\0"
    "Swarmer\0"
    "Swinger Body\0"
    "Swinger Head\0"
    "Swinger Neck\0"
    "Sword Tear\0"
    "Sworn Protector\0"
    "TV\0"
    "Tadpole\0"
    "Tainted Round Worm Butt\0"
    "Tall Ladder\0"
    "Tar Boy\0"
    "Tar Boy (mouth)\0"
    "Tar Bubble\0"
    "Tarot Card\0"
    "Tear\0"
    "Tear Creep (Green)\0"
    "Tear Poof small\0"
    "Tear Poof very small\0"
    "Tear PoofA\0"
    "Tear PoofB\0"
    "Tear Projectile\0"
    "Tech Dot\0"
    "Tech Sword\0"
    "Tech Sword Tear\0"
    "Telekinesis\tHalo\0"
    "Teleport Pitfall\0"
    "Teratoma\0"
    "Teratoma Medium\0"
    "Teratoma Small\0"
    "The Adversary\0"
    "The Blighted Ovum\0"
    "The Blighted Ovum Baby\0"
    "The Bloat\0"
    "The Cage\0"
    "The Carrion Queen\0"
    "The Duke of Flies\0"
    "The Fallen\0"
    "The Forsaken\0"
    "The Frail\0"
    "The Gate\0"
    "The Hollow\0"
    "The Husk\0"
    "The Lamb\0"
    "The Matriarch\0"
    "The Relic\0"
    "The Scourge (chain)\0"
    "The Stain\0"
    "The Thing\0"
    "The Wretched\0"
    "Thorns Halo\0"
    "Throwable Bomb\0"
    "Throwable Bomb (pickup)\0"
    "Ticking Spider\0"
    "Timer\0"
    "Tiny Bug\0"
    "Tiny Fly\0"
    "Tinytoma\0"
    "Tinytoma (small)\0"
    "Tonsil\0"
    "Tooth Particle\0"
    "Tooth Tear\0"
    "Tractor Beam\0"
    "Trap Door Cover\0"
    "Triachnid\0"
    "Trinity Shield\0"
    "Trinket\0"
    "Trite\0"
    "Troll Bomb\0"
    "Tube Worm\0"
    "Tumor\0"
    "Turdling\0"
    "Twisted Baby 1\0"
    "Twisted Baby 2\0"
    "Ulcer\0"
    "Ultra Death Head\0"
    "Ultra Death Scythe\0"
    "Ultra Famine Fly\0"
    "Ultra Greed\0"
    "Ultra Greed Bling\0"
    "Ultra Greed Coin (Bomb)\0"
    "Ultra Greed Coin (Heart)\0"
    "Ultra Greed Coin (Key)\0"
    "Ultra Greed Coin (Spinner)\0"
    "Ultra Greed Door\0"
    "Ultra Greed Footprint\0"
    "Ultra Greedier\0"
    "Ultra Pestilence Fly\0"
    "Ultra Pestilence Fly Ball\0"
    "Ultra Pestilence Maggot\0"
    "Ultra Pride\0"
    "Ultra Pride Baby\0"
    "Ultra War Bomb\0"
    "Umbilical Baby\0"
    "Umbilical Cord\0"
    "Umbilical Cord Helper\0"
    "Uriel\0"
    "Urn of Souls\0"
    "Urn of Souls (Belial)\0"
    "Vanishing Twin\0"
    "Vis\0"
    "Visage Chain\0"
    "Visage Mask\0"
    "Visage Plasma\0"
    "Vomit Grimace\0"
    "Walking Boil\0"
    "Walking Gut\0"
    "Walking Sack\0"
    "Wall Bug\0"
    "Wall Creep\0"
    "Wall Hole X-Ray\0"
    "Wall Hugger\0"
    "War\0"
    "War without horse\0"
    "Water Droplet\0"
    "Water Ripple\0"
    "Water Splash\0"
    "Whirlpool\0"
    "Whirlpool Particle\0"
    "White Fire Place\0"
    "Widow\0"
    "Willo Spawner\0"
    "Wisp\0"
    "Wisp Familiar\0"
    "Wizoob\0"
    "Womb hole teleport\0"
    "Wood Particle\0"
    "Wooden Chest\0"
    "Worm\0"
    "Worm Friend\0"
    "Worm Friend Snare\0"
    "Wormwood Hole\0"
    "Wormwood Hole Spray\0"
    "Wrath\0"
    "YO LISTEN!\0"
    "lvl2 Fly\0"
    "lvl2 Spider\0"
};

// 与名字块一一对应（`nameOffset` 是块内下标）。按名字升序 ⇒ 可以二分。
constexpr EntityNameEntry kEntityNameEntries[1028] = {
    {0, 3, 41},  // 1UP
    {4, 102, 1},  // \?\?\?
    {8, 102, 2},  // \?\?\? (Alt)
    {18, 3, 77},  // \?\?\?'s Only Friend
    {36, 3, 8},  // Abel
    {41, 3, 231},  // Abyss Locust
    {54, 3, 112},  // Acid Baby
    {64, 1000, 9},  // Angel
    {70, 38, 1},  // Angelic Baby
    {83, 3, 123},  // Angelic Prism
    {97, 3, 118},  // Angry Fly
    {107, 1000, 193},  // Anima Chain
    {119, 3, 43},  // Attack Fly
    {130, 3, 58},  // BBF
    {134, 38, 0},  // Baby
    {139, 206, 0},  // Baby Long Legs
    {154, 3, 224},  // Baby Plum (familiar)
    {175, 1000, 140},  // Backdrop Decoration
    {195, 951, 100},  // Background (Beast)
    {214, 951, 104},  // Background (Death)
    {233, 951, 101},  // Background (Famine)
    {253, 951, 102},  // Background (Pestilence)
    {277, 951, 103},  // Background (War)
    {294, 8, 4},  // Bag of Crafting
    {310, 3, 69},  // Ball of Bandages L1
    {330, 3, 70},  // Ball of Bandages L2
    {350, 3, 71},  // Ball of Bandages L3
    {370, 3, 72},  // Ball of Bandages L4
    {390, 2, 35},  // Balloon Tear
    {403, 1000, 75},  // Bar Particle
    {416, 6, 13},  // Battery Bum
    {428, 1000, 48},  // Battery up
    {439, 951, 2},  // Beast Rock Projectile
    {461, 951, 3},  // Beast Soul
    {472, 1000, 64},  // Beetle
    {479, 6, 4},  // Beggar
    {486, 251, 0},  // Begotten
    {495, 251, 10},  // Begotten Chain
    {510, 2, 32},  // Belial Tear
    {522, 3, 60},  // Best Bud
    {531, 3, 227},  // Beths Heart
    {543, 4, 1},  // Big Bomb
    {552, 830, 10},  // Big Bone
    {561, 5, 340},  // Big Chest
    {571, 3, 104},  // Big Chubby
    {582, 3, 65},  // Big Fan
    {590, 411, 2},  // Big Hole
    {599, 411, 0},  // Big Horn
    {608, 1000, 125},  // Big Horn Hand
    {622, 1000, 122},  // Big Horn Hole Helper
    {643, 1000, 182},  // Big Knife Projectile
    {664, 4, 6},  // Big Poison Bomb
    {680, 5, 42},  // Big Poop Nugget
    {696, 1000, 149},  // Big Rock Explosion
    {715, 1000, 150},  // Big Rock Wave
    {729, 94, 0},  // Big Spider
    {740, 1000, 132},  // Big Water Splash
    {757, 3, 210},  // Bird Cage
    {767, 1000, 160},  // Bishop Shield
    {781, 277, 0},  // Black Bony
    {792, 278, 0},  // Black Globin
    {805, 280, 0},  // Black Globin's Body
    {825, 279, 0},  // Black Globin's Head
    {845, 5, 10},  // Black Heart
    {857, 225, 0},  // Black Maw
    {867, 5, 300},  // Black Rune
    {878, 2, 30},  // Black Tooth Tear
    {895, 1000, 107},  // BlackHole
    {905, 1000, 107},  // BlackHoleRay
    {918, 74, 0},  // Blastocyst
    {929, 75, 0},  // Blastocyst Medium
    {947, 76, 0},  // Blastocyst Small
    {964, 5, 10},  // Blended Heart
    {978, 803, 0},  // Blind Bat
    {988, 242, 0},  // Blind Creep
    {1000, 303, 0},  // Blister
    {1008, 68, 11},  // Bloat Eye
    {1018, 3, 238},  // Blood Baby
    {1029, 6, 2},  // Blood Donation Machine
    {1052, 1000, 70},  // Blood Drop
    {1063, 1000, 2},  // Blood Explosion
    {1079, 1000, 42},  // Blood Gush
    {1090, 3, 203},  // Blood Oath
    {1101, 1000, 5},  // Blood Particle
    {1116, 3, 241},  // Blood Puppy
    {1128, 1000, 7},  // Blood Splat
    {1140, 2, 1},  // Blood Tear
    {1151, 3, 116},  // Bloodshot Eye
    {1165, 2, 44},  // Bloody Key Tear
    {1181, 4, 16},  // Bloody Sad Bomb
    {1197, 210, 0},  // Blubber
    {1205, 3, 13},  // Blue Baby Soul
    {1220, 298, 0},  // Blue Boil
    {1230, 257, 1},  // Blue Conjoined Fatty
    {1251, 33, 2},  // Blue Fire Place
    {1267, 1000, 10},  // Blue Flame
    {1278, 297, 0},  // Blue Gaper
    {1289, 3, 73},  // Blue Spider
    {1301, 3, 59},  // Bob's Brain
    {1313, 4, 11},  // Bobby Bomb
    {1324, 2, 4},  // Bobs Head Tear
    {1339, 30, 0},  // Boil
    {1344, 3, 208},  // Boiled Baby
    {1356, 4, 0},  // Bomb
    {1361, 3, 20},  // Bomb Bag
    {1370, 2, 38},  // Bomb Balloon Tear
    {1388, 6, 9},  // Bomb Bum
    {1397, 5, 51},  // Bomb Chest
    {1408, 1000, 18},  // Bomb Crater
    {1420, 1000, 1},  // Bomb Explosion
    {1435, 8, 1},  // Bone Club
    {1445, 5, 10},  // Bone Heart
    {1456, 283, 0},  // Bone Knight
    {1468, 3, 128},  // Bone Orbital
    {1481, 8, 2},  // Bone Scythe
    {1493, 3, 234},  // Bone Spur
    {1503, 2, 29},  // Bone Tear
    {1513, 885, 10},  // Bone Trap
    {1523, 227, 0},  // Bony
    {1528, 2, 26},  // Booger Tear
    {1540, 25, 0},  // Boom Fly
    {1549, 1000, 60},  // Boomerang
    {1559, 3, 218},  // Bot Fly
    {1567, 1000, 50},  // Bouncing Impact
    {1583, 3, 119},  // Box Buddy
    {1593, 32, 0},  // Brain
    {1599, 1000, 123},  // Breath of Life Halo
    {1619, 1000, 113},  // Brimstone Ball
    {1634, 2, 37},  // Brimstone Balloon Tear
    {1657, 4, 15},  // Brimstone Bomb
    {1672, 203, 0},  // Brimstone Head
    {1687, 1000, 50},  // Brimstone Impact
    {1704, 1000, 50},  // Brimstone Impact CageVis
    {1729, 1000, 71},  // Brimstone Swirl
    {1745, 236, 0},  // Broken Gaping Maw
    {1763, 5, 110},  // Broken Shovel
    {1777, 1000, 115},  // Broken Shovel Shadow
    {1798, 3, 1},  // Brother Bobby
    {1812, 1000, 105},  // Brown Cloud
    {1824, 1000, 56},  // Brown Creep
    {1836, 3, 115},  // Brown Nugget
    {1849, 402, 0},  // Brownie
    {1857, 217, 2},  // Brownie Corn
    {1870, 1000, 11},  // Bullet Poof
    {1882, 1000, 200},  // Bullet Poof (Static)
    {1903, 3, 24},  // Bum Fiend
    {1913, 3, 88},  // Bumbo
    {1919, 4, 9},  // Butt Bomb
    {1929, 1000, 69},  // Butterfly
    {1939, 89, 0},  // Buttlicker
    {1950, 28, 1},  // C.H.A.D.
    {1959, 3, 76},  // Cain's Eye
    {1970, 230, 0},  // Camillo Jr.
    {1982, 843, 0},  // Canary
    {1989, 5, 300},  // Card Against Humanity
    {2011, 3, 89},  // Censer
    {2018, 1000, 163},  // Chain Gib
    {2028, 1000, 167},  // Chain Lightning
    {2044, 5, 370},  // Challenge Trophy
    {2061, 5, 300},  // Chance Card
    {2073, 2, 9},  // Chaos Card Tear
    {2089, 3, 86},  // Charged Baby
    {2102, 5, 30},  // Charged Key
    {2114, 23, 0},  // Charger
    {2122, 5, 50},  // Chest
    {2128, 910, 1},  // Chimera (body)
    {2143, 910, 2},  // Chimera (head)
    {2158, 28, 0},  // Chub
    {2163, 39, 2},  // Chubber
    {2171, 39, 22},  // Chubber Projectile
    {2190, 1000, 176},  // Cleaver Slash
    {2204, 15, 1},  // Clot
    {2209, 15, 0},  // Clotty
    {2216, 921, 1},  // Clutch Orbital
    {2231, 33, 11},  // Coal
    {2236, 221, 0},  // Cod Worm
    {2245, 1000, 98},  // Coin Particle
    {2259, 9, 7},  // Coin Projectile
    {2275, 2, 20},  // Coin Tear
    {2285, 5, 100},  // Collectible
    {2297, 1000, 168},  // Colostomia Puddle
    {2315, 6, 17},  // Confessional
    {2328, 257, 0},  // Conjoined Fatty
    {2344, 243, 0},  // Conjoined Spitty
    {2361, 65, 1},  // Conquest
    {2370, 202, 0},  // Constant Stone Shooter
    {2393, 1, 1},  // Coplayer
    {2402, 217, 1},  // Corn
    {2407, 295, 0},  // Corn Mine
    {2417, 9, 5},  // Corn Projectile
    {2433, 960, 3},  // Couch
    {2439, 1000, 19},  // Crack The Sky
    {2453, 1000, 173},  // Cracked Orb Poof
    {2470, 1000, 72},  // Crackwave
    {2480, 6, 16},  // Crane Game
    {2491, 207, 0},  // Crazy Long Legs
    {2507, 5, 300},  // Credit Card
    {2519, 1000, 26},  // Creep (Black)
    {2533, 1000, 23},  // Creep (Green)
    {2547, 1000, 22},  // Creep (Red)
    {2559, 1000, 169},  // Creep (Static)
    {2574, 1000, 25},  // Creep (White)
    {2588, 1000, 24},  // Creep (Yellow)
    {2603, 226, 2},  // Crispy
    {2610, 202, 10},  // Cross Stone Shooter
    {2630, 202, 11},  // Cross Stone Shooter (always on)
    {2662, 302, 10},  // Cross Stoney
    {2675, 3, 239},  // Cube Baby
    {2685, 3, 44},  // Cube of Meat L1
    {2701, 3, 45},  // Cube of Meat L2
    {2717, 3, 46},  // Cube of Meat L3
    {2733, 3, 47},  // Cube of Meat L4
    {2749, 1000, 123},  // Curse Halo
    {2760, 284, 0},  // Cyclopia
    {2769, 101, 0},  // Daddy Long Legs
    {2785, 3, 16},  // Daddys Foot
    {2797, 3, 202},  // Damocles
    {2806, 261, 1},  // Dangle
    {2813, 23, 2},  // Dank Charger
    {2826, 212, 1},  // Dank Death's Head
    {2844, 24, 2},  // Dank Globin
    {2856, 220, 1},  // Dank Squirt
    {2868, 1000, 123},  // Dark Arts Halo
    {2883, 404, 1},  // Dark Ball
    {2893, 1000, 88},  // Dark Ball Smoke Particle
    {2918, 3, 64},  // Dark Bum
    {2927, 866, 1},  // Dark Esau's Pit
    {2943, 2, 6},  // Dark Matter Tear
    {2960, 267, 0},  // Dark One
    {2969, 1000, 194},  // Dark Snare
    {2980, 256, 0},  // Dart Fly
    {2989, 3, 14},  // Dead Bird
    {2999, 3, 219},  // Dead Bird (permanent)
    {3021, 3, 40},  // Dead Cat
    {3030, 66, 0},  // Death
    {3036, 66, 20},  // Death Horse
    {3048, 66, 10},  // Death Scythe
    {3061, 1000, 109},  // Death Skull
    {3073, 66, 30},  // Death without horse
    {3093, 212, 0},  // Death's Head
    {3106, 3, 243},  // Decap Attack
    {3119, 4, 2},  // Decoy
    {3125, 811, 0},  // Deep Gaper
    {3136, 412, 0},  // Delirium
    {3145, 3, 2},  // Demon Baby
    {3156, 3, 105},  // Depression
    {3167, 1000, 6},  // Devil
    {3173, 6, 5},  // Devil Beggar
    {3186, 1000, 85},  // Diamond Particle
    {3203, 2, 18},  // Diamond Tear
    {3216, 1000, 76},  // Dice Room Floor
    {3232, 5, 300},  // Dice Shard
    {3243, 5, 20},  // Dime
    {3248, 223, 0},  // Dinga
    {3254, 261, 0},  // Dingle
    {3261, 217, 0},  // Dip
    {3265, 3, 201},  // Dip Familiar
    {3278, 3, 201},  // Dip Familiar (Brownie)
    {3301, 3, 201},  // Dip Familiar (black)
    {3322, 3, 201},  // Dip Familiar (corny)
    {3343, 3, 201},  // Dip Familiar (flaming)
    {3366, 3, 201},  // Dip Familiar (gold)
    {3386, 3, 201},  // Dip Familiar (rainbow)
    {3409, 3, 201},  // Dip Familiar (red)
    {3428, 3, 201},  // Dip Familiar (stinky)
    {3450, 3, 201},  // Dip Familiar (stone)
    {3471, 3, 201},  // Dip Familiar (white)
    {3492, 1000, 116},  // Dirt Patch
    {3503, 1000, 146},  // Dirt Pile
    {3513, 3, 31},  // Distant Admiration
    {3532, 1000, 188},  // Divine Intervention
    {3552, 950, 2},  // Dogma Angel
    {3564, 950, 10},  // Dogma Angel Baby
    {3581, 1000, 171},  // Dogma Blackhole
    {3597, 1000, 170},  // Dogma Debris
    {3610, 1000, 172},  // Dogma Orb
    {3620, 950, 1},  // Dogma's TV
    {3631, 6, 8},  // Donation Machine
    {3648, 8, 3},  // Donkey Jawbone
    {3663, 1000, 154},  // Door Outline
    {3676, 53, 0},  // Dople
    {3682, 5, 40},  // Double Bomb
    {3694, 5, 20},  // Double Penny
    {3707, 39, 1},  // Double Vis
    {3718, 1000, 31},  // Dr. Fetus Rocket
    {3735, 1000, 30},  // Dr. Fetus Target
    {3752, 25, 2},  // Drowned Boom Fly
    {3769, 23, 1},  // Drowned Charger
    {3785, 22, 1},  // Drowned Hive
    {3798, 3, 51},  // Dry Baby
    {3807, 288, 0},  // Dukie
    {3813, 964, 0},  // Dummy
    {3819, 1000, 59},  // Dust Cloud
    {3830, 2, 27},  // Egg Tear
    {3839, 1000, 66},  // Ember Particle
    {3854, 77, 0},  // Embryo
    {3861, 5, 300},  // Emergency Contact
    {3879, 1000, 110},  // Enemy Brimstone Swirl
    {3901, 1000, 144},  // Enemy Ghost
    {3913, 1000, 179},  // Enemy Soul
    {3924, 1000, 179},  // Enemy Soul (Belial)
    {3944, 51, 0},  // Envy
    {3949, 51, 10},  // Envy (big)
    {3960, 51, 20},  // Envy (medium)
    {3974, 51, 30},  // Envy (small)
    {3987, 2, 45},  // Eraser Tear
    {3999, 17, 2},  // Error Room Keeper
    {4017, 3, 244},  // Esau Jr.
    {4026, 5, 53},  // Eternal Chest
    {4040, 96, 0},  // Eternal Fly
    {4052, 3, 15},  // Eves Bird Foot
    {4067, 1000, 84},  // Evil Eye
    {4076, 53, 1},  // Evil Twin
    {4086, 865, 10},  // Evis Guts
    {4096, 1000, 187},  // Explosion Wave
    {4111, 2, 19},  // Explosivo Tear
    {4126, 60, 0},  // Eye
    {4130, 9, 16},  // Eyeball Projectile
    {4149, 272, 1},  // Fallen Gabriel
    {4164, 271, 1},  // Fallen Uriel
    {4177, 1000, 87},  // Falling Ember
    {4191, 63, 0},  // Famine
    {4198, 1000, 34},  // Fart
    {4203, 1000, 106},  // Fart Ring
    {4213, 3, 95},  // Farting Baby
    {4226, 1000, 143},  // Fartwave
    {4235, 258, 0},  // Fat Bat
    {4243, 209, 0},  // Fat Sack
    {4252, 3, 81},  // Fate's Reward
    {4266, 208, 0},  // Fatty
    {4272, 9, 13},  // Feather Projectile
    {4291, 2, 50},  // Fetus Tear
    {4302, 3, 110},  // Finger!
    {4310, 1000, 51},  // Fire
    {4315, 1000, 147},  // Fire Jet
    {4324, 1000, 147},  // Fire Jet (purple)
    {4342, 33, 0},  // Fire Place
    {4353, 2, 5},  // Fire Tear
    {4363, 1000, 148},  // Fire Wave
    {4373, 1000, 104},  // Fireworks
    {4383, 1000, 192},  // Fissure Spawner
    {4399, 2, 39},  // Fist Tear
    {4409, 71, 0},  // Fistula
    {4417, 72, 0},  // Fistula Medium
    {4432, 73, 0},  // Fistula Small
    {4446, 308, 0},  // Fistuloid
    {4456, 208, 2},  // Flaming Fatty
    {4470, 10, 2},  // Flaming Gaper
    {4484, 54, 0},  // Flaming Hopper
    {4499, 286, 0},  // Flesh Death's Head
    {4518, 247, 0},  // Flesh Mobile Host
    {4536, 254, 0},  // Floating Knight
    {4552, 13, 0},  // Fly
    {4556, 1000, 3},  // Fly Explosion
    {4570, 3, 33},  // Fly Orbital
    {4582, 843, 1},  // Foreigner
    {4592, 3, 30},  // Forever Alone
    {4606, 3, 900},  // Forgotten Body
    {4621, 1000, 114},  // Forgotten Chain
    {4637, 1000, 117},  // Forgotten Soul
    {4652, 1000, 16},  // Forgotten Soul Poof
    {4672, 6, 3},  // Fortune Telling Machine
    {4696, 59, 0},  // Fred
    {4701, 3, 209},  // Freezer Baby
    {4714, 3, 84},  // Friend Zone
    {4726, 1000, 81},  // Friendly ball
    {4740, 10, 0},  // Frowning Gaper
    {4755, 963, 0},  // Frozen Enemy
    {4768, 3, 225},  // Fruity Plum
    {4780, 249, 0},  // Full Fly
    {4789, 3, 28},  // Full Key
    {4798, 3, 223},  // Full Knife
    {4809, 3, 93},  // GB Bug
    {4816, 272, 0},  // Gabriel
    {4824, 10, 1},  // Gaper
    {4830, 235, 0},  // Gaping Maw
    {4841, 24, 1},  // Gazing Globin
    {4855, 79, 0},  // Gemini
    {4862, 79, 10},  // Gemini Baby
    {4874, 3, 79},  // Gemini Familiar
    {4890, 960, 0},  // Generic Prop
    {4903, 1000, 198},  // Generic Tracer
    {4918, 3, 9},  // Ghost Baby
    {4929, 1000, 151},  // Gideon Attract Ring
    {4949, 1000, 151},  // Gideon Attract Trail
    {4970, 4, 17},  // Giga Bomb
    {4980, 4, 20},  // Giga Rocket
    {4992, 43, 1},  // Gish
    {4997, 2, 25},  // Glaucoma Blood Tear
    {5017, 2, 24},  // Glaucoma Tear
    {5031, 4, 12},  // Glitter Bomb
    {5044, 24, 0},  // Globin
    {5051, 49, 0},  // Gluttony
    {5060, 2, 17},  // God's Flesh Blood Tear
    {5083, 2, 16},  // God's Flesh Tear
    {5100, 5, 10},  // Gold Heart
    {5111, 5, 40},  // Golden Bomb
    {5123, 5, 30},  // Golden Key
    {5134, 4, 18},  // Golden Troll Bomb
    {5152, 5, 69},  // Grab Bag
    {5161, 907, 0},  // Great Gideon (defeated)
    {5185, 50, 0},  // Greed
    {5191, 6, 11},  // Greed Donation Machine
    {5214, 299, 0},  // Greed Gaper
    {5226, 9, 8},  // Grid Projectile
    {5242, 1000, 136},  // Grid Projectile Helper
    {5265, 2, 40},  // Grid Tear
    {5275, 1000, 196},  // Ground Glow
    {5287, 239, 0},  // Grub
    {5292, 3, 32},  // Guardian Angel
    {5307, 3, 68},  // Guillotine
    {5318, 3, 42},  // Guppys Hair Ball
    {5335, 36, 0},  // Gurdy
    {5341, 99, 0},  // Gurdy Jr.
    {5351, 87, 0},  // Gurgle
    {5358, 237, 0},  // Gurgling
    {5367, 237, 1},  // Gurgling (boss)
    {5383, 309, 0},  // Gush
    {5388, 11, 0},  // Gusher
    {5395, 30, 1},  // Gut
    {5399, 40, 0},  // Guts
    {5404, 831, 10},  // Gutted Fatty Eye
    {5421, 1000, 49},  // HP up
    {5427, 1000, 111},  // Haemolacria Trail
    {5445, 211, 0},  // Half Sack
    {5455, 3, 129},  // Hallowed Ground
    {5471, 1000, 123},  // Halo
    {5476, 90, 0},  // Hanger
    {5483, 3, 10},  // Harlequin Baby
    {5498, 260, 0},  // Haunt
    {5504, 5, 58},  // Haunted Chest
    {5518, 9, 15},  // Head Projectile
    {5534, 3, 55},  // Headless Baby
    {5548, 82, 0},  // Headless Horseman
    {5566, 83, 0},  // Headless Horsemans Head
    {5590, 5, 10},  // Heart
    {5596, 5, 10},  // Heart (double)
    {5611, 5, 10},  // Heart (eternal)
    {5627, 5, 10},  // Heart (half soul)
    {5645, 5, 10},  // Heart (half)
    {5658, 5, 10},  // Heart (soul)
    {5671, 98, 0},  // Heart of Infamy
    {5687, 1000, 39},  // Heaven Door
    {5699, 6, 15},  // Hell Game
    {5709, 1000, 162},  // Heretic Pentagram
    {5727, 22, 0},  // Hive
    {5732, 5, 300},  // Holy Card
    {5742, 55, 2},  // Holy Leech
    {5753, 3, 25},  // Holy Water
    {5764, 228, 0},  // Homunculus
    {5775, 228, 10},  // Homunculus Cord
    {5791, 29, 0},  // Hopper
    {5798, 12, 0},  // Horf
    {5803, 906, 1},  // Hornfel Decoy
    {5817, 967, 0},  // Hornfel Door
    {5830, 1000, 152},  // Hornfel Room Controller
    {5854, 27, 0},  // Host
    {5859, 4, 8},  // Hot Bomb
    {5868, 1000, 186},  // Hungry Soul
    {5880, 2, 36},  // Hungry Tear
    {5892, 407, 0},  // Hush
    {5897, 408, 0},  // Hush (Skinless)
    {5913, 1000, 100},  // Hush Ashes
    {5924, 296, 0},  // Hush Fly
    {5933, 1000, 96},  // Hush Laser
    {5944, 1000, 101},  // Hush Laser Up
    {5958, 9, 6},  // Hush Projectile
    {5974, 3, 107},  // Hushy
    {5980, 15, 2},  // I.Blob
    {5987, 2, 41},  // Ice Tear
    {5996, 259, 0},  // Imp
    {6000, 1000, 97},  // Impact
    {6007, 3, 80},  // Incubus
    {6015, 3, 200},  // Intruder
    {6024, 102, 0},  // Isaac
    {6030, 6, 14},  // Isaac (secret)
    {6045, 5, 380},  // Isaac's Bed
    {6057, 1000, 74},  // Isaac's Carpet
    {6072, 3, 62},  // Isaac's Heart
    {6086, 3, 48},  // Isaacs Body
    {6098, 3, 12},  // Isaacs Head
    {6110, 78, 1},  // It Lives
    {6119, 3, 237},  // Item Wisp Familiar
    {6138, 3, 130},  // Jaw Bone
    {6147, 3, 52},  // Juicy Sack
    {6158, 55, 1},  // Kamikaze Leech
    {6173, 86, 0},  // Keeper
    {6180, 5, 30},  // Key
    {6184, 3, 90},  // Key Bum
    {6192, 6, 7},  // Key Master
    {6203, 3, 26},  // Key Piece 1
    {6215, 3, 27},  // Key Piece 2
    {6227, 5, 30},  // Key Ring
    {6236, 2, 43},  // Key Tear
    {6245, 1000, 175},  // Kineti Beam
    {6257, 3, 109},  // King Baby
    {6267, 3, 213},  // Knife Piece 1
    {6281, 3, 214},  // Knife Piece 2
    {6295, 3, 215},  // Knife Piece 3
    {6309, 41, 0},  // Knight
    {6316, 81, 1},  // Krampus
    {6324, 1000, 8},  // Ladder
    {6331, 273, 10},  // Lamb Body
    {6341, 1000, 77},  // Large Blood Explosion
    {6363, 19, 0},  // Larry Jr.
    {6373, 7, 13},  // Laser (Beast)
    {6387, 7, 9},  // Laser (Brimtech)
    {6404, 7, 10},  // Laser (Electric)
    {6421, 7, 15},  // Laser (Giant Brimtech)
    {6444, 7, 6},  // Laser (Giant Red)
    {6462, 7, 5},  // Laser (Light Beam)
    {6481, 7, 4},  // Laser (Pride)
    {6495, 7, 3},  // Laser (Shoop da Whoop)
    {6518, 7, 12},  // Laser (Thick Brown)
    {6538, 7, 1},  // Laser (Thick Dark)
    {6557, 7, 1},  // Laser (Thick Red)
    {6575, 7, 14},  // Laser (Thicker Brimtech)
    {6600, 7, 11},  // Laser (Thicker Red)
    {6620, 7, 2},  // Laser (Thin Red)
    {6637, 1000, 50},  // Laser Impact
    {6650, 9, 14},  // Lava Projectile
    {6666, 1000, 181},  // Lava Spawner
    {6679, 34, 0},  // Leaper
    {6686, 3, 56},  // Leech
    {6692, 1000, 130},  // Leech Explosion
    {6708, 1000, 32},  // Lemon Mishap
    {6721, 1000, 78},  // Lemon Party
    {6733, 310, 0},  // Leper
    {6739, 310, 0},  // Leper (stage 2)
    {6755, 310, 0},  // Leper (stage 3)
    {6771, 310, 0},  // Leper (stage 4)
    {6787, 310, 1},  // Leper Flesh
    {6799, 3, 121},  // Leprocy
    {6807, 1000, 121},  // Light
    {6813, 7, 8},  // Light Ring
    {6824, 3, 230},  // Lil Abaddon
    {6836, 3, 82},  // Lil Chest
    {6846, 3, 212},  // Lil Dumpy
    {6856, 1000, 159},  // Lil Ghost
    {6866, 3, 87},  // Lil Gurdy
    {6876, 3, 122},  // Lil Harbingers
    {6891, 3, 97},  // Lil Loki
    {6900, 3, 108},  // Lil Monstro
    {6912, 3, 232},  // Lil Portal
    {6923, 3, 125},  // Lil Spewer
    {6934, 5, 90},  // Lil' Battery
    {6947, 3, 61},  // Lil' Brimstone
    {6962, 3, 63},  // Lil' Haunt
    {6973, 1000, 195},  // Liquid Poop Creep
    {6991, 3, 22},  // Little C.H.A.D.
    {7007, 3, 3},  // Little Chubby
    {7021, 3, 4},  // Little Gish
    {7033, 404, 0},  // Little Horn
    {7045, 3, 5},  // Little Steve
    {7058, 5, 60},  // Locked Chest
    {7071, 69, 0},  // Loki
    {7076, 69, 1},  // Lokii
    {7082, 3, 85},  // Lost Fly
    {7091, 3, 211},  // Lost Soul
    {7101, 5, 20},  // Lucky Penny
    {7113, 56, 0},  // Lump
    {7118, 47, 0},  // Lust
    {7123, 21, 0},  // Maggot
    {7130, 1000, 131},  // Maggot Explosion
    {7147, 5, 300},  // Magic Card
    {7158, 266, 0},  // Mama Gurdy
    {7169, 266, 1},  // Mama Gurdy Left Hand
    {7190, 266, 2},  // Mama Gurdy Right Hand
    {7212, 57, 1},  // Mama Guts
    {7222, 1000, 127},  // Mama Mega Explosion
    {7242, 93, 0},  // Mask
    {7247, 97, 0},  // Mask of Infamy
    {7262, 26, 0},  // Maw
    {7266, 9, 11},  // Meat Projectile
    {7282, 290, 0},  // Meatball
    {7291, 5, 57},  // Mega Chest
    {7302, 282, 0},  // Mega Clotty
    {7314, 264, 0},  // Mega Fatty
    {7325, 262, 0},  // Mega Maw
    {7334, 274, 0},  // Mega Satan
    {7345, 275, 0},  // Mega Satan 2
    {7358, 275, 2},  // Mega Satan 2's Left Hand
    {7383, 275, 1},  // Mega Satan 2's Right Hand
    {7409, 274, 2},  // Mega Satan's Left Hand
    {7432, 274, 1},  // Mega Satan's Right Hand
    {7456, 4, 4},  // Megatroll Bomb
    {7471, 57, 0},  // MemBrain
    {7480, 3, 205},  // Menorah
    {7488, 2, 3},  // Metallic Tear
    {7502, 1000, 90},  // Milk Puddle
    {7514, 3, 100},  // Milk!
    {7520, 5, 54},  // Mimic Chest
    {7532, 965, 0},  // Minecart
    {7541, 3, 228},  // Minisaac
    {7550, 305, 0},  // Ministro
    {7559, 1000, 138},  // Mist
    {7564, 204, 0},  // Mobile Host
    {7576, 45, 0},  // Mom
    {7580, 1000, 29},  // Mom Foot Stomp
    {7595, 45, 10},  // Mom Stomp
    {7605, 5, 390},  // Mom's Chest
    {7617, 287, 0},  // Mom's Dead Hand
    {7633, 960, 1},  // Mom's Dresser
    {7647, 6, 12},  // Mom's Dressing Table
    {7668, 213, 0},  // Mom's Hand
    {7679, 1000, 91},  // Mom's Hand (Emergency Contact)
    {7710, 78, 0},  // Mom's Heart
    {7722, 3, 117},  // Mom's Razor
    {7734, 960, 2},  // Mom's Vanity
    {7747, 78, 10},  // Moms Guts
    {7757, 8, 0},  // Moms Knife
    {7768, 3, 74},  // Mongo Baby
    {7779, 1000, 123},  // Monstrance Halo
    {7795, 20, 0},  // Monstro
    {7803, 43, 0},  // Monstro II
    {7814, 1000, 28},  // Monstros Tooth
    {7829, 80, 0},  // Moter
    {7835, 912, 10},  // Mother 2
    {7844, 912, 100},  // Mother Ball
    {7856, 912, 100},  // Mother Ball (Medium)
    {7877, 912, 100},  // Mother Ball (Small)
    {7897, 1000, 183},  // Mother Shockwave
    {7914, 1000, 190},  // Mother Tracer
    {7928, 912, 30},  // Mother Worm
    {7940, 292, 0},  // Movable TNT
    {7952, 292, 1},  // Movable TNT (Mine Crafter)
    {7979, 33, 12},  // Moveable Blue Fireplace
    {8003, 33, 10},  // Moveable Fireplace
    {8022, 33, 13},  // Moveable Purple Fireplace
    {8048, 270, 0},  // Mr. Fred
    {8057, 35, 0},  // Mr. Maw Body
    {8070, 35, 1},  // Mr. Maw Head
    {8083, 35, 10},  // Mr. Maw Neck
    {8096, 1000, 108},  // Mr. Me!
    {8104, 4, 10},  // Mr. Mega Bomb
    {8118, 311, 0},  // Mr. Mine
    {8127, 311, 10},  // Mr. Mine Neck
    {8141, 35, 2},  // Mr. Red Maw Body
    {8158, 35, 3},  // Mr. Red Maw Head
    {8175, 16, 2},  // Mulliboom
    {8185, 16, 0},  // Mulligan
    {8194, 16, 1},  // Mulligoon
    {8204, 3, 101},  // Multidimensional Baby
    {8226, 2, 21},  // Multidimensional Tear
    {8248, 300, 0},  // Mushroom
    {8257, 23, 0},  // My Shadow
    {8267, 2, 7},  // Mysterious Tear
    {8283, 3, 124},  // Mystery Egg
    {8295, 3, 57},  // Mystery Sack
    {8308, 2, 23},  // Nail Blood Tear
    {8324, 1000, 86},  // Nail Particle
    {8338, 2, 13},  // Nail Tear
    {8348, 2, 31},  // Needle Tear
    {8360, 231, 0},  // Nerve Ending
    {8373, 231, 1},  // Nerve Ending 2
    {8388, 205, 0},  // Nest
    {8393, 5, 20},  // Nickel
    {8400, 255, 0},  // Night Crawler
    {8414, 8, 9},  // Notched Axe
    {8426, 252, 0},  // Nulls
    {8432, 3, 98},  // Obsessed Fan
    {8445, 1000, 153},  // Occult Target
    {8459, 5, 55},  // Old Chest
    {8469, 234, 0},  // One Tooth
    {8479, 224, 0},  // Oob
    {8483, 11, 1},  // Pacer
    {8489, 208, 1},  // Pale Fatty
    {8500, 3, 99},  // Papa Fly
    {8509, 58, 0},  // Para-Bite
    {8519, 3, 221},  // Paschal Candle
    {8534, 1000, 134},  // Pedestal Ripple
    {8550, 68, 0},  // Peep
    {8555, 68, 10},  // Peep Eye
    {8564, 3, 17},  // Peepers Eye
    {8576, 3, 207},  // Peepers Other Eye
    {8594, 835, 10},  // Peeping Fatty Eye
    {8612, 5, 20},  // Penny
    {8618, 1000, 93},  // Pentagram (Black Powder)
    {8643, 64, 0},  // Pestilence
    {8654, 1000, 191},  // Pickup Ghost
    {8667, 5, 70},  // Pill Black-Yellow
    {8685, 5, 70},  // Pill Blue-Blue
    {8700, 5, 70},  // Pill Blue-Cadetblue
    {8720, 5, 70},  // Pill Dots-Red
    {8734, 5, 70},  // Pill Dots-White
    {8750, 5, 70},  // Pill Orange-Orange
    {8769, 5, 70},  // Pill Pink-Red
    {8783, 5, 70},  // Pill White-Azure
    {8800, 5, 70},  // Pill White-Black
    {8817, 5, 70},  // Pill White-Blue
    {8833, 5, 70},  // Pill White-White
    {8850, 5, 70},  // Pill White-Yellow
    {8868, 5, 70},  // Pill Yellow-Orange
    {8887, 62, 0},  // Pin
    {8891, 291, 0},  // Pitfall
    {8899, 1, 0},  // Player
    {8906, 1000, 92},  // Player Creep (Black Powder)
    {8934, 1000, 45},  // Player Creep (Black)
    {8955, 1000, 37},  // Player Creep (Holy Water)
    {8981, 1000, 46},  // Player Creep (Red)
    {9000, 1000, 44},  // Player Creep (White)
    {9021, 1000, 54},  // Player Creep Holy Water Trail
    {9051, 3, 127},  // Pointy Rib
    {9062, 4, 5},  // Poison Bomb
    {9074, 301, 0},  // Poison Mind
    {9086, 44, 0},  // Poky
    {9091, 269, 0},  // Polycephalus
    {9104, 1000, 15},  // Poof01
    {9111, 1000, 16},  // Poof02
    {9118, 1000, 17},  // Poof04
    {9125, 245, 0},  // Poop
    {9130, 1000, 43},  // Poop Explosion
    {9145, 5, 42},  // Poop Nugget
    {9157, 1000, 58},  // Poop Particle
    {9171, 14, 0},  // Pooter
    {9178, 2, 34},  // Pop Blood Tear
    {9193, 2, 33},  // Pop Tear
    {9202, 306, 0},  // Portal
    {9209, 1000, 161},  // Portal Teleport
    {9225, 52, 0},  // Pride
    {9231, 9, 0},  // Projectile
    {9242, 3, 204},  // Psy Fly
    {9250, 253, 0},  // Psy Tumor
    {9260, 248, 0},  // Psychic Horf
    {9273, 26, 2},  // Psychic Maw
    {9285, 9, 3},  // Puke Projectile
    {9301, 1000, 57},  // Pulling Effect
    {9316, 3, 67},  // Punching Bag
    {9329, 2, 15},  // Pupula Blood Tear
    {9347, 2, 14},  // Pupula Tear
    {9359, 1000, 189},  // Purgatory Rift
    {9374, 1000, 189},  // Purgatory Soul
    {9389, 409, 1},  // Purple Ball
    {9401, 33, 3},  // Purple Fire Place
    {9419, 9, 2},  // Purple Fire Projectile
    {9442, 804, 0},  // Quake Grimace
    {9456, 405, 0},  // Rag Man
    {9464, 405, 1},  // Rag Man's Head
    {9479, 409, 0},  // Rag Mega
    {9488, 409, 2},  // Rag Mega's Rebirth Pillar
    {9514, 246, 1},  // Rag man's Rag Ling
    {9533, 241, 0},  // Rage Creep
    {9544, 919, 1},  // Raglich Arm
    {9556, 246, 0},  // Ragling
    {9564, 1000, 135},  // Rain Drop
    {9574, 3, 11},  // Rainbow Baby
    {9587, 2, 28},  // Razor Tear
    {9598, 25, 1},  // Red Boom Fly
    {9611, 5, 360},  // Red Chest
    {9621, 33, 1},  // Red Fire Place
    {9636, 1000, 52},  // Red Flame
    {9646, 285, 0},  // Red Ghost
    {9656, 27, 1},  // Red Host
    {9665, 26, 1},  // Red Maw
    {9673, 1000, 185},  // Redemption
    {9684, 1000, 177},  // Reverse Explosion
    {9702, 1000, 177},  // Reverse Explosion Debris
    {9727, 1000, 180},  // Rift
    {9732, 222, 0},  // Ring Fly
    {9741, 1000, 14},  // Ripple Poof
    {9753, 3, 6},  // Robo-Baby
    {9763, 3, 53},  // Robo-Baby 2.0
    {9777, 1000, 62},  // Rock Explosion
    {9792, 1000, 4},  // Rock Particle
    {9806, 9, 9},  // Rock Projectile
    {9822, 2, 42},  // Rock Tear
    {9832, 1000, 145},  // Rock Tear Poof
    {9847, 4, 19},  // Rocket
    {9854, 911, 2},  // Rotgut (heart)
    {9869, 911, 1},  // Rotgut (maggot)
    {9885, 3, 54},  // Rotten Baby
    {9897, 6, 18},  // Rotten Beggar
    {9911, 226, 1},  // Rotty
    {9917, 244, 0},  // Round Worm
    {9928, 276, 0},  // Roundy
    {9935, 3, 91},  // Rune Bag
    {9944, 5, 300},  // Rune#1
    {9951, 5, 300},  // Rune#2
    {9958, 30, 2},  // Sack
    {9963, 3, 21},  // Sack of Pennies
    {9979, 3, 114},  // Sack of Sacks
    {9993, 3, 35},  // Sacrificial Dagger
    {10012, 4, 7},  // Sad Bomb
    {10021, 3, 75},  // Samson's Chains
    {10037, 84, 0},  // Satan
    {10043, 84, 10},  // Satan Stomp
    {10055, 1000, 123},  // Saturnus Halo
    {10069, 5, 10},  // Scared Heart
    {10082, 39, 3},  // Scarred Double Vis
    {10101, 40, 1},  // Scarred Guts
    {10114, 58, 1},  // Scarred Para-Bite
    {10132, 3, 78},  // Scissors
    {10141, 62, 1},  // Scolex
    {10148, 1000, 20},  // Scythe Break
    {10161, 2, 8},  // Scythe Tear
    {10173, 17, 1},  // Secret Room Keeper
    {10192, 41, 1},  // Selfless Knight
    {10208, 3, 92},  // Seraphim
    {10217, 3, 106},  // Shade
    {10223, 6, 6},  // Shell Game
    {10234, 1000, 67},  // Shockwave (Directional)
    {10258, 1000, 61},  // Shockwave (Radial)
    {10277, 1000, 73},  // Shockwave (Random)
    {10296, 1000, 151},  // Shockwave Ring
    {10311, 1000, 151},  // Shockwave Trail
    {10327, 1000, 50},  // Shoop Impact
    {10340, 5, 150},  // Shop Item
    {10350, 6, 10},  // Shop Restock Machine
    {10371, 1000, 174},  // Shop Spikes
    {10383, 17, 0},  // Shopkeeper
    {10394, 915, 1},  // Singe's Ball
    {10407, 1000, 165},  // Siren Charm Effect
    {10426, 1000, 165},  // Siren Charm Glow
    {10443, 966, 0},  // Siren Helper
    {10456, 904, 10},  // Siren Helper Projectile
    {10480, 3, 220},  // Siren Minion
    {10493, 1000, 164},  // Siren Ring
    {10504, 904, 1},  // Siren's Skull
    {10518, 3, 66},  // Sissy Longlegs
    {10533, 3, 7},  // Sister Maggy
    {10546, 410, 0},  // Sisters Vis
    {10558, 226, 0},  // Skinny
    {10565, 44, 1},  // Slide
    {10571, 3, 126},  // Slipped Rib
    {10583, 1000, 94},  // Slippery Brown Creep
    {10604, 1000, 155},  // Slippery Brown Creep (growing)
    {10635, 6, 1},  // Slot Machine
    {10648, 46, 0},  // Sloth
    {10654, 206, 1},  // Small Baby Long Legs
    {10675, 4, 14},  // Small Bomb
    {10686, 207, 1},  // Small Crazy Long Legs
    {10708, 411, 1},  // Small Hole
    {10719, 1000, 118},  // Small Rocket
    {10732, 1000, 133},  // Small Water Ripple
    {10751, 3, 50},  // Smart Fly
    {10761, 1000, 141},  // Smoke Cloud
    {10773, 61, 2},  // Soul Sucker
    {10785, 1000, 120},  // Spawner
    {10793, 1000, 83},  // Spear of destiny
    {10810, 17, 4},  // Special Secret Room Keeper
    {10837, 17, 3},  // Special Shopkeeper
    {10856, 85, 0},  // Spider
    {10863, 3, 113},  // Spider Baby
    {10875, 1000, 38},  // Spider Explosion
    {10892, 3, 94},  // Spider Mod
    {10903, 9001, 1},  // Spidermod Text
    {10918, 1000, 55},  // Spike Effect
    {10931, 5, 52},  // Spiked Chest
    {10944, 3, 226},  // Spin to Win
    {10956, 8, 10},  // Spirit Sword
    {10969, 61, 1},  // Spit
    {10974, 31, 0},  // Spitty
    {10981, 238, 0},  // Splasher
    {10990, 2, 48},  // Spore Tear
    {11001, 3, 120},  // Sprinkler
    {11011, 1000, 166},  // Sprite Trail
    {11024, 220, 0},  // Squirt
    {11031, 1000, 156},  // Stairway
    {11040, 951, 1},  // Stalactite
    {11051, 3, 236},  // Star of Bethlehem
    {11069, 1000, 123},  // Static Halo
    {11081, 1000, 123},  // Static Halo (Prerendered)
    {11107, 1000, 132},  // Static Splash
    {11121, 1000, 132},  // Static Splash 2
    {11137, 79, 1},  // Steven
    {11144, 79, 11},  // Steven Baby
    {11156, 9, 12},  // Steven Projectile
    {11174, 5, 20},  // Sticky Nickel
    {11188, 3, 222},  // Stitches
    {11197, 201, 0},  // Stone Eye
    {11207, 42, 0},  // Stone Grimace
    {11221, 2, 22},  // Stone Tear
    {11232, 302, 0},  // Stoney
    {11239, 3, 96},  // Succubus
    {11248, 61, 0},  // Sucker
    {11255, 291, 1},  // Suction Pitfall
    {11271, 5, 300},  // Suit Card
    {11281, 8, 5},  // Sumptorium
    {11292, 3, 102},  // Super Bum
    {11302, 51, 1},  // Super Envy
    {11313, 51, 11},  // Super Envy (big)
    {11330, 51, 21},  // Super Envy (medium)
    {11350, 51, 31},  // Super Envy (small)
    {11369, 49, 1},  // Super Gluttony
    {11384, 50, 1},  // Super Greed
    {11396, 47, 1},  // Super Lust
    {11407, 14, 1},  // Super Pooter
    {11420, 52, 1},  // Super Pride
    {11432, 46, 1},  // Super Sloth
    {11444, 48, 1},  // Super Wrath
    {11456, 281, 0},  // Swarm
    {11462, 3, 229},  // Swarm Fly Orbital
    {11480, 91, 0},  // Swarmer
    {11488, 216, 0},  // Swinger Body
    {11501, 216, 1},  // Swinger Head
    {11514, 216, 10},  // Swinger Neck
    {11527, 2, 47},  // Sword Tear
    {11538, 3, 83},  // Sworn Protector
    {11554, 960, 4},  // TV
    {11557, 1000, 158},  // Tadpole
    {11565, 244, 2},  // Tainted Round Worm Butt
    {11589, 1000, 156},  // Tall Ladder
    {11601, 307, 0},  // Tar Boy
    {11609, 307, 0},  // Tar Boy (mouth)
    {11625, 1000, 124},  // Tar Bubble
    {11636, 5, 300},  // Tarot Card
    {11647, 2, 0},  // Tear
    {11652, 1000, 53},  // Tear Creep (Green)
    {11671, 1000, 79},  // Tear Poof small
    {11687, 1000, 80},  // Tear Poof very small
    {11708, 1000, 12},  // Tear PoofA
    {11719, 1000, 13},  // Tear PoofB
    {11730, 9, 4},  // Tear Projectile
    {11746, 1000, 126},  // Tech Dot
    {11755, 8, 11},  // Tech Sword
    {11766, 2, 49},  // Tech Sword Tear
    {11782, 1000, 123},  // Telekinesis\tHalo
    {11799, 291, 2},  // Teleport Pitfall
    {11816, 71, 1},  // Teratoma
    {11825, 72, 1},  // Teratoma Medium
    {11841, 73, 1},  // Teratoma Small
    {11856, 268, 0},  // The Adversary
    {11870, 79, 2},  // The Blighted Ovum
    {11888, 79, 12},  // The Blighted Ovum Baby
    {11911, 68, 1},  // The Bloat
    {11921, 265, 0},  // The Cage
    {11930, 28, 2},  // The Carrion Queen
    {11948, 67, 0},  // The Duke of Flies
    {11966, 81, 0},  // The Fallen
    {11977, 403, 0},  // The Forsaken
    {11990, 62, 2},  // The Frail
    {12000, 263, 0},  // The Gate
    {12009, 19, 1},  // The Hollow
    {12020, 67, 1},  // The Husk
    {12029, 273, 0},  // The Lamb
    {12038, 413, 0},  // The Matriarch
    {12052, 3, 23},  // The Relic
    {12062, 909, 10},  // The Scourge (chain)
    {12082, 401, 0},  // The Stain
    {12092, 304, 0},  // The Thing
    {12102, 100, 1},  // The Wretched
    {12115, 1000, 123},  // Thorns Halo
    {12127, 4, 13},  // Throwable Bomb
    {12142, 5, 41},  // Throwable Bomb (pickup)
    {12166, 250, 0},  // Ticking Spider
    {12181, 1000, 119},  // Timer
    {12187, 1000, 21},  // Tiny Bug
    {12196, 1000, 33},  // Tiny Fly
    {12205, 3, 216},  // Tinytoma
    {12214, 3, 217},  // Tinytoma (small)
    {12231, 3, 103},  // Tonsil
    {12238, 1000, 35},  // Tooth Particle
    {12253, 2, 2},  // Tooth Tear
    {12264, 7, 7},  // Tractor Beam
    {12277, 1000, 139},  // Trap Door Cover
    {12293, 101, 1},  // Triachnid
    {12303, 1000, 47},  // Trinity Shield
    {12318, 5, 350},  // Trinket
    {12326, 29, 1},  // Trite
    {12332, 4, 3},  // Troll Bomb
    {12343, 244, 1},  // Tube Worm
    {12353, 229, 0},  // Tumor
    {12359, 237, 2},  // Turdling
    {12368, 3, 235},  // Twisted Baby 1
    {12383, 3, 235},  // Twisted Baby 2
    {12398, 289, 0},  // Ulcer
    {12404, 951, 42},  // Ultra Death Head
    {12421, 951, 41},  // Ultra Death Scythe
    {12440, 951, 11},  // Ultra Famine Fly
    {12457, 406, 0},  // Ultra Greed
    {12469, 1000, 103},  // Ultra Greed Bling
    {12487, 293, 2},  // Ultra Greed Coin (Bomb)
    {12511, 293, 3},  // Ultra Greed Coin (Heart)
    {12536, 293, 1},  // Ultra Greed Coin (Key)
    {12559, 293, 0},  // Ultra Greed Coin (Spinner)
    {12586, 294, 0},  // Ultra Greed Door
    {12603, 1000, 89},  // Ultra Greed Footprint
    {12625, 406, 1},  // Ultra Greedier
    {12640, 951, 21},  // Ultra Pestilence Fly
    {12661, 951, 23},  // Ultra Pestilence Fly Ball
    {12687, 951, 22},  // Ultra Pestilence Maggot
    {12711, 46, 2},  // Ultra Pride
    {12723, 38, 2},  // Ultra Pride Baby
    {12740, 951, 31},  // Ultra War Bomb
    {12755, 3, 240},  // Umbilical Baby
    {12770, 79, 20},  // Umbilical Cord
    {12785, 1000, 201},  // Umbilical Cord Helper
    {12807, 271, 0},  // Uriel
    {12813, 1000, 178},  // Urn of Souls
    {12826, 1000, 178},  // Urn of Souls (Belial)
    {12848, 3, 242},  // Vanishing Twin
    {12863, 39, 0},  // Vis
    {12867, 903, 10},  // Visage Chain
    {12880, 903, 1},  // Visage Mask
    {12892, 903, 20},  // Visage Plasma
    {12906, 42, 1},  // Vomit Grimace
    {12920, 88, 0},  // Walking Boil
    {12933, 88, 1},  // Walking Gut
    {12945, 88, 2},  // Walking Sack
    {12958, 1000, 68},  // Wall Bug
    {12967, 240, 0},  // Wall Creep
    {12978, 1000, 36},  // Wall Hole X-Ray
    {12994, 218, 0},  // Wall Hugger
    {13006, 65, 0},  // War
    {13010, 65, 10},  // War without horse
    {13028, 1000, 41},  // Water Droplet
    {13042, 1000, 133},  // Water Ripple
    {13055, 1000, 99},  // Water Splash
    {13068, 1000, 142},  // Whirlpool
    {13078, 1000, 142},  // Whirlpool Particle
    {13097, 33, 4},  // White Fire Place
    {13114, 100, 0},  // Widow
    {13120, 1000, 157},  // Willo Spawner
    {13134, 1000, 65},  // Wisp
    {13139, 3, 206},  // Wisp Familiar
    {13153, 219, 0},  // Wizoob
    {13160, 1000, 82},  // Womb hole teleport
    {13179, 1000, 27},  // Wood Particle
    {13193, 5, 56},  // Wooden Chest
    {13206, 1000, 63},  // Worm
    {13211, 3, 233},  // Worm Friend
    {13223, 1000, 184},  // Worm Friend Snare
    {13241, 1000, 137},  // Wormwood Hole
    {13255, 1000, 137},  // Wormwood Hole Spray
    {13275, 48, 0},  // Wrath
    {13281, 3, 111},  // YO LISTEN!
    {13292, 214, 0},  // lvl2 Fly
    {13301, 215, 0},  // lvl2 Spider
};

} // namespace

const char* EntityNameBlob() noexcept { return kEntityNameBlob; }

const EntityNameEntry* EntityNameEntries(std::size_t* count) noexcept {
    if (count != nullptr) {
        *count = sizeof(kEntityNameEntries) / sizeof(kEntityNameEntries[0]);
    }
    return kEntityNameEntries;
}

} // namespace isaac::runtime
