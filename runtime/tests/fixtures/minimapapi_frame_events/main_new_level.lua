function MinimapAPI:updatePlayerPos()
	local currentroom = cache.RoomDescriptor
	if currentroom.GridIndex < 0 then
		playerMapPos = Vector(-32768,-32768)
	elseif Isaac.GetChallenge() == Challenge.CHALLENGE_APRILS_FOOL then
		local level = game:GetLevel()
		local randomRoom = level:GetRooms():Get(level:GetRoomByIdx(level:GetRandomRoomIndex(false, cache.RoomDescriptor.DecorationSeed), MinimapAPI.CurrentDimension).ListIndex)
		playerMapPos = MinimapAPI:GridIndexToVector(randomRoom.GridIndex) + MinimapAPI.RoomShapeGridPivots[randomRoom.Data.Shape]
	else
		playerMapPos = MinimapAPI:GridIndexToVector(currentroom.GridIndex) + MinimapAPI.RoomShapeGridPivots[currentroom.Data.Shape]
	end
	MinimapAPI:RunPlayerPosCallbacks()
end

function MinimapAPI:IsBadLoad()
	local spr = Sprite()
	spr:Load("gfx/ui/minimap1.anm2", true)
	spr:SetFrame("RoomUnvisited", 0)
	spr:SetLastFrame()
	return spr:GetFrame() ~= 0
end

MinimapAPI:AddCallbackFunc(ModCallbacks.MC_POST_NEW_LEVEL, CALLBACK_PRIORITY, function(_)
	MinimapAPI:ClearLevels()
	MinimapAPI:LoadDefaultMap()
	MinimapAPI:updatePlayerPos()
	MinimapAPI:UpdateExternalMap()
end)

