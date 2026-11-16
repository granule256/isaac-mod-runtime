"""Reverie MGO's unguarded callbacks use the real production Lua dispatcher."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_repentogon_callbacks as fixture
from . import test_support


class MgoCallbackTests(unittest.TestCase):
    def test_unguarded_callbacks_exist(self):
        source = fixture.RUNTIME_DRIVER.replace(
            'if(mode=="off"||mode=="none"){\n        script+=',
            '''if(mode=="mgo"){
        script+="assert(ModCallbacks.MC_PRE_ITEM_TEXT_DISPLAY==1484);"
                "assert(ModCallbacks.MC_PRE_PLAYER_ADD_HEARTS==1009);"
                "assert(ModCallbacks.MC_POST_PLAYER_ADD_HEARTS==1010);"
                "assert(ModCallbacks.MC_GET_SHOP_ITEM_PRICE==1066);";
        script+="assert(ModCallbacks.MC_GET_FOLLOWER_PRIORITY==1063);";
        script+="assert(ModCallbacks.MC_POST_TRIGGER_WEAPON_FIRED==1098);";
        script+=R"lua(
m:AddCallback(1009,function(_,p,n,t,arg)
 assert(p and n==6 and t==1 and arg==nil);return 3
end,1)
m:AddCallback(1009,function()error('wrong health filter')end,4)
m:AddCallback(1010,function(_,p,n,t,arg)
 assert(p and n==3 and t==1 and arg==nil);calls=calls+1
end,1)
m:AddCallback(1066,function(_,v,s,shop,price)
 assert(v==7400 and s==2 and shop==-1 and price==15);return 7
end,7400)
m:AddCallback(1066,function()error('wrong price filter')end,100)
m:AddCallback(1484,function(_,title,subtitle,sticky,curse)
 assert(title=='stage' and subtitle=='curse' and sticky and curse);return false
end)
m:AddCallback(1063,function(_,familiar)assert(familiar);return 2 end,7)
m:AddCallback(1034,function(_,id,volume,fade)
 assert(id==3 and volume==0.5 and not fade);return 4
end,3)
m:AddPriorityCallback(1034,-10,function()error('wrong music filter')end,9)
m:AddCallback(1098,function(_,dir,amount,owner,weapon)
 assert(dir.X==1 and dir.Y==-2 and amount==3 and owner)
 assert(weapon:GetCharge()==4.5)
 savedWeapon=weapon
end,2)
m:AddPriorityCallback(1098,-10,function()error('wrong weapon filter')end,9)
m:AddCallback(1020,function()
 assert(not pcall(function()return savedWeapon:GetCharge()end))
end)
)lua";
    }else if(mode=="off"||mode=="none"){
        script+=''',
            1,
        )
        source = source.replace('if(mode=="catalog"){\n            assert(', '''if(mode=="mgo"){
            Event health{};health.id=1009;health.kind=EventKind::PlayerAddHearts;
            health.object=Address(entity);health.first=6;health.second=1;
            auto r=Dispatch(health);Check();assert(r.hasInteger&&r.integer==3);
            health.id=1010;health.first=3;Dispatch(health);Check();assert(Number("calls")==1);
            Event price{};price.id=1066;price.kind=EventKind::ShopItemPrice;
            price.first=7400;price.second=2;price.third=-1;price.fourth=15;
            r=Dispatch(price);Check();assert(r.hasInteger&&r.integer==7);
            Event text{};text.id=1484;text.kind=EventKind::ItemText;
            text.title="stage";text.subtitle="curse";text.low=true;text.first=1;
            r=Dispatch(text);Check();assert(r.hasBoolean&&!r.boolean);
            r=Dispatch({1063,EventKind::Entity,Address(entity)});
            Check();assert(r.hasInteger&&r.integer==2);
            Event music{};music.id=1034;music.kind=EventKind::MusicPlay;
            music.first=3;music.number=0.5F;
            r=Dispatch(music);Check();assert(r.hasInteger&&r.integer==4);
            alignas(8) unsigned char weapon[0x40]{};
            auto owner=Address(entity);float charge=4.5F;int weaponType=2;
            std::memcpy(weapon+0x8,&owner,8);
            std::memcpy(weapon+0x20,&charge,4);
            std::memcpy(weapon+0x38,&weaponType,4);
            Vector direction{1,-2};
            Dispatch({1098,EventKind::WeaponFired,owner,Address(weapon),&direction,false,nullptr,2,3});
            Check();Dispatch({1020});Check();
        }else if(mode=="catalog"){
            assert(''', 1)
        with tempfile.TemporaryDirectory(prefix="mgo-callbacks-") as temporary:
            binary = test_support.build_lua_harness(
                source_root=fixture.SOURCE, workdir=Path(temporary),
                harness_source=source)
            result = subprocess.run([str(binary), "mgo"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
