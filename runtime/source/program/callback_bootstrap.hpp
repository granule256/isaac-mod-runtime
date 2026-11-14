#pragma once
// PC Callbacks（main.lua SHA ae0efa…）；默认匹配内联，执行仍读取共享表。
namespace isaac::runtime {
inline constexpr char kPcCallbackBootstrap[] = R"pc(local invoke, changed, ownerMatches, nativeInvoke, nextMatching, extendedPolicy = ...
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
-- Keep custom ipairs iterators live; only the fixed Lua array iterator uses the direct loop.
local standardIterator = ipairs({})

-- Function objects are created once at bootstrap, never per rendered entity.
local function InvokeRender(invoke, id, entry, offset, entity, ignored, ...)
    local result = invoke(id, entry, entity, offset, ...)
    if result == false then return false, offset end
    if result ~= nil and type(result) ~= "boolean" and result.X and result.Y then
        offset = offset + result
    end
    return nil, offset
end

local function MakeRunner(invoke, nextMatching)
 return function(callbackId, param, ...)
    local callbacks = Callbacks[callbackId]
    if callbacks then
        local matchFunc = getmetatable(callbacks).__matchParams or defaultCallbackMeta.__matchParams
        local useDefault = matchFunc == originalDefaultMatch
        local iterator, iteratorState, iteratorIndex = ipairs(callbacks)
        if iterator == standardIterator and iteratorState == callbacks and iteratorIndex == 0 then
          if nextMatching and useDefault and param and param ~= -1 then
            local index = 0
            while true do
                index = index + 1
                local v = callbacks[index]
                if v == nil then break end
                local p = v.Param
                if not p or p == -1 or param == p then
                    local result = invoke(callbackId, v, ...)
                    if result ~= nil then return result end
                else
                    -- Param was already read. Scan after it and do not re-read
                    -- the matching entry's potentially live getter.
                    local nextIndex, nextEntry = nextMatching(callbacks, index, param)
                    if nextIndex == nil then break end
                    index, v = nextIndex, nextEntry
                    local result = invoke(callbackId, v, ...)
                    if result ~= nil then return result end
                end
            end
          else
            local index = 0
            while true do
                index = index + 1
                local v = callbacks[index]
                if v == nil then break end
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
        else
            for _, v in iterator, iteratorState, iteratorIndex do
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
end

-- Ordinary callbacks retain their original runner, including the OFF hot path.
local mutations = extendedPolicy and {}
local removedNext = extendedPolicy and setmetatable({}, {__mode="k"})
local function IsExtensionList(id)
    return extendedPolicy and type(id)=="number" and id>=1000 and extendedPolicy(id)
end
local function MarkRemoved(id, callbacks, index)
    if IsExtensionList(id) then
        removedNext[callbacks[index]]=callbacks[index+1] or false
        mutations[id]=(mutations[id] or 0)+1
    end
end
local function ResumeAfterMutation(callbacks, entry)
    while entry and removedNext[entry]~=nil do entry=removedNext[entry] end
    if not entry then return #callbacks+1, nil end
    for i=1,#callbacks do
        if callbacks[i]==entry then return i,entry end
    end
    return #callbacks+1,nil
end
local function MakeExtensionRunner(invoke, nextMatching)
    return function(callbackId,param,...)
        local callbacks=Callbacks[callbackId]
        if not callbacks then return end
        local render=callbackId>=1080 and callbackId<=1089
        local activeCharge=callbackId==1073
        local chargeSlot,chargePlayer,chargeValue
        if activeCharge then chargeSlot,chargePlayer,chargeValue=... end
        local offset
        if render then offset=select(2,...) end
        local match=getmetatable(callbacks).__matchParams or defaultCallbackMeta.__matchParams
        local default=match==originalDefaultMatch
        local iterator,state,initial=ipairs(callbacks)
        local standard=iterator==standardIterator and state==callbacks and initial==0
        if standard then
            local index,entry=1,callbacks[1]
            while entry do
                local p=entry.Param
                local matched
                if default then matched=not param or not p or param==-1 or p==-1 or param==p
                else matched=match(param,p) end
                if matched then
                    -- Prefetch before invoking, as the upstream linked iterator does.
                    local nextIndex,following=index+1,callbacks[index+1]
                    if default and nextMatching and param and param~=-1 then
                        nextIndex,following=nextMatching(callbacks,index,param)
                    else
                        while following do
                            local candidate=following.Param
                            local accepted
                            if default then accepted=not param or not candidate or param==-1 or candidate==-1 or param==candidate
                            else accepted=match(param,candidate) end
                            if accepted then break end
                            nextIndex=nextIndex+1;following=callbacks[nextIndex]
                        end
                    end
                    local version=mutations[callbackId] or 0
                    local result
                    if render then result,offset=InvokeRender(invoke,callbackId,entry,offset,...)
                    elseif activeCharge then result=invoke(callbackId,entry,chargeSlot,chargePlayer,chargeValue)
                    else result=invoke(callbackId,entry,...) end
                    if result~=nil then
                        if activeCharge then chargeValue=result else return result end
                    end
                    if (mutations[callbackId] or 0)~=version then
                        nextIndex,following=ResumeAfterMutation(callbacks,following)
                    end
                    index,entry=nextIndex,following
                else
                    if default and nextMatching and param and param~=-1 then
                        index,entry=nextMatching(callbacks,index,param)
                    else index=index+1;entry=callbacks[index] end
                end
            end
        else
            -- Preserve authored custom array iterators and matcher behavior.
            for _,entry in iterator,state,initial do
                local p=entry.Param
                local matched
                if default then matched=not param or not p or param==-1 or p==-1 or param==p
                else matched=match(param,p) end
                if matched then
                    local result
                    if render then result,offset=InvokeRender(invoke,callbackId,entry,offset,...)
                    elseif activeCharge then result=invoke(callbackId,entry,chargeSlot,chargePlayer,chargeValue)
                    else result=invoke(callbackId,entry,...) end
                    if result~=nil then
                        if activeCharge then chargeValue=result else return result end
                    end
                end
            end
        end
        if render then return offset end
        if activeCharge then return chargeValue end
    end
end
local function SelectRunner(invoke,nextMatching)
    local ordinary=MakeRunner(invoke,nextMatching)
    if not extendedPolicy then return ordinary end
    local extension=MakeExtensionRunner(invoke,nextMatching)
    return function(id,param,...)
        if IsExtensionList(id) then return extension(id,param,...) end
        return ordinary(id,param,...)
    end
end
_RunCallback=SelectRunner(invoke)
local RunNative=SelectRunner(nativeInvoke,nextMatching)

function _UnloadMod(mod)
	Isaac.RunCallback(ModCallbacks.MC_PRE_MOD_UNLOAD, mod)
	
	for callbackId,callbacks in pairs(Callbacks) do
		for i=#callbacks,1,-1 do
			if callbacks[i].Mod == mod then
				MarkRemoved(callbackId,callbacks,i)
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
    if IsExtensionList(callbackId) then mutations[callbackId]=(mutations[callbackId] or 0)+1 end
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
				MarkRemoved(callbackId,callbacks,i)
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
