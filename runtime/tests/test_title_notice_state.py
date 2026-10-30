"""标题说明册的真实状态机与版本确认记录；宿主编译执行，不访问设备。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "title_notice_state.hpp"
#include "title_notice_store.hpp"
#include <cstdio>
#include <cstring>
#include <string>
using namespace isaac::runtime;
using namespace isaac::runtime::notice;
int failures=0;
void check(bool ok,const char* what) { if(!ok) {std::printf("FAIL %s\n",what);++failures;} }
void step(State& s,unsigned keys=0,unsigned ticks=1,bool title=true,bool ready=true,unsigned pages=3) {
    for(unsigned i=0;i<ticks;++i) s.Tick(keys,title,ready,pages);
}
void settle(State& s) {step(s,0,30);}
struct Save : ISaveFilePort {
    std::string data; unsigned reads=0,writes=0; bool exists=false,fail=false;
    Status Read(std::string_view name,char* out,std::size_t cap,std::size_t* size) noexcept override {
        ++reads; check(name=="isaac-switch-notice-version.txt","dedicated save marker");
        if(fail) return Status{StatusCode::IoFailure};
        if(!exists) return Status{StatusCode::NotFound};
        if(data.size()>cap) return Status{StatusCode::CapacityExceeded};
        *size=data.size();std::memcpy(out,data.data(),*size);return Status::Ok();
    }
    Status Write(std::string_view,std::string_view value) noexcept override {
        ++writes;if(fail)return Status{StatusCode::IoFailure};data=value;exists=true;return Status::Ok();
    }
    Status Remove(std::string_view) noexcept override {return Status::Ok();}
    Status Exists(const char*,bool*) noexcept override {return Status::Ok();}
};
int main() {
    { State s; s.SetSeenVersion(false); step(s); check(s.phase==Phase::Opening,"first version opens");
      check(s.BlocksTitleConfirm(),"opening blocks title confirm");settle(s);
      step(s,Back,120);check(s.phase==Phase::Reading,"must visit every page before holding B");
      check(s.holdTicks==0,"locked hold does not accumulate");step(s);
      step(s,Right);step(s,0,12);step(s,Back,80);
      check(s.phase==Phase::Reading,"middle page still cannot dismiss");step(s);
      step(s,Right);step(s,0,12);
      check(s.AllPagesViewed(3),"last page completes visit set");
      step(s,Back,59);check(s.phase==Phase::Reading,"59 frames not enough");
      step(s);step(s,Back,59);check(s.phase==Phase::Reading,"release resets hold");
      step(s,Back);check(s.phase==Phase::Closing,"continuous 60 frames close");
      check(!s.ConsumeAcknowledgement(),"do not persist before close finishes");
      step(s,Back,20);check(s.phase==Phase::Hidden,"close animation completes");
      check(s.ConsumeAcknowledgement(),"automatic close acknowledges version");
      check(!s.ConsumeAcknowledgement(),"ack exactly once");
      step(s,0,100);check(s.phase==Phase::Hidden,"same launch never reopens");
      step(s,0,1,false);step(s);check(s.phase==Phase::Hidden,"title return stays dismissed"); }
    { State s;s.SetSeenVersion(true);step(s);check(s.phase==Phase::Hidden,"seen version starts closed");
      step(s,Right);check(s.focused,"direction selects bottom-right entry");step(s);
      step(s,Confirm);check(s.phase==Phase::Opening&&!s.requiresHold,"manual mode");settle(s);
      step(s,Back);check(s.phase==Phase::Closing,"manual tap closes");step(s,0,20);
      check(s.phase==Phase::Hidden&&!s.ConsumeAcknowledgement(),"manual open never writes seen");
      check(s.focused,"return focus to entry");step(s,Left);check(!s.focused,"left returns title focus"); }
    { State s;s.SetSeenVersion(false);step(s,Back);step(s,Back,100);
      check(s.phase==Phase::Reading,"B held before open must be released");step(s);
      step(s,Right);step(s,0,12);step(s,Right);step(s,0,12);step(s,Back,60);
      check(s.phase==Phase::Closing,"fresh hold works"); }
    for (Phase requested : {Phase::Opening,Phase::FlipOut,Phase::FlipIn}) {
      for (bool held : {false,true}) {
        State s;s.SetSeenVersion(true);step(s);step(s,Right);step(s);step(s,Confirm);
        unsigned untilReading=kOpenTicks;
        if(requested!=Phase::Opening) {
          step(s,0,kOpenTicks);step(s,Right);untilReading=kFlipTicks*2;
          if(requested==Phase::FlipIn) {step(s,0,kFlipTicks);untilReading=kFlipTicks;}
        }
        check(s.phase==requested,"manual close regression starts in requested transition");
        step(s,Back);check(s.phase==requested,"manual B waits for active transition");
        step(s,held?Back:0,untilReading-2);
        check(s.phase!=Phase::Closing,"manual close does not interrupt unfinished transition");
        step(s,held?Back:0);
        if(s.phase!=Phase::Closing) {
          std::printf("FAIL queued manual close phase=%u held=%u\n",unsigned(requested),unsigned(held));++failures;
        }
        step(s,held?Back:0,kCloseTicks);
        check(s.phase==Phase::Hidden,"queued manual close finishes normally");
        check(!s.ConsumeAcknowledgement(),"queued manual close does not acknowledge automatic notice");
      }
    }
    for (Phase requested : {Phase::Opening,Phase::FlipOut,Phase::FlipIn}) {
      State s;s.SetSeenVersion(false);step(s);
      if(requested!=Phase::Opening) {
        settle(s);step(s,Right);
        if(requested==Phase::FlipIn) step(s,0,kFlipTicks);
      }
      check(s.phase==requested,"automatic hold regression starts in requested transition");
      step(s,Back);step(s,0,kOpenTicks+kFlipTicks*2);
      check(s.phase==Phase::Reading,"automatic transition B tap does not queue close");
      while(s.page<2){step(s,Right);step(s,0,kFlipTicks*2);}
      step(s,Back,kHoldTicks-1);check(s.phase==Phase::Reading,"automatic still needs continuous hold");
      step(s,Back);check(s.phase==Phase::Closing,"automatic fresh full hold still closes");
    }
    { State s;s.SetSeenVersion(true);step(s);step(s,Back);step(s,Right|Back);step(s,Back);step(s,Confirm|Back);
      check(s.phase==Phase::Opening,"manual inherited B opens with B already held");
      step(s,Back,kOpenTicks+kHoldTicks);
      check(s.phase==Phase::Reading,"manual inherited B does not queue or close");
      step(s);step(s,Back);check(s.phase==Phase::Closing,"manual B release arms a fresh close"); }
    { State s;s.SetSeenVersion(false);step(s);settle(s);step(s,Left);
      check(s.page==0&&s.phase==Phase::Reading,"no flip past first page");step(s);
      step(s,Right);check(s.phase==Phase::FlipOut,"flip outgoing animation");
      step(s,Right,6);check(s.phase==Phase::FlipIn&&s.page==1,"swap at folded midpoint");
      step(s,Right,6);check(s.phase==Phase::Reading&&s.page==1,"held direction flips once");
      step(s,Right,40);check(s.page==1,"no held repeat between pages");step(s);step(s,Next);
      step(s,0,12);check(s.page==2,"shoulder key next");step(s,Right);
      check(s.phase==Phase::Reading&&s.page==2,"no flip past final page"); }
    { State s;s.SetSeenVersion(false);step(s,0,200,false);check(s.phase==Phase::Hidden,"no in-game overlay");
      check(!s.BlocksTitleConfirm(),"no in-game input gate");step(s,0,20,true,false);
      check(s.phase==Phase::Hidden,"wait for resources");step(s);check(s.phase==Phase::Opening,"auto opens when ready"); }
    { State s;s.SetSeenVersion(true);step(s);step(s,Down);step(s);step(s,Confirm);settle(s);
      step(s,Back);step(s,Confirm,20);check(s.phase==Phase::Hidden,"animation ends while A held");
      check(s.BlocksTitleConfirm(),"A held across closing cannot start game");
      step(s,Confirm,10);check(s.BlocksTitleConfirm(),"suppress until A released");step(s);step(s,Up);
      check(!s.BlocksTitleConfirm(),"normal title navigation restored"); }
    { State s;s.SetSeenVersion(false);step(s,0,1,true,true,1);step(s,0,30,true,true,1);
      check(s.AllPagesViewed(1),"one page is viewed when open completes");
      step(s,Back,60,true,true,1);check(s.phase==Phase::Closing,"one page needs no artificial flip"); }
    { State s;s.SetSeenVersion(false);step(s,0,30,true,true,32);
      check(!s.AllPagesViewed(32),"32 page mask begins locked");
      for(unsigned page=1;page<32;++page){
        step(s,Right,1,true,true,32);step(s,0,12,true,true,32);
        check(s.AllPagesViewed(32)==(page==31),"unlock only after all 32 pages");
      }
      check(!s.AllPagesViewed(0)&&!s.AllPagesViewed(33),"unsupported counts stay locked"); }
    { State s;s.SetSeenVersion(true);step(s);step(s,Right);step(s);step(s,Confirm);settle(s);
      step(s,Right);step(s,0,12);step(s,Back);
      check(s.phase==Phase::Closing,"manual reopen closes from any page without viewing all"); }
    { Save save;bool seen=true;check(ReadSeenVersion(save,"v1",&seen).ok()&&!seen,"missing marker needs notice");
      check(WriteSeenVersion(save,"v1").ok(),"persist release version");
      check(ReadSeenVersion(save,"v1",&seen).ok()&&seen,"same version accepted");
      check(ReadSeenVersion(save,"v2",&seen).ok()&&!seen,"new version needs notice");
      save.data="v1\ngarbage";check(ReadSeenVersion(save,"v1",&seen).ok()&&!seen,"exact record only");
      save.fail=true;check(!ReadSeenVersion(save,"v1",&seen).ok(),"read failure visible");
      check(!WriteSeenVersion(save,"v1").ok(),"write failure visible"); }
    return failures?1:0;
}
'''

class TitleNoticeStateTests(unittest.TestCase):
    def test_first_launch_navigation_animation_and_version_record(self):
        for name in ('title_notice_state.hpp', 'title_notice_store.hpp'):
            self.assertTrue((ROOT/'runtime/source'/name).exists(), f'{name}: notice feature missing')
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='title-notice-') as tmp:
            cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';cpp.write_text(HARNESS)
            built=subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)

if __name__=='__main__': unittest.main()
