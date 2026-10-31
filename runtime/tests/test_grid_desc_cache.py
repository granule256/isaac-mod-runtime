"""Production GridDesc aliasing, live reads, weak collection and allocation reduction."""
import unittest
from .test_api500_world import MAIN,run_world

class GridDescCacheTests(unittest.TestCase):
 def test_shared_view_live_fields_weak_gc_and_heap(self):
  extra=r'''
local r=Game():GetRoom()
local a=r:GetGridEntity(3)
local d=a.Desc
local b=r:GetGridEntity(3)
assert(not rawequal(a,b),'grid owner wrapper identity must stay independent')
assert(rawequal(d,b.Desc),'same native GridDesc must reuse its borrowed view')
b.State=41;assert(d.State==41 and a.Desc.State==41,'cached view copied stale field data')
d.State=42;assert(a.State==42,'cached view lost write-through')
local weak=setmetatable({d},{__mode='v'})
a=nil;b=nil;d=nil
collectgarbage('collect');collectgarbage('collect')
assert(weak[1]==nil,'cache retained grid owner/desc cycle')
local held=r:GetGridEntity(3).Desc
-- New owners remain ordinary fresh userdata; only the 64B descriptor view is shared.
collectgarbage('collect');collectgarbage('stop')
for i=1,100 do local g=r:GetGridEntity(3);local desc=g.Desc;assert(desc.State==42)end
local before=collectgarbage('count')
for i=1,1000 do local g=r:GetGridEntity(3);local desc=g.Desc;assert(desc.State==42)end
local growth=collectgarbage('count')-before
collectgarbage('restart')
assert(growth<65,'descriptor cache did not remove per-query view allocation: '..growth)
assert(held.State==42)
local co=coroutine.create(function()
 local other=r:GetGridEntity(3)
 assert(rawequal(held,other.Desc),'coroutine lost shared registry view')
 other.State=43;assert(held.State==43)
end)
local ok,err=coroutine.resume(co);assert(ok,err)
Poop.State=19
'''
  marker='local pool=Game():GetItemPool();'
  main=MAIN.replace(marker,extra+'\n'+marker,1)
  self.assertNotEqual(main,MAIN)
  r=run_world(main=main);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
