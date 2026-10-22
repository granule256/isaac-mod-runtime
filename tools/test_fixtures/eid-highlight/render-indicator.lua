local playerRGB = { {1,0.6,0.6}, {0.5,0.75,1}, {0.9, 0.9, 0.5}, {0.5,1,0.75} }
function EID:renderIndicator(entity, playerNum)
	if EID.Config["Indicator"] == "none" then
		return
	end
	local repDiv = 1
	local entityPos = Isaac.WorldToScreen(entity.PositionOffset and entity.Position + entity.PositionOffset or entity.Position)
	local ArrowOffset = Vector(0, -35)
	if entity.Variant == 100 and not entity:ToPickup():IsShopItem() then
		ArrowOffset = Vector(0, -62)
	end
	local arrowPos = Isaac.WorldToScreen(entity.Position + ArrowOffset)
	entityPos = entityPos + (EID:getEntityData(entity, "EID_RenderOffset") or Vector(0,0))

	-- Move highlights a bit to fit onto the alt Item layout of Flip / Tainted Laz
	if EID.isRepentance and not EID:IsGridEntity(entity) then
		if entity.Variant == 100 and EID:PlayersHaveCollectible(CollectibleType.COLLECTIBLE_FLIP) and EID:getEntityData(entity, "EID_FlipItemID") then
			entityPos = entityPos + Vector(2.5,2.5)
		end
	end
	local sprite = nil
	if not EID:IsGridEntity(entity) then sprite = entity:GetSprite() end
	if EID.isRepentance then
		repDiv = 255
		if EID.isMirrorRoom then
			local screenCenter = EID:getScreenSize()/2
			entityPos.X = entityPos.X - (entityPos-screenCenter).X * 2
			arrowPos.X = arrowPos.X - (arrowPos-screenCenter).X * 2
			if sprite then sprite.FlipX = true end
		end
	end

	-- Don't apply sprite.Color changes to Effects (Dice Floors, Card Reading Portals), use Arrow instead
	if EID.Config["Indicator"] == "arrow" or entity.Type == 1000 or sprite == nil then
		ArrowSprite:RenderLayer(playerNum-1, arrowPos, nullVector, nullVector)
	else
		local colorMult = {1,1,1}
		local framecount = entity.FrameCount or game:GetFrameCount()
		if EID.isMultiplayer then colorMult = playerRGB[playerNum] end
		if EID.Config["Indicator"] == "blink" then
			local c = 255 - math.floor(255 * ((framecount % 40) / 40))
			local r, g, b = math.floor(c*colorMult[1]), math.floor(c*colorMult[2]), math.floor(c*colorMult[3])
			sprite.Color = Color(1, 1, 1, 1, r/repDiv, g/repDiv, b/repDiv)
			EID:RenderEntity(entity, sprite, entityPos)
			sprite.Color = Color(1, 1, 1, 1, 0, 0, 0)
		else
			if EID.Config["Indicator"] == "highlight" then
				local c = 255 - math.floor(255 * ((framecount % 40) / 40))
				local r, g, b = math.floor(c*colorMult[1]), math.floor(c*colorMult[2]), math.floor(c*colorMult[3])
				sprite.Color = Color(1, 1, 1, 1, r/repDiv, g/repDiv, b/repDiv)
			elseif EID.Config["Indicator"] == "border" then
				local c = 255
				local r, g, b = math.floor(c*colorMult[1]), math.floor(c*colorMult[2]), math.floor(c*colorMult[3])
				sprite.Color = Color(1, 1, 1, 1, r/repDiv, g/repDiv, b/repDiv)
			end
			EID:RenderEntity(entity, sprite, entityPos + Vector(0, 1))
			EID:RenderEntity(entity, sprite, entityPos + Vector(0, -1))
			EID:RenderEntity(entity, sprite, entityPos + Vector(1, 0))
			EID:RenderEntity(entity, sprite, entityPos + Vector(-1, 0))
			sprite.Color = Color(1, 1, 1, 1, 0, 0, 0)
			EID:RenderEntity(entity, sprite, entityPos)
		end
	end
	if EID.isMirrorRoom then
		if sprite then sprite.FlipX = false end
	end
end

