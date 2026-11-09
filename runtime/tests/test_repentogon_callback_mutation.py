"""RGON's prefetched iterator must survive removals without skipping unrelated listeners."""
from .test_repentogon_callbacks import POLICY_DRIVER, SOURCE
from . import test_repentogon_callbacks as callbacks
import unittest

DRIVER=POLICY_DRIVER
start=DRIVER.index('    Run(s,R"lua(')
end=DRIVER.index('    lua_close(s);',start)
DRIVER=DRIVER[:start]+r'''
    Run(s,R"lua(
CallbackPriority={DEFAULT=0};local m={};local order='';local first
first=function()order=order..'A';Isaac.RemoveCallback(m,1020,first)end
Isaac.AddCallback(m,1020,first)
Isaac.AddCallback(m,1020,function()order=order..'B'end)
Isaac.AddCallback(m,1020,function()order=order..'C'end)
Isaac.RunCallback(1020);assert(order=='ABC','self removal skipped next listener: '..order)
order='';local a,b,c
b=function()order=order..'B'end;c=function()order=order..'C'end
a=function()order=order..'A';Isaac.RemoveCallback(m,1021,a);Isaac.RemoveCallback(m,1021,b)end
Isaac.AddCallback(m,1021,a);Isaac.AddCallback(m,1021,b);Isaac.AddCallback(m,1021,c)
Isaac.RunCallback(1021);assert(order=='AC','removed-next chain changed: '..order)
order='';local added=false
Isaac.AddPriorityCallback(m,1022,0,function()
 order=order..'A'
 if not added then added=true;Isaac.AddPriorityCallback(m,1022,1,function()order=order..'N'end) end
end)
Isaac.AddPriorityCallback(m,1022,2,function()order=order..'B'end)
Isaac.RunCallback(1022);assert(order=='AB','new callback between prefetched entries ran early: '..order)
order='';Isaac.RunCallback(1022);assert(order=='ANB')
-- Ordinary PC callback traversal retains its old array behavior.
order='';local pc
pc=function()order=order..'A';Isaac.RemoveCallback(m,1,pc)end
Isaac.AddCallback(m,1,pc);Isaac.AddCallback(m,1,function()order=order..'B'end)
Isaac.RunCallback(1);assert(order=='A')
)lua");
'''+DRIVER[end:]

class CallbackMutationTests(unittest.TestCase):
 def test_upstream_prefetch_and_removal_semantics(self):
  callbacks.RepentogonCallbackTests._run_policy_driver(self,DRIVER)
