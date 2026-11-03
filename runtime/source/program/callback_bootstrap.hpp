#pragma once
// PC Callbacks（main.lua SHA ae0efa…）；默认匹配内联，执行仍读取共享表。
namespace isaac::runtime {
inline constexpr char kPcCallbackBootstrap[] = R"pc(local invoke, changed, ownerMatches, nativeInvoke = ...
nativeInvoke = nativeInvoke or invoke
local debug_getinfo = debug.getinfo
local diagnostic_pcall = pcall

local function checktype(index, val, typ, level)
	local t = type(val)
	if t ~= typ then
		error(string.format("bad argument #%d to '%s' (%s expected, got %s)", index, debug_getinfo(level).name, typ, t), level+1)
	end
end

local function checknumber(index, val, level) checktype(index, val, "number", (level or 2)+1) end
local function checkfunction(index, val, level) checktype(index, val, "function", (level or 2)+1) end
local function checkstring(index, val, level) checktype(index, val, "string", (level or 2)+1) end
local function checktable(index, val, level) checktype(index, val, "table", (level or 2)+1) end

------------------------------------------------------------
-- Callbacks

local Callbacks = {}

local defaultCallbackMeta = {
	__matchParams = function(a, b)
		return not a or not b or a == -1 or b == -1 or a == b
	end
}

local originalDefaultMatch = defaultCallbackMeta.__matchParams

local function MakeRunner(invoke)
 return function(callbackId, param, ...)
    local callbacks = Callbacks[callbackId]
    if callbacks then
        local matchFunc = getmetatable(callbacks).__matchParams or defaultCallbackMeta.__matchParams
        local useDefault = matchFunc == originalDefaultMatch
        for _, v in ipairs(callbacks) do
            local p = v.Param
            local matched
            if useDefault then
                matched = not param or not p or param == -1 or p == -1 or param == p
            else
                matched = matchFunc(param, p)
            end
            if matched then
                local result = invoke(callbackId, v, ...)
                if result ~= nil then return result end
            end
        end
    end
end
end

_RunCallback = MakeRunner(invoke)
local RunNative = MakeRunner(nativeInvoke)

function _UnloadMod(mod)
	Isaac.RunCallback(ModCallbacks.MC_PRE_MOD_UNLOAD, mod)
	
	for callbackId,callbacks in pairs(Callbacks) do
		for i=#callbacks,1,-1 do
			if callbacks[i].Mod == mod then
				table.remove(callbacks, i)
			end
		end
		
		if #callbacks == 0 then
			if type(callbackId) == "number" then
				-- No more functions left, disable this callback
				Isaac.SetBuiltInCallbackState(callbackId, false)
			end
		end
	end
end

rawset(Isaac, "AddPriorityCallback", function(mod, callbackId, priority, fn, param)
	checknumber(3, priority)
	checkfunction(4, fn)
	
	local callbacks = Isaac.GetCallbacks(callbackId, true)
	local wasEmpty = #callbacks == 0
	
	local pos = #callbacks+1
	for i=#callbacks,1,-1 do
		if callbacks[i].Priority <= priority then
			break
		else
			pos = pos-1
		end
	end
	
	table.insert(callbacks, pos, {Mod = mod, Function = fn, Priority = priority, Param = param})
	diagnostic_pcall(changed, callbackId, true)
	
	if wasEmpty then
		if type(callbackId) == "number" then
			-- Enable this callback
			Isaac.SetBuiltInCallbackState(callbackId, true)
		end
	end
end)

rawset(Isaac, "AddCallback", function(mod, callbackId, fn, param)
	checkfunction(3, fn)
	Isaac.AddPriorityCallback(mod, callbackId, CallbackPriority.DEFAULT, fn, param)
end)

rawset(Isaac, "RemoveCallback", function(mod, callbackId, fn)
	checkfunction(3, fn)
	
	local callbacks = Callbacks[callbackId]
	if callbacks then
		for i=#callbacks,1,-1 do
			if callbacks[i].Function == fn then
				table.remove(callbacks, i)
			end
		end
		
		-- No more functions left, disable this callback
		diagnostic_pcall(changed, callbackId)
		if not next(callbacks) then
			if type(callbackId) == "number" then
				Isaac.SetBuiltInCallbackState(callbackId, false)
			end
		end
	end
end)

rawset(Isaac, "GetCallbacks", function(callbackId, createIfMissing)
	if createIfMissing and not Callbacks[callbackId] then
		Callbacks[callbackId] = setmetatable({}, defaultCallbackMeta)
	end
	
	return Callbacks[callbackId] or {}
end)

local RunCallback = _RunCallback

rawset(Isaac, "RunCallbackWithParam", RunCallback)
rawset(Isaac, "RunCallback", function(callbackID, ...) return RunCallback(callbackID, nil, ...) end)

local function RunOwner(callbackId, param, owner, ...)
    local callbacks = Callbacks[callbackId]
    if callbacks then
        local matchFunc = getmetatable(callbacks).__matchParams or defaultCallbackMeta.__matchParams
        local useDefault = matchFunc == originalDefaultMatch
        for _, v in ipairs(callbacks) do
            if ownerMatches(v.Mod, owner) then
                local p = v.Param
                local matched
                if useDefault then
                    matched = not param or not p or param == -1 or p == -1 or param == p
                else
                    matched = matchFunc(param, p)
                end
                if matched then
                    local result = nativeInvoke(callbackId, v, ...)
                    if result ~= nil then return result end
                end
            end
        end
    end
end

return _RunCallback, Callbacks, _UnloadMod, RunOwner, RunNative
)pc";
}
