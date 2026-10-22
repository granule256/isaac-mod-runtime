local mod = RegisterMod("Cycling Items API", 1)
CyclingItemsAPI = mod
local game = Game()
local rng = RNG()
local json = require("json")
CyclingItemsAPI.CyclingItems = {}

local DEFAULT_CYCLE_COOLDOWN = 36
-- for Binge Eater
local FOOD_ITEMS = {707, 22, 23, 24, 25, 26, 346, 456} 

---@enum CycleFlags
local CycleFlags = {
    FLAG_ISAAC_SPECIAL = 1,     -- 1 more options from room's pool (T. Isaac or Isaac + Birthright)
    FLAG_BINGE_EATER = 2,       -- 1 more option from Binge Eater's pool
    FLAG_GLITCHED_CROWN = 4,    -- 4 more options, faster cycling
    NUM_FLAGS = 8
}

local function getRandomFromPool(pool)
    rng:SetSeed(Random() + 1, 1)
    local roll = rng:RandomInt(#pool) + 1

    return pool[roll]
end

local function roomToPool(room)
    -- ItemPool:GetPoolForRoom() doesn't seem to work correctly, so this serves as a substitute
    -- taken from Repentance Plus
    local rt = room:GetType()
    local ip
    
    if rt == 2 or rt == 22 then ip = 1
    elseif rt == 5 then ip = 2
    elseif rt == 7 or rt == 8 then ip = 5
    elseif rt == 10 then ip = 12
    elseif rt == 14 then ip = 3
    elseif rt == 15 then ip = 4
    elseif rt == 24 then ip = 26
    elseif rt == 29 then ip = 24
    elseif rt == 12 then ip = 6
    else ip = 0
    end

    return ip
end

---@return CycleFlags
local function getCyclingFlags()
    local flags = CycleFlags.NUM_FLAGS

    for i = 0, game:GetNumPlayers() - 1 do
        local player = Isaac.GetPlayer(i)

        if player:HasCollectible(CollectibleType.COLLECTIBLE_GLITCHED_CROWN) then
            flags = flags | CycleFlags.FLAG_GLITCHED_CROWN
        elseif player:GetPlayerType() == 21 or (player:GetPlayerType() == 0 and player:HasCollectible(CollectibleType.COLLECTIBLE_BIRTHRIGHT)) then
            flags = flags | CycleFlags.FLAG_ISAAC_SPECIAL
        end

        if player:HasCollectible(CollectibleType.COLLECTIBLE_BINGE_EATER) then
            flags = flags | CycleFlags.FLAG_BINGE_EATER
        end
    end

    return flags
end

---@param numOptions integer
---@param cd integer
---@return integer
local function adjustCycleCooldown(numOptions, cd)
    if numOptions > 8 then
        -- 1 frame, impossible to catch (only used as one of the fully charged Everything Jar's effects in vanilla)
        return DEFAULT_CYCLE_COOLDOWN / 36
    elseif numOptions > 4 then
        -- 6 frames, very hard to catch (Glitched Crown)
        return math.min(DEFAULT_CYCLE_COOLDOWN / 6, cd)
    end

    return cd
end

---@return EntityPickup
function CyclingItemsAPI:spawnTestItem()
    return Isaac.Spawn(5, 100, -1, Isaac.GetFreeNearPosition(Isaac.GetPlayer(0).Position, 40), Vector.Zero, nil):ToPickup()
end

---@param collectible Entity
---@param optionPool table | ItemPoolType | number | string
---@param ignoreCycleFlags? boolean @default false
---@param ignoreCooldowns? boolean @default false
function CyclingItemsAPI:addCyclingOption(collectible, optionPool, ignoreCycleFlags, ignoreCooldowns)
    --[[
        *collectible - `EntityPickup`. what collectible to add option to?

        *optionPool - can be provided in multiple types:
            `table`. random item is then chosen from this table via getRandomFromPool() when assigning item options (basically a custom pool).
            `number`. referes to the ItemPoolType game enum (0 - Treasure Room, 1 - Shop etc.).
            `string "roompool" or "room"`. random item from the current room's pool is the chosen when assigning item options.

        *ignoreCycleFlags - `boolean`.
        DEFAULT: false
        allows you to ignore cycling mechanics provided by the base game when making an option pedestal (see CycleFlags enum for reference).
        
        *ignoreCooldowns - `boolean`. true to ignore the following mechanic, false otherwise:
        in vanilla, item pedestal cycles every frame (30 times a second) if there's 9 or more options in it,
        and every 6 frames (5 times a second) if there's 5-8 options.
        DEFAULT: false
    ]]

    ignoreCycleFlags = ignoreCycleFlags or false
    ignoreCooldowns = ignoreCooldowns or false

    local data = CyclingItemsAPI:getPedestalCycleData(collectible.Position)
    local id = game:GetLevel():GetCurrentRoomIndex()

    if not data then
        table.insert(CyclingItemsAPI.CyclingItems, {roomIndex = id, itemPos = {collectible.Position.X, collectible.Position.Y},
                                itemOptions = {collectible.SubType}, itemCycleCooldown = DEFAULT_CYCLE_COOLDOWN})
    end

    for _, val in pairs(CyclingItemsAPI.CyclingItems) do
        if val.roomIndex == id then
            local v = Vector(val.itemPos[1], val.itemPos[2])

            if v:Distance(collectible.Position) < 5 then
                -- add more options, because this is our pedestal
                if type(optionPool) == "number" then
                    table.insert(val.itemOptions, game:GetItemPool():GetCollectible(optionPool, true, Random() + 1, CollectibleType.COLLECTIBLE_NULL))
                elseif type(optionPool) == "table" then
                    table.insert(val.itemOptions, getRandomFromPool(optionPool))
                elseif optionPool == "roompool" or optionPool == "room" then
                    table.insert(val.itemOptions, game:GetItemPool():GetCollectible(roomToPool(game:GetRoom()), true, Random() + 1, CollectibleType.COLLECTIBLE_NULL))
                end

                if not ignoreCycleFlags then
                    if getCyclingFlags() & CycleFlags.FLAG_ISAAC_SPECIAL == CycleFlags.FLAG_ISAAC_SPECIAL then
                        table.insert(val.itemOptions, game:GetItemPool():GetCollectible(roomToPool(game:GetRoom()), true, Random() + 1, CollectibleType.COLLECTIBLE_NULL))
                    end
            
                    if getCyclingFlags() & CycleFlags.FLAG_BINGE_EATER  == CycleFlags.FLAG_BINGE_EATER then
                        table.insert(val.itemOptions, getRandomFromPool(FOOD_ITEMS))
                    end
            
                    if getCyclingFlags() & CycleFlags.FLAG_GLITCHED_CROWN == CycleFlags.FLAG_GLITCHED_CROWN then
                        for i = 1, 4 do
                            table.insert(val.itemOptions, game:GetItemPool():GetCollectible(roomToPool(game:GetRoom()), true, Random() + 1, CollectibleType.COLLECTIBLE_NULL))
                        end
            
                        val.itemCycleCooldown = DEFAULT_CYCLE_COOLDOWN / 6
                    end
                end

                -- adjust cooldown
                if not ignoreCooldowns then
                    val.itemCycleCooldown = adjustCycleCooldown(#val.itemOptions, val.itemCycleCooldown)
                end
            end
        end
    end
end

---@param pos? Vector
---@param numOptions? integer @default 2
---@param optionPools? table @default {0, 0}
---@param cycleCooldown? integer @default 36
---@param ignoreCycleFlags? boolean @default false
---@param ignoreCooldowns? boolean @default false
---@return Entity
function CyclingItemsAPI:createCyclingPedestal(pos, numOptions, optionPools, cycleCooldown, ignoreCycleFlags, ignoreCooldowns)
    --[[
        *pos - `Vector`. where to create the new pedestal in a current room?
        DEFAULT: near the main player

        *numOptions - `number`. how many options to create?
        DEFAULT: 2

        *optionPools - `table`. what pools to grab options from?
        DEFAULT: {0, 0} (2 Treasure items)
        table can hold tables, numbers or "roompool"/"pool" strings as elements.
        see the optionPool param in addCyclingOption() for a reference on how to handle that.
        ! if more pools than options is provided, only the first X pools will be used for options.
        ! if less pools than options is provided, the last pool provided will be duplicated for all options left.

        *cycleCooldown - `number`. how fast will items cycle on a pedestal?
        DEFAULT: 36

        *ignoreCycleFlags - `boolean`.
        DEFAULT: false
        see the ignoreCycleFlags param in addCyclingOption() for a reference on how to handle that.
        
        *ignoreCooldowns - `boolean`.
        DEFAULT: false
        see the ignoreCooldowns param in addCyclingOption() for a reference on how to handle that.

        *RETURNS: `Entity` - item spawned.
    ]]

    pos = pos or Isaac.GetFreeNearPosition(Isaac.GetPlayer(0).Position, 40)
    numOptions = numOptions or 2
    optionPools = optionPools or {0, 0}
    cycleCooldown = cycleCooldown or DEFAULT_CYCLE_COOLDOWN
    ignoreCycleFlags = ignoreCycleFlags or false
    ignoreCooldowns = ignoreCooldowns or false
    
    if numOptions > #optionPools then
        print("Less pools than options provided! Duplicating the last given pool for " .. tostring(numOptions - #optionPools) .. " collectible option(s) left.")
        local poolToFill = optionPools[#optionPools]

        for i = 1, numOptions - #optionPools do
            table.insert(optionPools, poolToFill)
        end
    elseif numOptions < #optionPools then
        print("More pools than options provided! Only the first " .. tostring(numOptions) .. " pool(s) will be assigned to their collectible option(s).")
    end

    if not ignoreCycleFlags then
        if getCyclingFlags() & CycleFlags.FLAG_ISAAC_SPECIAL == CycleFlags.FLAG_ISAAC_SPECIAL then
            numOptions = numOptions + 1
            table.insert(optionPools, "room")
        end

        if getCyclingFlags() & CycleFlags.FLAG_BINGE_EATER  == CycleFlags.FLAG_BINGE_EATER then
            numOptions = numOptions + 1
            table.insert(optionPools, FOOD_ITEMS)
        end

        if getCyclingFlags() & CycleFlags.FLAG_GLITCHED_CROWN == CycleFlags.FLAG_GLITCHED_CROWN then
            numOptions = numOptions + 4
            for i = 1, 4 do
                table.insert(optionPools, "room")
            end

            cycleCooldown = DEFAULT_CYCLE_COOLDOWN / 6
        end
    end

    local resOptions = {}
    for i = 1, numOptions do
        local currentPool = optionPools[i]

        if type(currentPool) == "number" then   -- vanilla item pool
            table.insert(resOptions, game:GetItemPool():GetCollectible(currentPool, true, Random() + 1, CollectibleType.COLLECTIBLE_NULL))
        elseif type(currentPool) == "table" then    -- custom item pool
            table.insert(resOptions, getRandomFromPool(currentPool))
        elseif currentPool == "roompool" or currentPool == "room" then
            table.insert(resOptions, game:GetItemPool():GetCollectible(roomToPool(game:GetRoom()), true, Random() + 1, CollectibleType.COLLECTIBLE_NULL))
        end

    end

    if not ignoreCooldowns then
        cycleCooldown = adjustCycleCooldown(numOptions, cycleCooldown)
    end

    table.insert(CyclingItemsAPI.CyclingItems, {roomIndex = game:GetLevel():GetCurrentRoomIndex(), itemPos = {pos.X, pos.Y},
                                itemOptions = resOptions, itemCycleCooldown = cycleCooldown})

    return Isaac.Spawn(5, 100, resOptions[1], pos, Vector.Zero, nil)
end

---@param pos Vector
---@return table | nil
function CyclingItemsAPI:getPedestalCycleData(pos)
    --[[
        *pos - `Vector`. from where to check the pedestal IN THE CURRENT ROOM?

        *RETURNS: `table` (CyclingItemsAPI.CyclingItems table entry) if the item is found, `nil` otherwise.
        table contains:
            roomIndex: room index (number);
            itemPos: position (table {X, Y});
            itemOptions: options contained within a pedestal (table of numbers);
            itemCycleCooldown: cycle cooldown (number).
    ]]

    local id = game:GetLevel():GetCurrentRoomIndex()

    for _, val in pairs(CyclingItemsAPI.CyclingItems) do
        if val.roomIndex == id then
            local v = Vector(val.itemPos[1], val.itemPos[2])

            if v:Distance(pos) < 5 then
                return val
            end
        end
    end

    return nil
end

---@return table
function CyclingItemsAPI:findCyclingItems()
    --[[
        *RETURNS: `table` containing all cycling pedestals in a room.
        if there are no cycling pedestals, returns an empty table.
        ! does NOT register items that are cycling naturally without this mod interfering (Binge Eater, Soul of Isaac etc.).
    ]]

    local t = {}

    for _, p in pairs(Isaac.FindByType(5, 100)) do
        if p:ToPickup() and p.SubType ~= 0
        and CyclingItemsAPI:getPedestalCycleData(p.Position) then
            table.insert(t, p:ToPickup())
        end
    end

    return t
end

---@param item Entity | EntityPickup
function CyclingItemsAPI:rerollAllOptions(item)
    --[[
        *item - `Entity` | `EntityPickup`. pedestal for which one wants to reroll all options.
        if the pedestal isn't cycling via this API, does nothing.
        ! all options are rerolled into random items from the current room's pool, with no customization.

        is used to handle re-roll mechanics from the base game (breaks the cycling if not used):
            works for D6, D100, D Infinity, Perthro (via Clear Rune as well).
            ! does NOT work for Blank Rune that acted as a Perthro.
    ]]

    local data = CyclingItemsAPI:getPedestalCycleData(item.Position)

    if data then
        for i, v in pairs(data.itemOptions) do
            v = game:GetItemPool():GetCollectible(roomToPool(game:GetRoom()), true, Random() + 1, CollectibleType.COLLECTIBLE_NULL)
            data.itemOptions[i] = v
        end
    end
end

---@param item Entity | EntityPickup
---@param newCooldown number
function CyclingItemsAPI:setCyclingCooldown(item, newCooldown)
    --[[
        *item - `Entity` | `EntityPickup`. pedestal for which one wants to set a new cycling cooldown.
        if the pedestal isn't cycling via this API, does nothing.

        *newCooldown - `number`. new cycling cooldown.
    ]]

    local data = CyclingItemsAPI:getPedestalCycleData(item.Position)

    if data and newCooldown then
        data.itemCycleCooldown = newCooldown
    end
end


--* SAVE MANAGERS
---@param isContinued boolean
function CyclingItemsAPI:OnGameStart(isContinued)
    if not isContinued or not Isaac.HasModData(CyclingItemsAPI) then
        CyclingItemsAPI.CyclingItems = {}
    else
        CyclingItemsAPI.CyclingItems = json.decode(Isaac.LoadModData(CyclingItemsAPI))
    end
end
CyclingItemsAPI:AddCallback(ModCallbacks.MC_POST_GAME_STARTED, CyclingItemsAPI.OnGameStart)

---@param shouldSave boolean
function CyclingItemsAPI:PreGameExit(shouldSave)
    if shouldSave then
	    Isaac.SaveModData(CyclingItemsAPI, json.encode(CyclingItemsAPI.CyclingItems, "CyclingItems"))
    end
end
CyclingItemsAPI:AddCallback(ModCallbacks.MC_PRE_GAME_EXIT, CyclingItemsAPI.PreGameExit)
--*

--* THE CORE
---@param entityPickup EntityPickup
function mod:PickupUpdate(entityPickup)
    if entityPickup.Touched or entityPickup.SubType == 0 then return end

    local data = CyclingItemsAPI:getPedestalCycleData(entityPickup.Position)

    if data and entityPickup.FrameCount % data.itemCycleCooldown == 0 then
        local currentOption = 1

        for i, v in pairs(data.itemOptions) do
            if entityPickup.SubType == v then 
                currentOption = i
            end
        end

        local next = currentOption < #data.itemOptions and data.itemOptions[currentOption + 1] or data.itemOptions[1]
        local s = entityPickup:GetSprite()
        local f = s:GetFrame()
        
        entityPickup:Morph(5, 100, next, true, false, true)
        -- thanks to Xalum for telling me how to get rid of the buffer after Morph
        entityPickup.Wait = 0
        s:SetFrame(f)
    end

end
mod:AddCallback(ModCallbacks.MC_POST_PICKUP_UPDATE, mod.PickupUpdate, PickupVariant.PICKUP_COLLECTIBLE)
--*

---@param Item CollectibleType | integer
---@param RNG RNG
---@param Player EntityPlayer
---@param UseFlags UseFlag | integer
---@param Slot ActiveSlot | integer
---@param CustomVarData integer
function mod:HandleItemReroll(Item, RNG, Player, UseFlags, Slot, CustomVarData)
    if UseFlags & UseFlag.USE_CARBATTERY > 0 then
        for _, item in pairs(Isaac.FindByType(5, 100)) do
            if item.SubType > 0 then
                CyclingItemsAPI:addCyclingOption(item, "room")
            end
        end
    end
    
    if #CyclingItemsAPI:findCyclingItems() > 0 then

        for _, item in pairs(CyclingItemsAPI:findCyclingItems()) do
            CyclingItemsAPI:rerollAllOptions(item)
            item:Morph(5, 100, CyclingItemsAPI:getPedestalCycleData(item.Position).itemOptions[1], true, false, true)
        end
    end
end
mod:AddCallback(ModCallbacks.MC_USE_ITEM, mod.HandleItemReroll, CollectibleType.COLLECTIBLE_D6)

---@param MyCard Card | integer
---@param Player EntityPlayer
---@param UseFlags UseFlag | integer
function mod:HandleCardReroll(MyCard, Player, UseFlags)
    if #CyclingItemsAPI:findCyclingItems() > 0 then

        for _, item in pairs(CyclingItemsAPI:findCyclingItems()) do
            CyclingItemsAPI:addCyclingOption(item, "room", false)
        end
    end
end
mod:AddCallback(ModCallbacks.MC_USE_CARD, mod.HandleCardReroll, Card.CARD_SOUL_ISAAC)

return CyclingItemsAPI