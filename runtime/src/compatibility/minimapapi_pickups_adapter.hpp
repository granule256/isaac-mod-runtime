#pragma once

namespace isaac::runtime::compatibility {

// Optional behavior enhancement for the two reviewed MiniMAPI layouts.
// It is not a vanilla PC callback or part of the engine's cache ownership.
inline constexpr char kMinimapApiPickupAdapter[] = R"lua(
local get, put, each, size, kind, text = rawget, rawset, next, rawlen, type, tostring
local globals = _G
local protectedVariants = {[41]=true,[340]=true,[370]=true,[380]=true,[390]=true}

local function affected(definition, pickups, collectibles)
    if get(definition, 'Type') ~= 5 then return false end
    local variant = get(definition, 'Variant')
    if kind(variant) ~= 'number' or variant == -1 or protectedVariants[variant] then
        return false
    end
    if variant == 100 then
        local subtype = get(definition, 'SubType')
        return collectibles and subtype ~= 0 and subtype ~= 668
    end
    return pickups
end

local function definitions(list, grid, pickups, collectibles, changed, preserved)
    for _, definition in each, list do
        if kind(definition) == 'table' then
            local id = get(definition, 'IconID')
            if kind(id) == 'string' then
                local target = not grid and affected(definition, pickups, collectibles)
                               and changed or preserved
                target[id] = true
            end
        end
    end
end

return function(pickups, collectibles)
    local api = get(globals, 'MinimapAPI')
    if kind(api) ~= 'table' then return false, 'MiniMAPI is not loaded' end
    local major, minor = get(api, 'MajorVersion'), get(api, 'MinorVersion')
    if major ~= 2 or (minor ~= 59 and minor ~= 62) then
        local version = kind(major) == 'number' and kind(minor) == 'number'
                        and text(major)..'.'..text(minor) or 'unknown'
        return false, 'MiniMAPI '..version..' has not been reviewed by this adapter'
    end
    local pickupsList, grids, levels = get(api, 'PickupList'), get(api, 'GridEntityList'), get(api, 'Levels')
    if kind(pickupsList) ~= 'table' or kind(grids) ~= 'table' or kind(levels) ~= 'table' then
        return false, 'MiniMAPI cache schema is not available'
    end
    local changed, preserved = {}, {}
    definitions(pickupsList, false, pickups, collectibles, changed, preserved)
    definitions(grids, true, pickups, collectibles, changed, preserved)
    for _, rooms in each, levels do
        if kind(rooms) == 'table' then
            for _, room in each, rooms do
                if kind(room) == 'table' and not get(room, 'NoUpdate') and get(room, 'Descriptor') then
                    local icons = get(room, 'ItemIcons')
                    if kind(icons) == 'table' then
                        local count, kept = size(icons), 0
                        for index = 1, count do
                            local id = get(icons, index)
                            if not (changed[id] and not preserved[id]) then
                                kept = kept + 1
                                if kept ~= index then put(icons, kept, id) end
                            end
                        end
                        for index = kept + 1, count do put(icons, index, nil) end
                    end
                end
            end
        end
    end
    return true
end
)lua";

} // namespace isaac::runtime::compatibility
