"""控制台配置入口、原生提示与配置持久化的定向回归。"""
import unittest
import subprocess
import tempfile
from pathlib import Path
from . import test_console_panel as panel
from . import test_console_long_commands as fixture

ROOT=Path(__file__).resolve().parents[2]

class ConsoleControlsTests(unittest.TestCase):
    def test_mod_row_tells_how_to_open_console(self):
        source=(ROOT/'runtime/source/mod_menu_native.cpp').read_text()
        self.assertTrue('Hold ' in source or 'ConsoleControlRowName(' in source,
                        '控制台首行没有提供长按开启提示')

    def test_controls_persist_and_drive_actual_panel(self):
        driver=panel.DRIVER[:panel.DRIVER.index(' // 长按只')] + r'''
 (void)frame;(void)a;(void)b;
 struct Save : ISaveFilePort {
   std::string text="isaac-switch-console-state 1\nenabled=0\nfirst_button=6\nsecond_button=7\nhold_tenths=2\n";
   unsigned reads{},writes{};bool ready=false;
   Status Read(std::string_view,char* out,std::size_t capacity,std::size_t* n)noexcept override {
      ++reads;if(!ready)return Status{StatusCode::Unsupported};assert(text.size()<=capacity);memcpy(out,text.data(),text.size());*n=text.size();return Status::Ok();}
   Status Write(std::string_view,std::string_view value)noexcept override {++writes;text=value;return Status::Ok();}
   Status Remove(std::string_view)noexcept override{return Status::Ok();}
   Status Exists(const char*,bool*)noexcept override{return Status::Ok();}
 } save;
 SetSessionSaveFilePort(nullptr);console::ConsoleSwitchTick();assert(console::Storage().switchReadPending);
 SetSessionSaveFilePort(&save);console::ConsoleSwitchTick();assert(console::Storage().switchReadPending);save.ready=true;
 for(int i=0;i<31;++i)console::ConsoleSwitchTick();assert(save.reads==2 && !console::ConsoleSwitchEnabled());
 auto value=console::Storage().controls;assert(value.first==6&&value.second==7&&value.holdTenths==2);
 console::ConsoleSwitchTick();assert(save.reads==2&&save.writes==0);
 console::RequestConsoleSwitchWrite(true);console::ConsoleSwitchTick();
 assert(save.writes==1&&ParseConsoleSwitch(save.text)&&SameConsoleControls(ParseConsoleControls(save.text),value));
 auto step=[&](unsigned buttons=0,bool blocked=false){console::PanelFrame(entries,ui,moduleBase,1,((buttons&(1u<<4))?(1u<<14):0)|((buttons&(1u<<5))?(1u<<15):0),{},426,240,ConsoleButtonsHeld(console::Storage().controls,buttons),blocked);};
 for(int i=0;i<60;++i)step((1u<<4)|(1u<<5));assert(shown==0); // 旧快捷键失效
 for(int i=0;i<11;++i)step((1u<<6)|(1u<<7));assert(shown==0);
 step(); // 松开中断计时
 for(int i=0;i<11;++i)step((1u<<6)|(1u<<7));assert(shown==0);
 step((1u<<6)|(1u<<7));assert(shown==1&&console::ConsolePaused());
 for(int i=0;i<100;++i)step((1u<<6)|(1u<<7));assert(shown==1&&hidden==0);
 step();for(int i=0;i<12;++i)step((1u<<6)|(1u<<7));step();assert(hidden==1&&!console::ConsolePaused());
 for(int i=0;i<60;++i)step((1u<<6)|(1u<<7),true);assert(shown==1); // MCM隔离
 for(int i=0;i<12;++i)step((1u<<6)|(1u<<7));assert(shown==1); // 关MCM仍需先放开
 step();for(int i=0;i<12;++i)step((1u<<6)|(1u<<7));assert(shown==2);
 step();for(int i=0;i<12;++i)step((1u<<6)|(1u<<7));step();assert(hidden==2);
 assert(!console::RequestConsoleControlsWrite({14,5,8}));assert(!console::RequestConsoleControlsWrite({4,5,51}));
 assert(console::RequestConsoleControlsWrite({8,255,50}));
 console::ConsoleSwitchTick();assert(save.writes==1); // 配置调整合并写入
 for(int i=0;i<30;++i)console::ConsoleSwitchTick();assert(save.writes==2);
 assert(SameConsoleControls(ParseConsoleControls(save.text),ConsoleControls{8,255,50}));
 step();for(int i=0;i<299;++i)step(1u<<8);assert(shown==2);step(1u<<8);assert(shown==3);
 console::ClosePanelImmediately(ui);step();
 assert(console::RequestConsoleControlsWrite({4,255,2}));step();
 for(int i=0;i<12;++i)step(1u<<4);step();assert(shown==4);
 step(1u<<4);step();assert(keyboards==1&&console::Panel().keyboardOpen); // 单A短按仍可编辑
 console::KeyboardFinishedCallback(nullptr,nullptr);step();step(1u<<5);step();
 assert(!console::ConsolePaused());
 assert(console::RequestConsoleControlsWrite({5,255,2}));step();
 for(int i=0;i<12;++i)step(1u<<5);step();assert(shown==5);
 step(1u<<5);step();assert(!console::ConsolePaused()); // 单B短按仍可返回
 char label[80]{};FormatConsoleControlRow(true,{4,5,8},label,sizeof(label));
 assert(std::string(label)=="Console: ON (Hold A+B 0.8s)");
 FormatConsoleControlRow(false,{8,255,50},label,sizeof(label));assert(std::string(label)=="Console: OFF (Hold L 5.0s)");
 assert(SameConsoleControls(ParseConsoleControls("enabled=0\n"),ConsoleControls{}));
 assert(SameConsoleControls(ParseConsoleControls("first_button=-1\nsecond_button=999999999999\nhold_tenths=0\n"),ConsoleControls{}));
 assert(SameConsoleControls(ParseConsoleControls("first_button=13\r\nsecond_button=255\nhold_tenths=50\n"),ConsoleControls{13,255,50}));
 assert(SameConsoleControls(ParseConsoleControls("first_button=2x\nsecond_button=14\nhold_tenths=51\n"),ConsoleControls{}));
 char tiny[2]={'x','x'};assert(SerializeConsoleControls({},tiny,sizeof(tiny))==0&&tiny[0]=='x');
 assert(ConsoleButtonsHeld({4,4,8},1u<<4));assert(!ConsoleButtonsHeld({99,255,8},0xffffffff));
 for(int i=0;i<31;++i)console::ConsoleSwitchTick();const auto written=save.writes;
 console::ConsoleSwitchTick();assert(save.writes==written); // 无修改无I/O
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'stdfloat').write_text('#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n')
            (p/'test.cpp').write_text(fixture.HARNESS[:fixture.HARNESS.index('int main(')]+driver)
            result=subprocess.run([fixture.host_compilers()[1],'-std=c++23','-Wall','-Wextra','-Werror','-I',tmp,'-I',str(fixture.SOURCE),'-I',str(fixture.SOURCE.parent/'src'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
