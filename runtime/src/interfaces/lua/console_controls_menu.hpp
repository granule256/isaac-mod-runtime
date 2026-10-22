#pragma once

// 运行时自有平台设置，不修改MCM作者文件、不增加Lua逐帧回调。
inline constexpr char kConsoleControlsMenuScript[] = R"lua(
local m, api = ModConfigMenu, SwitchConsole
if not m or m.SwitchConsoleSettingsInstalled then return end
local keys = {4,5,6,7,8,11,9,12,10,13,0,1,2,3}
local names = {"A","B","X","Y","L","R","ZL","ZR","LS","RS","Left","Right","Up","Down"}
local function current(slot)
    local first, second = api.GetControls()
    local value = slot == 1 and first or second
    if value == 255 then return 0 end
    for index, code in ipairs(keys) do if code == value then return index end end
    return slot
end
for slot = 1, 2 do
    m.AddSetting("Console", "Controls", {
        Type = m.OptionType.NUMBER, Minimum = slot == 1 and 1 or 0, Maximum = #keys, ModifyBy = 1,
        Default = slot,
        CurrentSetting = function() return current(slot) end,
        Display = function()
            local index = current(slot)
            return "Open button " .. slot .. ": " .. (names[index] or "None")
        end,
        OnChange = function(index)
            local a,b,t = api.GetControls()
            local code = keys[index] or 255
            if slot == 1 then a = code else b = code end
            api.SetControls(a,b,t)
        end,
        Info = {"Hold both buttons to open the console.", "Button 2: None uses a single button.",
                "Use buttons different from the MCM shortcut."}
    })
end
m.AddSetting("Console", "Controls", {
    Type = m.OptionType.NUMBER, Minimum = 2, Maximum = 50, ModifyBy = 1, Default = 8,
    CurrentSetting = function() local _,_,t = api.GetControls(); return t end,
    Display = function() local _,_,t = api.GetControls(); return string.format("Hold time: %.1f s",t/10) end,
    OnChange = function(t) local a,b = api.GetControls(); api.SetControls(a,b,t) end,
    Info = {"Hold continuously for 0.2 to 5.0 seconds.", "Changes are saved automatically."}
})
m.AddSetting("Console", "Controls", {
    Type = m.OptionType.BOOLEAN, CurrentSetting = function() return false end,
    Display = function() return "Reset controls to A+B / 0.8 s" end,
    OnChange = function() api.SetControls(4,5,8) end,
    Info = {"Restore the default console shortcut."}
})
m.SwitchConsoleSettingsInstalled = true
)lua";
