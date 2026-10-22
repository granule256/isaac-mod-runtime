#pragma once
// 固定PC main.lua完整BitSet128 Lua层，原文件SHA256 ae0efa082e0ea8844a6e7a5ab55e4a96a8dc87a8fa046483e590c0677c40cfdf
namespace isaac::runtime {
inline constexpr char kBitSet128Bootstrap[] = R"IsaacLua(local function tobitset128(n)
	if type(n) == "number" then
		return BitSet128(n, 0)
	else
		return n
	end
end

-- BitSet128 -----------------------------------------------
local META_BITSET128 = getmetatable(BitSet128).__class

rawset(META_BITSET128, "__bnot", function(a)
	return BitSet128(~a.l, ~a.h)
end)

rawset(META_BITSET128, "__bor", function(a, b)
	a, b = tobitset128(a), tobitset128(b)
	return BitSet128(a.l|b.l, a.h|b.h)
end)

rawset(META_BITSET128, "__band", function(a, b)
	a, b = tobitset128(a), tobitset128(b)
	return BitSet128(a.l&b.l, a.h&b.h)
end)

rawset(META_BITSET128, "__bxor", function(a, b)
	a, b = tobitset128(a), tobitset128(b)
	return BitSet128(a.l~b.l, a.h~b.h)
end)

rawset(META_BITSET128, "__shl", function(a, b)
	return BitSet128(a.l<<b, (a.h<<b) | (a.l>>(64-b)))
end)

rawset(META_BITSET128, "__shr", function(a, b)
	return BitSet128((a.l>>b) | (a.h<<(64-b)), a.h>>b)
end)

-- god damnit Lua this doesn't work when comparing with a normal number
rawset(META_BITSET128, "__eq", function(a, b)
	a, b = tobitset128(a), tobitset128(b)
	return a.l==b.l and a.h==b.h
end)

rawset(META_BITSET128, "__lt", function(a, b)
	a, b = tobitset128(a), tobitset128(b)
	return a.h<b.h or (a.h==b.h and a.l<b.l)
end)

rawset(META_BITSET128, "__le", function(a, b)
	a, b = tobitset128(a), tobitset128(b)
	return a.h<b.h or (a.h==b.h and a.l<=b.l)
end)

local BitSet128_constructor = getmetatable(BitSet128).__call
getmetatable(BitSet128).__call = function(self, l, h)
	return BitSet128_constructor(self, l or 0, h or 0)
end

)IsaacLua";
}
