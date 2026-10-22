-- Variables shared locally within the mod
-- (were originally sort-of-locals inside of the singular main.lua)
local sharedVars = {}

sharedVars.Game = Game()
sharedVars.Sfx = SFXManager()
sharedVars.Music = MusicManager()
sharedVars.ItemConfig = Isaac.GetItemConfig()
 -- for autocomplete, set by basic.lua
---@type Room
sharedVars.Room = room
---@type Level
sharedVars.Level = level
if false then -- for vscode autocompletion, do not actually run as it gets metatable'd, see after
    ---@type EntityPlayer[]
    sharedVars.Players = {}
end

setmetatable(sharedVars, {
    __index = function(self, key)
        if key == "Players" then
            -- Do not actually keep players in memory to avoid crashes
            -- and running it in a callback risked players being nil
            -- for things that run before it in a run, or invalid for 
            -- things that run before it in general
            return StageAPI.GetPlayers()
        elseif key == "Room" or key == "Level" then
            -- 首次原生实体生成可能早于 NEW_ROOM；按需获取真实对象并缓存。
            -- 后续 basic.lua 的 NEW_ROOM 赋值仍直接覆盖缓存，Players 保持动态。
            local value
            if key == "Room" then
                value = self.Game:GetRoom()
            else
                value = self.Game:GetLevel()
            end
            rawset(self, key, value)
            return value
        end
    end
})

return sharedVars
