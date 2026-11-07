// 由 `tools/generate_isaac_name_tables.py` 从 `tools/isaac_name_source/*.txt` 生成 —— **不要手改**。

#include "program/isaac_name_tables.hpp"

#include <cstring>

namespace isaac::runtime {
namespace {

// `Isaac.GetItemIdByName` 的名字块（717 条，按名字升序）。
constexpr char kCollectibleNameBlob[8317] = {
    "120 Volt\0"
    "1up!\0"
    "20/20\0"
    "2Spooky\0"
    "3 Dollar Bill\0"
    "4.5 Volt\0"
    "7 Seals\0"
    "8 Inch Nails\0"
    "9 Volt\0"
    "<3\0"
    "\?\?\?'s Only Friend\0"
    "A Bar of Soap\0"
    "A Dollar\0"
    "A Lump of Coal\0"
    "A Pony\0"
    "A Pound of Flesh\0"
    "A Quarter\0"
    "A Snack\0"
    "Abaddon\0"
    "Abel\0"
    "Abyss\0"
    "Acid Baby\0"
    "Act of Contrition\0"
    "Adrenaline\0"
    "Akeldama\0"
    "Alabaster Box\0"
    "Almond Milk\0"
    "Analog Stick\0"
    "Anarchist Cookbook\0"
    "Anemic\0"
    "Angelic Prism\0"
    "Angry Fly\0"
    "Anima Sola\0"
    "Ankh\0"
    "Anti-Gravity\0"
    "Apple!\0"
    "Aquarius\0"
    "Aries\0"
    "Astral Projection\0"
    "Athame\0"
    "Azazel's Rage\0"
    "BBF\0"
    "BFFS!\0"
    "BOGO Bombs\0"
    "BackStabber\0"
    "Bag of Crafting\0"
    "Ball of Bandages\0"
    "Ball of Tar\0"
    "Battery Pack\0"
    "Belly Button\0"
    "Belly Jelly\0"
    "Berserk!\0"
    "Best Bud\0"
    "Best Friend\0"
    "Betrayal\0"
    "Big Chubby\0"
    "Big Fan\0"
    "Binge Eater\0"
    "Binky\0"
    "Bird Cage\0"
    "Bird's Eye\0"
    "Birthright\0"
    "Black Candle\0"
    "Black Hole\0"
    "Black Lotus\0"
    "Black Powder\0"
    "Blank Card\0"
    "Blanket\0"
    "Blood Bag\0"
    "Blood Bombs\0"
    "Blood Clot\0"
    "Blood Oath\0"
    "Blood Puppy\0"
    "Blood Rights\0"
    "Blood of the Martyr\0"
    "Bloodshot Eye\0"
    "Bloody Gust\0"
    "Bloody Lust\0"
    "Blue Cap\0"
    "Blue Map\0"
    "Bob's Brain\0"
    "Bob's Curse\0"
    "Bob's Rotten Head\0"
    "Bobby-Bomb\0"
    "Boiled Baby\0"
    "Bomb Bag\0"
    "Bomber Boy\0"
    "Bone Spurs\0"
    "Book of Revelations\0"
    "Book of Secrets\0"
    "Book of Shadows\0"
    "Book of Virtues\0"
    "Book of the Dead\0"
    "Boom!\0"
    "Booster Pack\0"
    "Bot Fly\0"
    "Box\0"
    "Box of Friends\0"
    "Box of Spiders\0"
    "Bozo\0"
    "Breakfast\0"
    "Breath of Life\0"
    "Brimstone\0"
    "Brimstone Bombs\0"
    "Brittle Bones\0"
    "Broken Modem\0"
    "Broken Shovel\0"
    "Broken Watch\0"
    "Brother Bobby\0"
    "Brown Nugget\0"
    "Bucket of Lard\0"
    "Buddy in a Box\0"
    "Bum Friend\0"
    "Bumbo\0"
    "Bursting Sack\0"
    "Butt Bombs\0"
    "Butter Bean\0"
    "C Section\0"
    "Caffeine Pill\0"
    "Cain's Other Eye\0"
    "Cambion Conception\0"
    "Camo Undies\0"
    "Cancer\0"
    "Candy Heart\0"
    "Capricorn\0"
    "Car Battery\0"
    "Card Reading\0"
    "Cat-o-nine-tails\0"
    "Celtic Cross\0"
    "Censer\0"
    "Ceremonial Robes\0"
    "Champion Belt\0"
    "Chaos\0"
    "Charged Baby\0"
    "Charm of the Vampire\0"
    "Chemical Peel\0"
    "Chocolate Milk\0"
    "Circle of Protection\0"
    "Clear Rune\0"
    "Clicker\0"
    "Compost\0"
    "Compound Fracture\0"
    "Cone Head\0"
    "Consolation Prize\0"
    "Contagion\0"
    "Continuum\0"
    "Contract from Below\0"
    "Converter\0"
    "Coupon\0"
    "Crack Jacks\0"
    "Crack the Sky\0"
    "Cracked Orb\0"
    "Cricket's Body\0"
    "Cricket's Head\0"
    "Crooked Penny\0"
    "Crown Of Light\0"
    "Crystal Ball\0"
    "Cube Baby\0"
    "Cube of Meat\0"
    "Cupid's Arrow\0"
    "Curse of the Tower\0"
    "Cursed Eye\0"
    "D infinity\0"
    "D1\0"
    "D10\0"
    "D100\0"
    "D12\0"
    "D20\0"
    "D4\0"
    "D7\0"
    "D8\0"
    "Dad's Key\0"
    "Dad's Lost Coin\0"
    "Dad's Note\0"
    "Dad's Ring\0"
    "Daddy Longlegs\0"
    "Damocles\0"
    "Dark Arts\0"
    "Dark Bum\0"
    "Dark Matter\0"
    "Dark Princes Crown\0"
    "Dataminer\0"
    "Dead Bird\0"
    "Dead Cat\0"
    "Dead Dove\0"
    "Dead Eye\0"
    "Dead Onion\0"
    "Dead Sea Scrolls\0"
    "Dead Tooth\0"
    "Death Certificate\0"
    "Death's List\0"
    "Death's Touch\0"
    "Decap Attack\0"
    "Deck of Cards\0"
    "Deep Pockets\0"
    "Delirious\0"
    "Demon Baby\0"
    "Depression\0"
    "Dessert\0"
    "Dinner\0"
    "Diplopia\0"
    "Dirty Mind\0"
    "Distant Admiration\0"
    "Divine Intervention\0"
    "Divorce Papers\0"
    "Doctor's Remote\0"
    "Dog Tooth\0"
    "Dogma\0"
    "Dr. Fetus\0"
    "Dream Catcher\0"
    "Dry Baby\0"
    "Duality\0"
    "Dull Razor\0"
    "E. Coli\0"
    "Echo Chamber\0"
    "Eden's Blessing\0"
    "Eden's Soul\0"
    "Empty Heart\0"
    "Empty Vessel\0"
    "Epic Fetus\0"
    "Epiphora\0"
    "Eraser\0"
    "Esau Jr.\0"
    "Eternal D6\0"
    "Eucharist\0"
    "Euthanasia\0"
    "Eve's Mascara\0"
    "Everything Jar\0"
    "Evil Charm\0"
    "Evil Eye\0"
    "Experimental Treatment\0"
    "Explosivo\0"
    "Eye Drops\0"
    "Eye Sore\0"
    "Eye of Belial\0"
    "Eye of Greed\0"
    "Eye of the Occult\0"
    "False PHD\0"
    "Fanny Pack\0"
    "Farting Baby\0"
    "Fast Bombs\0"
    "Fate\0"
    "Fate's Reward\0"
    "Finger!\0"
    "Fire Mind\0"
    "Flat Stone\0"
    "Flip\0"
    "Flush!\0"
    "Forever alone\0"
    "Forget Me Now\0"
    "Fortune Cookie\0"
    "Free Lemonade\0"
    "Freezer Baby\0"
    "Friend Finder\0"
    "Friend Zone\0"
    "Friendly Ball\0"
    "Fruit Cake\0"
    "Fruity Plum\0"
    "GB Bug\0"
    "Gello\0"
    "Gemini\0"
    "Genesis\0"
    "Ghost Baby\0"
    "Ghost Bombs\0"
    "Ghost Pepper\0"
    "Giant Cell\0"
    "Gimpy\0"
    "Glass Cannon\0"
    "Glass Eye\0"
    "Glaucoma\0"
    "Glitched Crown\0"
    "Glitter Bombs\0"
    "Glowing Hour Glass\0"
    "Glyph of Balance\0"
    "Gnawed Leaf\0"
    "Goat Head\0"
    "God's Flesh\0"
    "Godhead\0"
    "Golden Razor\0"
    "Greed's Gullet\0"
    "Growth Hormones\0"
    "Guardian Angel\0"
    "Guillotine\0"
    "Guppy's Collar\0"
    "Guppy's Eye\0"
    "Guppy's Hairball\0"
    "Guppy's Head\0"
    "Guppy's Paw\0"
    "Guppy's Tail\0"
    "Habit\0"
    "Haemolacria\0"
    "Hallowed Ground\0"
    "Halo of Flies\0"
    "Harlequin Baby\0"
    "Head of Krampus\0"
    "Head of the Keeper\0"
    "Headless Baby\0"
    "Heartbreak\0"
    "Hemoptysis\0"
    "Hive Mind\0"
    "Hold\0"
    "Holy Grail\0"
    "Holy Light\0"
    "Holy Mantle\0"
    "Holy Water\0"
    "Host Hat\0"
    "Hot Bombs\0"
    "How to Jump\0"
    "Humbleing Bundle\0"
    "Hungry Soul\0"
    "Hushy\0"
    "Hypercoagulation\0"
    "IBS\0"
    "IV Bag\0"
    "Immaculate Conception\0"
    "Immaculate Heart\0"
    "Incubus\0"
    "Infamy\0"
    "Infestation\0"
    "Infestation 2\0"
    "Inner Child\0"
    "Ipecac\0"
    "Iron Bar\0"
    "Isaac's Heart\0"
    "Isaac's Tears\0"
    "Isaac's Tomb\0"
    "It Hurts\0"
    "Jacob's Ladder\0"
    "Jar of Flies\0"
    "Jar of Wisps\0"
    "Jaw Bone\0"
    "Jesus Juice\0"
    "Judas' Shadow\0"
    "Juicy Sack\0"
    "Jumper Cables\0"
    "Jupiter\0"
    "Kamikaze!\0"
    "Keeper's Box\0"
    "Keeper's Kin\0"
    "Keeper's Sack\0"
    "Key Bum\0"
    "Key Piece 1\0"
    "Key Piece 2\0"
    "Kidney Bean\0"
    "Kidney Stone\0"
    "King Baby\0"
    "Knife Piece 1\0"
    "Knife Piece 2\0"
    "Knockout Drops\0"
    "Lachryphagy\0"
    "Large Zit\0"
    "Larynx\0"
    "Latch Key\0"
    "Lazarus' Rags\0"
    "Lead Pencil\0"
    "Leech\0"
    "Lemegeton\0"
    "Lemon Mishap\0"
    "Leo\0"
    "Leprosy\0"
    "Libra\0"
    "Lil Abaddon\0"
    "Lil Brimstone\0"
    "Lil Chest\0"
    "Lil Delirium\0"
    "Lil Dumpy\0"
    "Lil Gurdy\0"
    "Lil Haunt\0"
    "Lil Loki\0"
    "Lil Monstro\0"
    "Lil Portal\0"
    "Lil Spewer\0"
    "Linger Bean\0"
    "Little Baggy\0"
    "Little C.H.A.D.\0"
    "Little Chubby\0"
    "Little Gish\0"
    "Little Horn\0"
    "Little Steven\0"
    "Lodestone\0"
    "Loki's Horns\0"
    "Lord of the Pit\0"
    "Lost Contact\0"
    "Lost Fly\0"
    "Lost Soul\0"
    "Lucky Foot\0"
    "Luna\0"
    "Lunch\0"
    "Lusty Blood\0"
    "MEAT!\0"
    "Maggy's Bow\0"
    "Magic 8 Ball\0"
    "Magic Fingers\0"
    "Magic Mushroom\0"
    "Magic Scab\0"
    "Magic Skin\0"
    "Magneto\0"
    "Mama Mega!\0"
    "Marbles\0"
    "Marked\0"
    "Marrow\0"
    "Mars\0"
    "Match Book\0"
    "Maw Of The Void\0"
    "Meat Cleaver\0"
    "Mega Bean\0"
    "Mega Blast\0"
    "Mega Mush\0"
    "Member Card\0"
    "Mercurius\0"
    "Metal Plate\0"
    "Metronome\0"
    "Midas' Touch\0"
    "Milk!\0"
    "Mine Crafter\0"
    "Mini Mush\0"
    "Missing No.\0"
    "Missing Page 2\0"
    "Mitre\0"
    "Moldy Bread\0"
    "Mom's Bottle of Pills\0"
    "Mom's Box\0"
    "Mom's Bra\0"
    "Mom's Bracelet\0"
    "Mom's Coin Purse\0"
    "Mom's Contacts\0"
    "Mom's Eye\0"
    "Mom's Eyeshadow\0"
    "Mom's Heels\0"
    "Mom's Key\0"
    "Mom's Knife\0"
    "Mom's Lipstick\0"
    "Mom's Pad\0"
    "Mom's Pearls\0"
    "Mom's Perfume\0"
    "Mom's Purse\0"
    "Mom's Razor\0"
    "Mom's Ring\0"
    "Mom's Shovel\0"
    "Mom's Underwear\0"
    "Mom's Wig\0"
    "Money = Power\0"
    "Mongo Baby\0"
    "Monster Manual\0"
    "Monstrance\0"
    "Monstro's Lung\0"
    "Monstro's Tooth\0"
    "Montezuma's Revenge\0"
    "More Options\0"
    "Moving Box\0"
    "Mr. Boom\0"
    "Mr. Dolly\0"
    "Mr. ME!\0"
    "Mr. Mega\0"
    "Mucormycosis\0"
    "Multidimensional Baby\0"
    "Mutant Spider\0"
    "My Little Unicorn\0"
    "My Reflection\0"
    "My Shadow\0"
    "Mysterious Liquid\0"
    "Mystery Egg\0"
    "Mystery Gift\0"
    "Mystery Sack\0"
    "Nancy Bombs\0"
    "Neptunus\0"
    "Night Light\0"
    "No. 2\0"
    "Notched Axe\0"
    "Number One\0"
    "Obsessed Fan\0"
    "Ocular Rift\0"
    "Odd Mushroom\0"
    "Old Bandage\0"
    "Options\?\0"
    "Orphan Socks\0"
    "Ouija Board\0"
    "PHD\0"
    "PJs\0"
    "Pageant Boy\0"
    "Pandora's Box\0"
    "Papa Fly\0"
    "Parasitoid\0"
    "Paschal Candle\0"
    "Pause\0"
    "Pay To Play\0"
    "Pentagram\0"
    "Piggy Bank\0"
    "Pisces\0"
    "Placebo\0"
    "Placenta\0"
    "Plan C\0"
    "Playdough Cookie\0"
    "Plum Flute\0"
    "Pluto\0"
    "Pointy Rib\0"
    "Poke Go\0"
    "Polydactyly\0"
    "Polyphemus\0"
    "Pop!\0"
    "Portable Slot\0"
    "Potato Peeler\0"
    "Prayer Card\0"
    "Proptosis\0"
    "Psy Fly\0"
    "Punching Bag\0"
    "Pupula Duplex\0"
    "Purgatory\0"
    "Purity\0"
    "Pyro\0"
    "Pyromaniac\0"
    "Quints\0"
    "R Key\0"
    "Rainbow Baby\0"
    "Raw Liver\0"
    "Razor Blade\0"
    "Recall\0"
    "Red Candle\0"
    "Red Key\0"
    "Red Stew\0"
    "Redemption\0"
    "Remote Detonator\0"
    "Restock\0"
    "Revelation\0"
    "Robo-Baby\0"
    "Robo-Baby 2.0\0"
    "Rock Bottom\0"
    "Rocket in a Jar\0"
    "Roid Rage\0"
    "Rosary\0"
    "Rotten Baby\0"
    "Rotten Meat\0"
    "Rotten Tomato\0"
    "Rubber Cement\0"
    "Rune Bag\0"
    "SMB Super Fan\0"
    "Sack Head\0"
    "Sack of Pennies\0"
    "Sack of Sacks\0"
    "Sacred Heart\0"
    "Sacred Orb\0"
    "Sacrificial Altar\0"
    "Sacrificial Dagger\0"
    "Sad Bombs\0"
    "Safety Pin\0"
    "Sagittarius\0"
    "Salvation\0"
    "Samson's Chains\0"
    "Sanguine Bond\0"
    "Satanic Bible\0"
    "Saturnus\0"
    "Sausage\0"
    "Scapular\0"
    "Scatter Bombs\0"
    "Schoolbag\0"
    "Scissors\0"
    "Scorpio\0"
    "Screw\0"
    "Seraphim\0"
    "Serpent's Kiss\0"
    "Shade\0"
    "Shard of Glass\0"
    "Sharp Key\0"
    "Sharp Plug\0"
    "Sharp Straw\0"
    "Shoop da Whoop!\0"
    "Sinus Infection\0"
    "Sissy Longlegs\0"
    "Sister Maggy\0"
    "Skatole\0"
    "Skeleton Key\0"
    "Slipped Rib\0"
    "Smart Fly\0"
    "Smelter\0"
    "Sol\0"
    "Soul Locket\0"
    "Soy Milk\0"
    "Spear Of Destiny\0"
    "Speed Ball\0"
    "Spelunker Hat\0"
    "Spider Bite\0"
    "Spider Butt\0"
    "Spider Mod\0"
    "Spiderbaby\0"
    "Spin to Win\0"
    "Spindown Dice\0"
    "Spirit Shackles\0"
    "Spirit Sword\0"
    "Spirit of the Night\0"
    "Spoon Bender\0"
    "Sprinkler\0"
    "Squeezy\0"
    "Stapler\0"
    "Star of Bethlehem\0"
    "Starter Deck\0"
    "Steam Sale\0"
    "Stem Cells\0"
    "Steven\0"
    "Sticky Bombs\0"
    "Stigmata\0"
    "Stitches\0"
    "Stop Watch\0"
    "Strange Attractor\0"
    "Strawman\0"
    "Stye\0"
    "Succubus\0"
    "Sulfur\0"
    "Sulfuric Acid\0"
    "Sumptorium\0"
    "Super Bandage\0"
    "Suplex!\0"
    "Supper\0"
    "Sworn Protector\0"
    "Synthoil\0"
    "TMTRAINER\0"
    "Tammy's Head\0"
    "Tarot Cloth\0"
    "Taurus\0"
    "Tear Detonator\0"
    "Tech X\0"
    "Tech.5\0"
    "Technology\0"
    "Technology 2\0"
    "Technology Zero\0"
    "Telekinesis\0"
    "Telepathy For Dummies\0"
    "Teleport 2.0\0"
    "Teleport!\0"
    "Terra\0"
    "The Battery\0"
    "The Bean\0"
    "The Belt\0"
    "The Bible\0"
    "The Black Bean\0"
    "The Body\0"
    "The Book of Belial\0"
    "The Book of Sin\0"
    "The Boomerang\0"
    "The Candle\0"
    "The Common Cold\0"
    "The Compass\0"
    "The D6\0"
    "The Gamekid\0"
    "The Halo\0"
    "The Hourglass\0"
    "The Inner Eye\0"
    "The Intruder\0"
    "The Jar\0"
    "The Ladder\0"
    "The Ludovico Technique\0"
    "The Mark\0"
    "The Mind\0"
    "The Mulligan\0"
    "The Nail\0"
    "The Necronomicon\0"
    "The Negative\0"
    "The Pact\0"
    "The Parasite\0"
    "The Peeper\0"
    "The Pinking Shears\0"
    "The Polaroid\0"
    "The Poop\0"
    "The Relic\0"
    "The Sad Onion\0"
    "The Scooper\0"
    "The Small Rock\0"
    "The Soul\0"
    "The Stairway\0"
    "The Swarm\0"
    "The Virus\0"
    "The Wafer\0"
    "The Wiz\0"
    "There's Options\0"
    "Thunder Thighs\0"
    "Tiny Planet\0"
    "Tinytoma\0"
    "Tonsil\0"
    "Tooth Picks\0"
    "Tooth and Nail\0"
    "Torn Photo\0"
    "Tough Love\0"
    "Toxic Shock\0"
    "Tractor Beam\0"
    "Transcendence\0"
    "Treasure Map\0"
    "Trinity Shield\0"
    "Trisagion\0"
    "Tropicamide\0"
    "Twisted Pair\0"
    "Undefined\0"
    "Unicorn Stump\0"
    "Uranus\0"
    "Urn of Souls\0"
    "Vade Retro\0"
    "Vanishing Twin\0"
    "Varicose Veins\0"
    "Vasculitis\0"
    "Vengeful Spirit\0"
    "Ventricle Razor\0"
    "Venus\0"
    "Virgo\0"
    "Void\0"
    "Voodoo Head\0"
    "Wait What\?\0"
    "Wavy Cap\0"
    "We Need To Go Deeper!\0"
    "White Pony\0"
    "Whore of Babylon\0"
    "Wire Coat Hanger\0"
    "Wooden Nickel\0"
    "Wooden Spoon\0"
    "Worm Friend\0"
    "X-Ray Vision\0"
    "YO LISTEN!\0"
    "Yuck Heart\0"
    "Yum Heart\0"
    "Zodiac\0"
};

// `Isaac.GetCardIdByName` 的名字块（87 条，按名字升序）。
constexpr char kCardNameBlob[1366] = {
    "0 - The Fool\0"
    "0 - The Fool\?\0"
    "2 of Clubs\0"
    "2 of Diamonds\0"
    "2 of Hearts\0"
    "2 of Spades\0"
    "\? Card\0"
    "A Card Against Humanity\0"
    "Ace of Clubs\0"
    "Ace of Diamonds\0"
    "Ace of Hearts\0"
    "Ace of Spades\0"
    "Ancient Recall\0"
    "Chaos Card\0"
    "Cracked Key\0"
    "Credit Card\0"
    "Dice Shard\0"
    "Emergency Contact\0"
    "Era Walk\0"
    "Get Out Of Jail Free Card\0"
    "Holy Card\0"
    "Huge Growth\0"
    "I - The Magician\0"
    "I - The Magician\?\0"
    "II - The High Priestess\0"
    "II - The High Priestess\?\0"
    "III - The Empress\0"
    "III - The Empress\?\0"
    "IV - The Emperor\0"
    "IV - The Emperor\?\0"
    "IX - The Hermit\0"
    "IX - The Hermit\?\0"
    "Joker\0"
    "NULL\0"
    "Queen of Hearts\0"
    "Rules Card\0"
    "Soul of \?\?\?\0"
    "Soul of Apollyon\0"
    "Soul of Azazel\0"
    "Soul of Bethany\0"
    "Soul of Cain\0"
    "Soul of Eden\0"
    "Soul of Eve\0"
    "Soul of Isaac\0"
    "Soul of Jacob and Esau\0"
    "Soul of Judas\0"
    "Soul of Lazarus\0"
    "Soul of Lilith\0"
    "Soul of Magdalene\0"
    "Soul of Samson\0"
    "Soul of the Forgotten\0"
    "Soul of the Keeper\0"
    "Soul of the Lost\0"
    "Suicide King\0"
    "V - The Hierophant\0"
    "V - The Hierophant\?\0"
    "VI - The Lovers\0"
    "VI - The Lovers\?\0"
    "VII - The Chariot\0"
    "VII - The Chariot\?\0"
    "VIII - Justice\0"
    "VIII - Justice\?\0"
    "Wild Card\0"
    "X - Wheel of Fortune\0"
    "X - Wheel of Fortune\?\0"
    "XI - Strength\0"
    "XI - Strength\?\0"
    "XII - The Hanged Man\0"
    "XII - The Hanged Man\?\0"
    "XIII - Death\0"
    "XIII - Death\?\0"
    "XIV - Temperance\0"
    "XIV - Temperance\?\0"
    "XIX - The Sun\0"
    "XIX - The Sun\?\0"
    "XV - The Devil\0"
    "XV - The Devil\?\0"
    "XVI - The Tower\0"
    "XVI - The Tower\?\0"
    "XVII - The Stars\0"
    "XVII - The Stars\?\0"
    "XVIII - The Moon\0"
    "XVIII - The Moon\?\0"
    "XX - Judgement\0"
    "XX - Judgement\?\0"
    "XXI - The World\0"
    "XXI - The World\?\0"
};

// `Isaac.GetPillEffectByName` 的名字块（50 条，按名字升序）。
constexpr char kPillEffectNameBlob[617] = {
    "48 Hour Energy!\0"
    "\?\?\?\0"
    "Addicted!\0"
    "Amnesia\0"
    "Bad Gas\0"
    "Bad Trip\0"
    "Balls of Steel\0"
    "Bombs are Key\0"
    "Experimental Pill\0"
    "Explosive Diarrhea\0"
    "Feels like I'm walking on sunshine!\0"
    "Friends Till The End!\0"
    "Full Health\0"
    "Gulp!\0"
    "Health Down\0"
    "Health Up\0"
    "Hematemesis\0"
    "Horf!\0"
    "I Found Pills\0"
    "I can see forever!\0"
    "I'm Drowsy...\0"
    "I'm Excited!!!\0"
    "Infested!\0"
    "Infested\?\0"
    "Lemon Party\0"
    "Luck Down\0"
    "Luck Up\0"
    "One makes you larger\0"
    "One makes you small\0"
    "Paralysis\0"
    "Percs!\0"
    "Pheromones\0"
    "Power Pill!\0"
    "Pretty Fly\0"
    "Puberty\0"
    "R U A Wizard\?\0"
    "Range Down\0"
    "Range Up\0"
    "Re-Lax\0"
    "Retro Vision\0"
    "Shot Speed Down\0"
    "Shot Speed Up\0"
    "Something's wrong...\0"
    "Speed Down\0"
    "Speed Up\0"
    "Tears Down\0"
    "Tears Up\0"
    "Telepills\0"
    "Vurp!\0"
    "X-Lax\0"
};

// `Isaac.GetPlayerTypeByName` 的名字块（21 条，按名字升序）。
constexpr char kPlayerTypeNameBlob[160] = {
    "\?\?\?\0"
    "Apollyon\0"
    "Azazel\0"
    "Bethany\0"
    "Black Judas\0"
    "Cain\0"
    "Eden\0"
    "Esau\0"
    "Eve\0"
    "Isaac\0"
    "Jacob\0"
    "Judas\0"
    "Keeper\0"
    "Lazarus\0"
    "Lazarus II\0"
    "Lilith\0"
    "Magdalene\0"
    "Samson\0"
    "The Forgotten\0"
    "The Lost\0"
    "The Soul\0"
};

// `Isaac.GetChallengeIdByName` 的名字块（44 条，按名字升序）。
constexpr char kChallengeNameBlob[527] = {
    "Aprils fool\0"
    "BEANS!\0"
    "BRAINS!\0"
    "Backasswards\0"
    "Baptism by Fire\0"
    "Bloody Mary\0"
    "Blue Bomber\0"
    "Cantripped!\0"
    "Cat Got Your Tongue\0"
    "Computer Savy\0"
    "Cursed!\0"
    "Darkness Falls\0"
    "Demo Man\0"
    "Glass Cannon\0"
    "Have a heart\0"
    "Head Trauma\0"
    "High Brow\0"
    "Hot Potato\0"
    "I RULE!\0"
    "Isaac's Awakening\0"
    "Its In The Cards\0"
    "Onan's Streak\0"
    "PAY TO PLAY\0"
    "PONG\0"
    "PRIDE DAY!\0"
    "Pica Run\0"
    "Pitch Black\0"
    "Pokey mans\0"
    "Purist\0"
    "Red Redemption\0"
    "SPEED!\0"
    "Scat Man\0"
    "Seeing Double\0"
    "Slow Roll\0"
    "Solar System\0"
    "Suicide King\0"
    "The Family Man\0"
    "The Guardian\0"
    "The Host\0"
    "The Tank\0"
    "Ultra hard\0"
    "WAKA WAKA\0"
    "When Life Gives You Lemons\0"
    "XXXXXXXXL\0"
};

// `Isaac.GetTrinketIdByName` 的名字块（188 条，按名字升序）。
constexpr char kTrinketNameBlob[2309] = {
    "'M\0"
    "\?\?\?'s Soul\0"
    "A Lighter\0"
    "A Missing Page\0"
    "AAA Battery\0"
    "Ace of Spades\0"
    "Adoption Papers\0"
    "Apollyon's Best Friend\0"
    "Apple of Sodom\0"
    "Azazel's Stump\0"
    "Baby-Bender\0"
    "Bag Lunch\0"
    "Bat Wing\0"
    "Beth's Essence\0"
    "Beth's Faith\0"
    "Bible Tract\0"
    "Black Feather\0"
    "Black Lipstick\0"
    "Black Tooth\0"
    "Blasting Cap\0"
    "Blessed Penny\0"
    "Blind Rage\0"
    "Blister\0"
    "Bloody Crown\0"
    "Bloody Penny\0"
    "Blue Key\0"
    "Bob's Bladder\0"
    "Brain Worm\0"
    "Broken Ankh\0"
    "Broken Glasses\0"
    "Broken Magnet\0"
    "Broken Padlock\0"
    "Broken Remote\0"
    "Broken Syringe\0"
    "Brown Cap\0"
    "Burnt Penny\0"
    "Butt Penny\0"
    "Butter!\0"
    "Cain's Eye\0"
    "Callus\0"
    "Cancer\0"
    "Cartridge\0"
    "Charged Penny\0"
    "Chewed Pen\0"
    "Child Leash\0"
    "Child's Heart\0"
    "Counterfeit Penny\0"
    "Cracked Crown\0"
    "Cracked Dice\0"
    "Cricket Leg\0"
    "Crow Heart\0"
    "Crystal Key\0"
    "Cursed Penny\0"
    "Cursed Skull\0"
    "Curved Horn\0"
    "Daemon's Tail\0"
    "Devil's Crown\0"
    "Dice Bag\0"
    "Dim Bulb\0"
    "Dingle Berry\0"
    "Door Stop\0"
    "Duct Tape\0"
    "Endless Nameless\0"
    "Equality!\0"
    "Error\0"
    "Eve's Bird Foot\0"
    "Expansion Pack\0"
    "Extension Cord\0"
    "Faded Polaroid\0"
    "Filigree Feather\0"
    "Finger Bone\0"
    "Fish Head\0"
    "Fish Tail\0"
    "Flat File\0"
    "Flat Penny\0"
    "Flat Worm\0"
    "Forgotten Lullaby\0"
    "Found Soul\0"
    "Fragmented Card\0"
    "Friendship Necklace\0"
    "Gigante Bean\0"
    "Gilded Key\0"
    "Goat Hoof\0"
    "Golden Horse Shoe\0"
    "Hairpin\0"
    "Hollow Heart\0"
    "Holy Crown\0"
    "Hook Worm\0"
    "Ice Cube\0"
    "Isaac's Fork\0"
    "Isaac's Head\0"
    "Jawbreaker\0"
    "Judas' Tongue\0"
    "Karma\0"
    "Keeper's Bargain\0"
    "Kid's Drawing\0"
    "Lazy Worm\0"
    "Liberty Cap\0"
    "Lil Clot\0"
    "Lil Larva\0"
    "Locust of Conquest\0"
    "Locust of Death\0"
    "Locust of Famine\0"
    "Locust of Pestilence\0"
    "Locust of War\0"
    "Lost Cork\0"
    "Louse\0"
    "Lucky Rock\0"
    "Lucky Sack\0"
    "Lucky Toe\0"
    "Maggy's Faith\0"
    "Match Stick\0"
    "Meconium\0"
    "Missing Poster\0"
    "Modeling Clay\0"
    "Mom's Lock\0"
    "Mom's Locket\0"
    "Mom's Pearl\0"
    "Mom's Toenail\0"
    "Monkey Paw\0"
    "Mother's Kiss\0"
    "Myosotis\0"
    "Mysterious Candy\0"
    "Mysterious Paper\0"
    "NO!\0"
    "Nose Goblin\0"
    "Nuh Uh!\0"
    "Number Magnet\0"
    "Old Capacitor\0"
    "Ouroboros Worm\0"
    "Panic Button\0"
    "Paper Clip\0"
    "Pay To Win\0"
    "Perfection\0"
    "Petrified Poop\0"
    "Pinky Eye\0"
    "Poker Chip\0"
    "Polished Bone\0"
    "Pulse Worm\0"
    "Purple Heart\0"
    "Push Pin\0"
    "RC Remote\0"
    "Rainbow Worm\0"
    "Red Patch\0"
    "Rib of Greed\0"
    "Ring Cap\0"
    "Ring Worm\0"
    "Rosary Bead\0"
    "Rotten Penny\0"
    "Rusted Key\0"
    "Safety Cap\0"
    "Safety Scissors\0"
    "Samson's Lock\0"
    "Second Hand\0"
    "Shiny Rock\0"
    "Short Fuse\0"
    "Sigil of Baphomet\0"
    "Silver Dollar\0"
    "Stem Cell\0"
    "Store Credit\0"
    "Store Key\0"
    "Strange Key\0"
    "Stud Finder\0"
    "Super Ball\0"
    "Super Magnet\0"
    "Swallowed M80\0"
    "Swallowed Penny\0"
    "Tape Worm\0"
    "Teardrop Charm\0"
    "Telescope Lens\0"
    "Temporary Tattoo\0"
    "The Left Hand\0"
    "The Twins\0"
    "Tick\0"
    "Tonsil\0"
    "Torn Card\0"
    "Torn Pocket\0"
    "Umbilical Cord\0"
    "Used Diaper\0"
    "Vibrant Bulb\0"
    "Walnut\0"
    "Watch Battery\0"
    "Whip Worm\0"
    "Wicked Crown\0"
    "Wiggle Worm\0"
    "Wish Bone\0"
    "Wooden Cross\0"
    "Your Soul\0"
};

// `Isaac.GetItemIdByName` 的条目表（与上面名字块一一对应）。
constexpr IsaacNameEntry kCollectibleNameEntries[] = {
    {0, 559, -1},
    {9, 11, -1},
    {14, 245, -1},
    {20, 554, -1},
    {28, 191, -1},
    {42, 647, -1},
    {51, 526, -1},
    {59, 359, -1},
    {72, 116, -1},
    {79, 15, -1},
    {82, 320, -1},
    {100, 564, -1},
    {114, 18, -1},
    {123, 132, -1},
    {138, 130, -1},
    {145, 672, -1},
    {162, 74, -1},
    {172, 346, -1},
    {180, 230, -1},
    {188, 188, -1},
    {193, 706, -1},
    {199, 491, -1},
    {209, 601, -1},
    {227, 493, -1},
    {238, 641, -1},
    {247, 585, -1},
    {261, 561, -1},
    {273, 465, -1},
    {286, 65, -1},
    {305, 214, -1},
    {312, 528, -1},
    {326, 511, -1},
    {336, 722, -1},
    {347, 161, -1},
    {352, 222, -1},
    {365, 443, -1},
    {372, 308, -1},
    {381, 300, -1},
    {387, 677, -1},
    {405, 408, -1},
    {412, 699, -1},
    {426, 272, -1},
    {430, 247, -1},
    {436, 250, -1},
    {447, 506, -1},
    {459, 710, -1},
    {475, 207, -1},
    {492, 231, -1},
    {504, 603, -1},
    {517, 458, -1},
    {530, 690, -1},
    {542, 704, -1},
    {551, 274, -1},
    {560, 136, -1},
    {572, 391, -1},
    {581, 473, -1},
    {592, 279, -1},
    {600, 664, -1},
    {612, 438, -1},
    {618, 610, -1},
    {628, 616, -1},
    {639, 619, -1},
    {650, 260, -1},
    {663, 512, -1},
    {674, 226, -1},
    {686, 420, -1},
    {699, 286, -1},
    {710, 535, -1},
    {718, 119, -1},
    {728, 614, -1},
    {740, 254, -1},
    {751, 569, -1},
    {762, 565, -1},
    {774, 186, -1},
    {787, 7, -1},
    {807, 509, -1},
    {821, 695, -1},
    {833, 157, -1},
    {845, 342, -1},
    {854, 246, -1},
    {863, 273, -1},
    {875, 140, -1},
    {887, 42, -1},
    {905, 125, -1},
    {916, 607, -1},
    {928, 131, -1},
    {937, 353, -1},
    {948, 683, -1},
    {959, 78, -1},
    {979, 287, -1},
    {995, 58, -1},
    {1011, 584, -1},
    {1027, 545, -1},
    {1044, 19, -1},
    {1050, 624, -1},
    {1063, 629, -1},
    {1071, 198, -1},
    {1075, 357, -1},
    {1090, 288, -1},
    {1105, 513, -1},
    {1110, 25, -1},
    {1120, 326, -1},
    {1135, 118, -1},
    {1145, 646, -1},
    {1161, 549, -1},
    {1175, 514, -1},
    {1188, 550, -1},
    {1202, 337, -1},
    {1215, 8, -1},
    {1229, 504, -1},
    {1242, 129, -1},
    {1257, 518, -1},
    {1272, 144, -1},
    {1283, 385, -1},
    {1289, 377, -1},
    {1303, 209, -1},
    {1314, 294, -1},
    {1326, 678, -1},
    {1336, 340, -1},
    {1350, 319, -1},
    {1367, 412, -1},
    {1386, 497, -1},
    {1398, 301, -1},
    {1405, 671, -1},
    {1417, 307, -1},
    {1427, 356, -1},
    {1439, 660, -1},
    {1452, 165, -1},
    {1469, 162, -1},
    {1482, 387, -1},
    {1489, 216, -1},
    {1506, 208, -1},
    {1520, 402, -1},
    {1526, 372, -1},
    {1539, 62, -1},
    {1560, 154, -1},
    {1574, 69, -1},
    {1589, 423, -1},
    {1610, 263, -1},
    {1621, 482, -1},
    {1629, 480, -1},
    {1637, 453, -1},
    {1655, 457, -1},
    {1665, 644, -1},
    {1683, 466, -1},
    {1693, 369, -1},
    {1703, 241, -1},
    {1723, 296, -1},
    {1733, 521, -1},
    {1740, 354, -1},
    {1752, 160, -1},
    {1766, 675, -1},
    {1778, 224, -1},
    {1793, 4, -1},
    {1808, 485, -1},
    {1822, 415, -1},
    {1837, 158, -1},
    {1850, 652, -1},
    {1860, 73, -1},
    {1873, 48, -1},
    {1887, 371, -1},
    {1906, 316, -1},
    {1917, 489, -1},
    {1928, 476, -1},
    {1931, 285, -1},
    {1935, 283, -1},
    {1940, 386, -1},
    {1944, 166, -1},
    {1948, 284, -1},
    {1951, 437, -1},
    {1954, 406, -1},
    {1957, 175, -1},
    {1967, 455, -1},
    {1983, 668, -1},
    {1994, 546, -1},
    {2005, 170, -1},
    {2020, 577, -1},
    {2029, 705, -1},
    {2039, 278, -1},
    {2048, 259, -1},
    {2060, 442, -1},
    {2079, 481, -1},
    {2089, 117, -1},
    {2099, 81, -1},
    {2108, 185, -1},
    {2118, 373, -1},
    {2127, 336, -1},
    {2138, 124, -1},
    {2155, 446, -1},
    {2166, 628, -1},
    {2184, 530, -1},
    {2197, 237, -1},
    {2211, 729, -1},
    {2224, 85, -1},
    {2238, 416, -1},
    {2251, 510, -1},
    {2261, 113, -1},
    {2272, 469, -1},
    {2283, 24, -1},
    {2291, 23, -1},
    {2298, 347, -1},
    {2307, 576, -1},
    {2318, 57, -1},
    {2337, 568, -1},
    {2357, 547, -1},
    {2372, 47, -1},
    {2388, 445, -1},
    {2398, 633, -1},
    {2404, 52, -1},
    {2414, 566, -1},
    {2428, 265, -1},
    {2437, 498, -1},
    {2445, 486, -1},
    {2456, 236, -1},
    {2464, 700, -1},
    {2477, 381, -1},
    {2493, 490, -1},
    {2505, 676, -1},
    {2517, 409, -1},
    {2530, 168, -1},
    {2541, 368, -1},
    {2550, 638, -1},
    {2557, 703, -1},
    {2566, 609, -1},
    {2577, 499, -1},
    {2587, 496, -1},
    {2598, 310, -1},
    {2612, 720, -1},
    {2627, 632, -1},
    {2638, 410, -1},
    {2647, 240, -1},
    {2670, 401, -1},
    {2680, 600, -1},
    {2690, 558, -1},
    {2699, 462, -1},
    {2713, 450, -1},
    {2726, 572, -1},
    {2744, 654, -1},
    {2754, 204, -1},
    {2765, 404, -1},
    {2778, 517, -1},
    {2789, 179, -1},
    {2794, 361, -1},
    {2808, 467, -1},
    {2816, 257, -1},
    {2826, 540, -1},
    {2837, 711, -1},
    {2842, 291, -1},
    {2849, 128, -1},
    {2863, 127, -1},
    {2877, 557, -1},
    {2892, 578, -1},
    {2906, 608, -1},
    {2919, 687, -1},
    {2933, 364, -1},
    {2945, 382, -1},
    {2959, 418, -1},
    {2970, 649, -1},
    {2982, 405, -1},
    {2989, 728, -1},
    {2995, 318, -1},
    {3002, 622, -1},
    {3010, 163, -1},
    {3021, 727, -1},
    {3033, 495, -1},
    {3046, 658, -1},
    {3057, 225, -1},
    {3063, 352, -1},
    {3076, 730, -1},
    {3086, 460, -1},
    {3095, 689, -1},
    {3110, 432, -1},
    {3124, 422, -1},
    {3143, 464, -1},
    {3160, 210, -1},
    {3172, 215, -1},
    {3182, 398, -1},
    {3194, 331, -1},
    {3202, 555, -1},
    {3215, 501, -1},
    {3230, 70, -1},
    {3246, 112, -1},
    {3261, 206, -1},
    {3272, 212, -1},
    {3287, 665, -1},
    {3299, 187, -1},
    {3316, 145, -1},
    {3329, 133, -1},
    {3341, 134, -1},
    {3354, 156, -1},
    {3360, 531, -1},
    {3372, 543, -1},
    {3388, 10, -1},
    {3402, 167, -1},
    {3417, 293, -1},
    {3433, 429, -1},
    {3452, 269, -1},
    {3466, 694, -1},
    {3477, 726, -1},
    {3488, 248, -1},
    {3498, 715, -1},
    {3503, 184, -1},
    {3514, 374, -1},
    {3525, 313, -1},
    {3537, 178, -1},
    {3548, 375, -1},
    {3557, 256, -1},
    {3567, 282, -1},
    {3579, 203, -1},
    {3596, 684, -1},
    {3608, 470, -1},
    {3614, 724, -1},
    {3631, 725, -1},
    {3635, 135, -1},
    {3642, 413, -1},
    {3664, 573, -1},
    {3681, 360, -1},
    {3689, 242, -1},
    {3696, 148, -1},
    {3708, 234, -1},
    {3722, 688, -1},
    {3734, 149, -1},
    {3741, 201, -1},
    {3750, 276, -1},
    {3764, 323, -1},
    {3778, 701, -1},
    {3791, 560, -1},
    {3800, 494, -1},
    {3815, 434, -1},
    {3828, 685, -1},
    {3841, 548, -1},
    {3850, 197, -1},
    {3862, 311, -1},
    {3876, 266, -1},
    {3887, 520, -1},
    {3901, 594, -1},
    {3909, 40, -1},
    {3919, 719, -1},
    {3932, 717, -1},
    {3945, 716, -1},
    {3959, 388, -1},
    {3967, 238, -1},
    {3979, 239, -1},
    {3991, 421, -1},
    {4003, 440, -1},
    {4016, 472, -1},
    {4026, 626, -1},
    {4040, 627, -1},
    {4054, 637, -1},
    {4069, 532, -1},
    {4081, 502, -1},
    {4091, 611, -1},
    {4098, 343, -1},
    {4108, 332, -1},
    {4122, 444, -1},
    {4134, 270, -1},
    {4140, 712, -1},
    {4150, 56, -1},
    {4163, 302, -1},
    {4167, 525, -1},
    {4175, 304, -1},
    {4181, 679, -1},
    {4193, 275, -1},
    {4207, 362, -1},
    {4217, 519, -1},
    {4230, 615, -1},
    {4240, 384, -1},
    {4250, 277, -1},
    {4260, 435, -1},
    {4269, 471, -1},
    {4281, 681, -1},
    {4292, 537, -1},
    {4303, 447, -1},
    {4315, 252, -1},
    {4328, 96, -1},
    {4344, 88, -1},
    {4358, 99, -1},
    {4370, 503, -1},
    {4382, 100, -1},
    {4396, 617, -1},
    {4406, 87, -1},
    {4419, 82, -1},
    {4435, 213, -1},
    {4448, 365, -1},
    {4457, 612, -1},
    {4467, 46, -1},
    {4478, 589, -1},
    {4483, 22, -1},
    {4489, 411, -1},
    {4501, 193, -1},
    {4507, 312, -1},
    {4519, 194, -1},
    {4532, 295, -1},
    {4546, 12, -1},
    {4561, 253, -1},
    {4572, 642, -1},
    {4583, 53, -1},
    {4591, 483, -1},
    {4602, 538, -1},
    {4610, 394, -1},
    {4617, 541, -1},
    {4624, 593, -1},
    {4629, 344, -1},
    {4640, 399, -1},
    {4656, 631, -1},
    {4669, 351, -1},
    {4679, 441, -1},
    {4690, 625, -1},
    {4700, 602, -1},
    {4712, 590, -1},
    {4722, 449, -1},
    {4734, 488, -1},
    {4744, 202, -1},
    {4757, 436, -1},
    {4763, 427, -1},
    {4776, 71, -1},
    {4786, 258, -1},
    {4798, 262, -1},
    {4813, 173, -1},
    {4819, 456, -1},
    {4831, 102, -1},
    {4853, 439, -1},
    {4863, 39, -1},
    {4873, 604, -1},
    {4888, 195, -1},
    {4905, 110, -1},
    {4920, 55, -1},
    {4930, 200, -1},
    {4946, 30, -1},
    {4958, 199, -1},
    {4968, 114, -1},
    {4980, 31, -1},
    {4995, 41, -1},
    {5005, 355, -1},
    {5018, 228, -1},
    {5032, 139, -1},
    {5044, 508, -1},
    {5056, 732, -1},
    {5067, 552, -1},
    {5080, 29, -1},
    {5096, 217, -1},
    {5106, 109, -1},
    {5120, 322, -1},
    {5131, 123, -1},
    {5146, 574, -1},
    {5157, 229, -1},
    {5172, 86, -1},
    {5188, 680, -1},
    {5208, 414, -1},
    {5221, 523, -1},
    {5232, 37, -1},
    {5241, 370, -1},
    {5251, 527, -1},
    {5259, 106, -1},
    {5268, 553, -1},
    {5281, 431, -1},
    {5303, 153, -1},
    {5317, 77, -1},
    {5335, 5, -1},
    {5349, 433, -1},
    {5359, 317, -1},
    {5377, 539, -1},
    {5389, 515, -1},
    {5402, 271, -1},
    {5415, 563, -1},
    {5427, 597, -1},
    {5436, 425, -1},
    {5448, 378, -1},
    {5454, 147, -1},
    {5466, 6, -1},
    {5477, 426, -1},
    {5490, 606, -1},
    {5502, 120, -1},
    {5515, 219, -1},
    {5527, 670, -1},
    {5536, 571, -1},
    {5549, 115, -1},
    {5561, 75, -1},
    {5565, 428, -1},
    {5569, 141, -1},
    {5581, 297, -1},
    {5595, 430, -1},
    {5604, 461, -1},
    {5615, 567, -1},
    {5630, 478, -1},
    {5636, 380, -1},
    {5648, 51, -1},
    {5658, 227, -1},
    {5669, 309, -1},
    {5676, 348, -1},
    {5684, 218, -1},
    {5693, 475, -1},
    {5700, 570, -1},
    {5717, 650, -1},
    {5728, 598, -1},
    {5734, 544, -1},
    {5745, 505, -1},
    {5753, 454, -1},
    {5765, 169, -1},
    {5776, 529, -1},
    {5781, 177, -1},
    {5795, 487, -1},
    {5809, 146, -1},
    {5821, 261, -1},
    {5831, 581, -1},
    {5839, 281, -1},
    {5852, 379, -1},
    {5866, 634, -1},
    {5876, 407, -1},
    {5883, 190, -1},
    {5888, 223, -1},
    {5899, 661, -1},
    {5906, 636, -1},
    {5912, 174, -1},
    {5925, 16, -1},
    {5935, 126, -1},
    {5947, 714, -1},
    {5954, 289, -1},
    {5965, 580, -1},
    {5973, 621, -1},
    {5982, 673, -1},
    {5993, 137, -1},
    {6010, 376, -1},
    {6018, 643, -1},
    {6029, 95, -1},
    {6039, 267, -1},
    {6053, 562, -1},
    {6065, 583, -1},
    {6081, 14, -1},
    {6091, 72, -1},
    {6098, 268, -1},
    {6110, 26, -1},
    {6122, 618, -1},
    {6136, 221, -1},
    {6150, 389, -1},
    {6159, 189, -1},
    {6173, 424, -1},
    {6183, 94, -1},
    {6199, 500, -1},
    {6213, 182, -1},
    {6226, 691, -1},
    {6237, 536, -1},
    {6255, 172, -1},
    {6274, 220, -1},
    {6284, 339, -1},
    {6295, 306, -1},
    {6307, 696, -1},
    {6317, 321, -1},
    {6333, 692, -1},
    {6347, 292, -1},
    {6361, 595, -1},
    {6370, 669, -1},
    {6378, 142, -1},
    {6387, 366, -1},
    {6401, 534, -1},
    {6411, 325, -1},
    {6420, 305, -1},
    {6428, 255, -1},
    {6434, 390, -1},
    {6443, 393, -1},
    {6458, 468, -1},
    {6464, 448, -1},
    {6479, 623, -1},
    {6489, 205, -1},
    {6500, 507, -1},
    {6512, 49, -1},
    {6528, 459, -1},
    {6544, 280, -1},
    {6559, 67, -1},
    {6572, 9, -1},
    {6580, 17, -1},
    {6593, 542, -1},
    {6605, 264, -1},
    {6615, 479, -1},
    {6623, 588, -1},
    {6627, 686, -1},
    {6639, 330, -1},
    {6648, 400, -1},
    {6665, 143, -1},
    {6676, 91, -1},
    {6690, 89, -1},
    {6702, 171, -1},
    {6714, 403, -1},
    {6725, 211, -1},
    {6736, 655, -1},
    {6748, 723, -1},
    {6762, 674, -1},
    {6778, 579, -1},
    {6791, 159, -1},
    {6811, 3, -1},
    {6824, 516, -1},
    {6834, 196, -1},
    {6842, 708, -1},
    {6850, 651, -1},
    {6868, 251, -1},
    {6881, 64, -1},
    {6892, 176, -1},
    {6903, 50, -1},
    {6910, 367, -1},
    {6923, 138, -1},
    {6932, 635, -1},
    {6941, 232, -1},
    {6952, 315, -1},
    {6970, 667, -1},
    {6979, 731, -1},
    {6984, 417, -1},
    {6993, 556, -1},
    {7000, 463, -1},
    {7014, 713, -1},
    {7025, 92, -1},
    {7039, 709, -1},
    {7047, 707, -1},
    {7054, 363, -1},
    {7070, 345, -1},
    {7079, 721, -1},
    {7089, 38, -1},
    {7102, 451, -1},
    {7114, 299, -1},
    {7121, 383, -1},
    {7136, 395, -1},
    {7143, 244, -1},
    {7150, 68, -1},
    {7161, 152, -1},
    {7174, 524, -1},
    {7190, 522, -1},
    {7202, 192, -1},
    {7224, 419, -1},
    {7237, 44, -1},
    {7247, 592, -1},
    {7253, 63, -1},
    {7265, 111, -1},
    {7274, 28, -1},
    {7283, 33, -1},
    {7293, 180, -1},
    {7308, 334, -1},
    {7317, 34, -1},
    {7336, 97, -1},
    {7352, 338, -1},
    {7366, 164, -1},
    {7377, 103, -1},
    {7393, 21, -1},
    {7405, 105, -1},
    {7412, 93, -1},
    {7424, 101, -1},
    {7433, 66, -1},
    {7447, 2, -1},
    {7461, 575, -1},
    {7474, 290, -1},
    {7482, 60, -1},
    {7493, 329, -1},
    {7516, 79, -1},
    {7525, 333, -1},
    {7534, 151, -1},
    {7547, 83, -1},
    {7556, 35, -1},
    {7573, 328, -1},
    {7586, 80, -1},
    {7595, 104, -1},
    {7608, 155, -1},
    {7619, 107, -1},
    {7638, 327, -1},
    {7651, 36, -1},
    {7660, 98, -1},
    {7670, 1, -1},
    {7684, 605, -1},
    {7696, 90, -1},
    {7711, 335, -1},
    {7720, 586, -1},
    {7733, 693, -1},
    {7743, 13, -1},
    {7753, 108, -1},
    {7763, 358, -1},
    {7771, 249, -1},
    {7787, 314, -1},
    {7802, 233, -1},
    {7814, 645, -1},
    {7823, 474, -1},
    {7830, 183, -1},
    {7842, 663, -1},
    {7857, 341, -1},
    {7868, 150, -1},
    {7879, 350, -1},
    {7891, 397, -1},
    {7904, 20, -1},
    {7918, 54, -1},
    {7931, 243, -1},
    {7946, 533, -1},
    {7956, 659, -1},
    {7968, 698, -1},
    {7981, 324, -1},
    {7991, 298, -1},
    {8005, 596, -1},
    {8012, 640, -1},
    {8025, 653, -1},
    {8036, 697, -1},
    {8051, 452, -1},
    {8066, 657, -1},
    {8077, 702, -1},
    {8093, 396, -1},
    {8109, 591, -1},
    {8115, 303, -1},
    {8121, 477, -1},
    {8126, 599, -1},
    {8138, 484, -1},
    {8149, 582, -1},
    {8158, 84, -1},
    {8180, 181, -1},
    {8191, 122, -1},
    {8208, 32, -1},
    {8225, 349, -1},
    {8239, 27, -1},
    {8252, 682, -1},
    {8264, 76, -1},
    {8277, 492, -1},
    {8288, 639, -1},
    {8299, 45, -1},
    {8309, 392, -1},
};

// `Isaac.GetCardIdByName` 的条目表（与上面名字块一一对应）。
constexpr IsaacNameEntry kCardNameEntries[] = {
    {0, 1, -1},
    {13, 56, -1},
    {27, 23, -1},
    {38, 24, -1},
    {52, 26, -1},
    {64, 25, -1},
    {76, 48, -1},
    {83, 45, -1},
    {107, 27, -1},
    {120, 28, -1},
    {136, 30, -1},
    {150, 29, -1},
    {164, 53, -1},
    {179, 42, -1},
    {190, 78, -1},
    {202, 43, -1},
    {214, 49, -1},
    {225, 50, -1},
    {243, 54, -1},
    {252, 47, -1},
    {278, 51, -1},
    {288, 52, -1},
    {300, 2, -1},
    {317, 57, -1},
    {335, 3, -1},
    {359, 58, -1},
    {384, 4, -1},
    {402, 59, -1},
    {421, 5, -1},
    {438, 60, -1},
    {456, 10, -1},
    {472, 65, -1},
    {489, 31, -1},
    {495, 0, -1},
    {500, 79, -1},
    {516, 44, -1},
    {527, 85, -1},
    {539, 94, -1},
    {556, 88, -1},
    {571, 96, -1},
    {587, 83, -1},
    {600, 90, -1},
    {613, 86, -1},
    {625, 81, -1},
    {639, 97, -1},
    {662, 84, -1},
    {676, 89, -1},
    {692, 92, -1},
    {707, 82, -1},
    {725, 87, -1},
    {740, 95, -1},
    {762, 93, -1},
    {781, 91, -1},
    {798, 46, -1},
    {811, 6, -1},
    {830, 61, -1},
    {850, 7, -1},
    {866, 62, -1},
    {883, 8, -1},
    {901, 63, -1},
    {920, 9, -1},
    {935, 64, -1},
    {951, 80, -1},
    {961, 11, -1},
    {982, 66, -1},
    {1004, 12, -1},
    {1018, 67, -1},
    {1033, 13, -1},
    {1054, 68, -1},
    {1076, 14, -1},
    {1089, 69, -1},
    {1103, 15, -1},
    {1120, 70, -1},
    {1138, 20, -1},
    {1152, 75, -1},
    {1167, 16, -1},
    {1182, 71, -1},
    {1198, 17, -1},
    {1214, 72, -1},
    {1231, 18, -1},
    {1248, 73, -1},
    {1266, 19, -1},
    {1283, 74, -1},
    {1301, 21, -1},
    {1316, 76, -1},
    {1332, 22, -1},
    {1348, 77, -1},
};

// `Isaac.GetPillEffectByName` 的条目表（与上面名字块一一对应）。
constexpr IsaacNameEntry kPillEffectNameEntries[] = {
    {0, 20, -1},
    {16, 31, -1},
    {20, 29, -1},
    {30, 25, -1},
    {38, 0, -1},
    {46, 1, -1},
    {55, 2, -1},
    {70, 3, -1},
    {84, 49, -1},
    {102, 4, -1},
    {121, 45, -1},
    {157, 38, -1},
    {179, 5, -1},
    {191, 43, -1},
    {197, 6, -1},
    {209, 7, -1},
    {219, 21, -1},
    {231, 44, -1},
    {237, 8, -1},
    {251, 23, -1},
    {270, 41, -1},
    {284, 42, -1},
    {299, 34, -1},
    {309, 35, -1},
    {319, 26, -1},
    {331, 17, -1},
    {341, 18, -1},
    {349, 32, -1},
    {370, 33, -1},
    {390, 22, -1},
    {400, 28, -1},
    {407, 24, -1},
    {418, 36, -1},
    {430, 10, -1},
    {441, 9, -1},
    {449, 27, -1},
    {463, 11, -1},
    {474, 12, -1},
    {483, 30, -1},
    {490, 37, -1},
    {503, 47, -1},
    {519, 48, -1},
    {533, 40, -1},
    {554, 13, -1},
    {565, 14, -1},
    {574, 15, -1},
    {585, 16, -1},
    {594, 19, -1},
    {604, 46, -1},
    {610, 39, -1},
};

// `Isaac.GetPlayerTypeByName` 的条目表（与上面名字块一一对应）。
constexpr IsaacNameEntry kPlayerTypeNameEntries[] = {
    {0, 4, 25},
    {4, 15, 34},
    {13, 7, 28},
    {20, 18, 36},
    {28, 12, -1},
    {40, 2, 23},
    {45, 9, 30},
    {50, 20, -1},
    {55, 5, 26},
    {59, 0, 21},
    {65, 19, 37},
    {71, 3, 24},
    {77, 14, 33},
    {84, 8, 29},
    {92, 11, -1},
    {103, 13, 32},
    {110, 1, 22},
    {120, 6, 27},
    {127, 16, 35},
    {141, 10, 31},
    {150, 17, 40},
};

// `Isaac.GetChallengeIdByName` 的条目表（与上面名字块一一对应）。
constexpr IsaacNameEntry kChallengeNameEntries[] = {
    {0, 32, -1},
    {12, 13, -1},
    {19, 27, -1},
    {27, 31, -1},
    {40, 38, -1},
    {56, 37, -1},
    {68, 23, -1},
    {80, 43, -1},
    {92, 8, -1},
    {112, 16, -1},
    {126, 10, -1},
    {134, 4, -1},
    {149, 9, -1},
    {158, 11, -1},
    {171, 25, -1},
    {184, 3, -1},
    {196, 2, -1},
    {206, 42, -1},
    {217, 26, -1},
    {225, 39, -1},
    {243, 14, -1},
    {260, 29, -1},
    {274, 24, -1},
    {286, 35, -1},
    {291, 28, -1},
    {302, 41, -1},
    {311, 1, -1},
    {323, 33, -1},
    {334, 20, -1},
    {341, 44, -1},
    {356, 22, -1},
    {363, 36, -1},
    {372, 40, -1},
    {386, 15, -1},
    {396, 6, -1},
    {409, 7, -1},
    {422, 19, -1},
    {437, 30, -1},
    {450, 18, -1},
    {459, 5, -1},
    {468, 34, -1},
    {479, 17, -1},
    {489, 12, -1},
    {516, 21, -1},
};

// `Isaac.GetTrinketIdByName` 的条目表（与上面名字块一一对应）。
constexpr IsaacNameEntry kTrinketNameEntries[] = {
    {0, 138, -1},
    {3, 57, -1},
    {14, 135, -1},
    {24, 48, -1},
    {39, 3, -1},
    {51, 45, -1},
    {65, 184, -1},
    {81, 186, -1},
    {104, 140, -1},
    {119, 162, -1},
    {134, 127, -1},
    {146, 105, -1},
    {156, 118, -1},
    {165, 182, -1},
    {180, 142, -1},
    {193, 18, -1},
    {205, 80, -1},
    {219, 17, -1},
    {234, 95, -1},
    {246, 73, -1},
    {259, 131, -1},
    {273, 81, -1},
    {284, 77, -1},
    {292, 111, -1},
    {305, 49, -1},
    {318, 150, -1},
    {327, 71, -1},
    {341, 144, -1},
    {352, 28, -1},
    {364, 187, -1},
    {379, 6, -1},
    {393, 136, -1},
    {408, 4, -1},
    {422, 132, -1},
    {437, 90, -1},
    {447, 50, -1},
    {459, 24, -1},
    {470, 122, -1},
    {478, 59, -1},
    {489, 14, -1},
    {496, 39, -1},
    {503, 8, -1},
    {513, 147, -1},
    {527, 130, -1},
    {538, 89, -1},
    {550, 34, -1},
    {564, 52, -1},
    {582, 92, -1},
    {596, 67, -1},
    {609, 185, -1},
    {621, 107, -1},
    {632, 170, -1},
    {644, 172, -1},
    {657, 43, -1},
    {670, 35, -1},
    {682, 22, -1},
    {696, 146, -1},
    {710, 154, -1},
    {719, 101, -1},
    {728, 163, -1},
    {741, 124, -1},
    {751, 109, -1},
    {761, 79, -1},
    {778, 103, -1},
    {788, 75, -1},
    {794, 60, -1},
    {810, 181, -1},
    {825, 125, -1},
    {840, 69, -1},
    {855, 123, -1},
    {872, 128, -1},
    {884, 29, -1},
    {894, 94, -1},
    {904, 151, -1},
    {914, 51, -1},
    {925, 12, -1},
    {935, 141, -1},
    {953, 180, -1},
    {964, 102, -1},
    {980, 148, -1},
    {1000, 134, -1},
    {1013, 159, -1},
    {1024, 37, -1},
    {1034, 82, -1},
    {1052, 120, -1},
    {1060, 168, -1},
    {1073, 155, -1},
    {1084, 26, -1},
    {1094, 188, -1},
    {1103, 46, -1},
    {1116, 54, -1},
    {1129, 129, -1},
    {1140, 56, -1},
    {1154, 85, -1},
    {1160, 171, -1},
    {1177, 169, -1},
    {1191, 66, -1},
    {1201, 32, -1},
    {1213, 176, -1},
    {1222, 86, -1},
    {1232, 117, -1},
    {1251, 116, -1},
    {1267, 115, -1},
    {1284, 114, -1},
    {1305, 113, -1},
    {1319, 106, -1},
    {1329, 70, -1},
    {1335, 15, -1},
    {1346, 160, -1},
    {1357, 42, -1},
    {1367, 55, -1},
    {1381, 41, -1},
    {1393, 91, -1},
    {1402, 23, -1},
    {1417, 166, -1},
    {1431, 153, -1},
    {1442, 87, -1},
    {1455, 38, -1},
    {1467, 16, -1},
    {1481, 20, -1},
    {1492, 156, -1},
    {1506, 137, -1},
    {1515, 25, -1},
    {1532, 21, -1},
    {1549, 88, -1},
    {1553, 98, -1},
    {1565, 165, -1},
    {1573, 174, -1},
    {1587, 143, -1},
    {1601, 96, -1},
    {1616, 149, -1},
    {1629, 19, -1},
    {1640, 112, -1},
    {1651, 145, -1},
    {1662, 2, -1},
    {1677, 30, -1},
    {1687, 76, -1},
    {1698, 167, -1},
    {1712, 9, -1},
    {1723, 5, -1},
    {1736, 31, -1},
    {1745, 179, -1},
    {1755, 64, -1},
    {1768, 40, -1},
    {1778, 84, -1},
    {1791, 164, -1},
    {1800, 11, -1},
    {1810, 7, -1},
    {1822, 126, -1},
    {1835, 36, -1},
    {1846, 44, -1},
    {1857, 63, -1},
    {1873, 58, -1},
    {1887, 78, -1},
    {1899, 62, -1},
    {1910, 133, -1},
    {1921, 189, -1},
    {1939, 110, -1},
    {1953, 119, -1},
    {1963, 13, -1},
    {1976, 83, -1},
    {1986, 175, -1},
    {1998, 74, -1},
    {2010, 99, -1},
    {2021, 68, -1},
    {2034, 178, -1},
    {2048, 1, -1},
    {2064, 65, -1},
    {2074, 139, -1},
    {2089, 152, -1},
    {2104, 177, -1},
    {2121, 61, -1},
    {2135, 183, -1},
    {2145, 53, -1},
    {2150, 97, -1},
    {2157, 157, -1},
    {2167, 158, -1},
    {2179, 33, -1},
    {2194, 93, -1},
    {2206, 100, -1},
    {2219, 108, -1},
    {2226, 72, -1},
    {2240, 27, -1},
    {2250, 161, -1},
    {2263, 10, -1},
    {2275, 104, -1},
    {2285, 121, -1},
    {2298, 173, -1},
};

// 名字块按名字升序 ⇒ 下面的查找走二分（表最大 960 条，无脑线性扫也能过，
// 但二分让「每帧查几次」的模组不吃亏；前提是同一份升序，见生成器的排序）。
constexpr IsaacNameTable kIsaacNameTables[] = {
    {kCollectibleNameBlob, kCollectibleNameEntries, sizeof(kCollectibleNameEntries) / sizeof(kCollectibleNameEntries[0])},
    {kCardNameBlob, kCardNameEntries, sizeof(kCardNameEntries) / sizeof(kCardNameEntries[0])},
    {kPillEffectNameBlob, kPillEffectNameEntries, sizeof(kPillEffectNameEntries) / sizeof(kPillEffectNameEntries[0])},
    {kPlayerTypeNameBlob, kPlayerTypeNameEntries, sizeof(kPlayerTypeNameEntries) / sizeof(kPlayerTypeNameEntries[0])},
    {kChallengeNameBlob, kChallengeNameEntries, sizeof(kChallengeNameEntries) / sizeof(kChallengeNameEntries[0])},
    {kTrinketNameBlob, kTrinketNameEntries, sizeof(kTrinketNameEntries) / sizeof(kTrinketNameEntries[0])},
};

std::int32_t LookupInTable(const IsaacNameTable& table, const char* name,
                           std::size_t length, bool alternate) noexcept {
    std::size_t low = 0;
    std::size_t high = table.count;
    while (low < high) {
        const std::size_t middle = low + (high - low) / 2;
        const char* candidate = table.blob + table.entries[middle].nameOffset;
        const std::size_t candidate_length = std::strlen(candidate);
        const std::size_t shorter = length < candidate_length ? length : candidate_length;
        const int order = std::memcmp(name, candidate, shorter);
        // 前缀相同时短的那个排在前面（与生成器的字典序一致）。
        const int verdict = order != 0 ? order
                                       : (length < candidate_length ? -1
                                          : (length > candidate_length ? 1 : 0));
        if (verdict == 0) {
            return alternate ? table.entries[middle].alternateId
                             : table.entries[middle].id;
        }
        if (verdict < 0) {
            high = middle;
        } else {
            low = middle + 1;
        }
    }
    return -1;
}

} // namespace

const IsaacNameTable* IsaacNameTables(std::size_t* count) noexcept {
    if (count != nullptr) {
        *count = sizeof(kIsaacNameTables) / sizeof(kIsaacNameTables[0]);
    }
    return kIsaacNameTables;
}

std::int32_t LookupIsaacName(IsaacNameKind kind, const char* name,
                             std::size_t length, bool alternate) noexcept {
    std::size_t count = 0;
    const IsaacNameTable* tables = IsaacNameTables(&count);
    const auto index = static_cast<std::size_t>(kind);
    if (tables == nullptr || name == nullptr || length == 0 || index >= count) {
        return -1;
    }
    return LookupInTable(tables[index], name, length, alternate);
}

} // namespace isaac::runtime
