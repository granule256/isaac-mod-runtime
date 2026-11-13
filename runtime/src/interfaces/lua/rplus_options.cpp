#include "interfaces/lua/rplus_options.hpp"
#include "domain/console/console_commands.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "ports/save_file_port.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>
#include <string_view>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
struct State {
 ISaveFilePort* provider;std::int32_t mode,persisted;
 std::int32_t autofillLimit,persistedAutofillLimit;
 bool statHud,persistedStatHud,ready;StatusCode last;
};
State g_State{nullptr,0,0,console::kConsoleAutofillLimitDefault,
 console::kConsoleAutofillLimitDefault,true,true,false,StatusCode::Unsupported};
std::uint64_t g_Reads{},g_Writes{};
constexpr std::string_view kAnnouncerName="AnnouncerVoiceMode";
constexpr std::string_view kStatHudName="StatHUDPlanetarium";
constexpr std::string_view kAutofillName="ConsoleAutofillLimit";
bool Space(char c)noexcept{return c==' '||c=='\t'||c=='\r'||c=='\n';}
std::string_view Trim(std::string_view text)noexcept{
 while(!text.empty()&&Space(text.front()))text.remove_prefix(1);
 while(!text.empty()&&Space(text.back()))text.remove_suffix(1);
 return text;
}
bool ParseInteger(std::string_view text,std::int32_t* value)noexcept{
 text=Trim(text);
 if(text.empty()||value==nullptr)return false;
 bool negative=false;
 if(!text.empty()&&(text.front()=='-'||text.front()=='+')){negative=text.front()=='-';text.remove_prefix(1);}
 if(text.empty())return false;
 std::uint32_t parsed=0;const std::uint32_t limit=negative?0x80000000U:0x7fffffffU;
 for(const char c:text){
  if(c<'0'||c>'9')return false;
  const auto digit=static_cast<std::uint32_t>(c-'0');
  if(parsed>(limit-digit)/10)return false;
  parsed=parsed*10+digit;
 }
 const auto bits=negative?std::uint32_t{0}-parsed:parsed;
 std::memcpy(value,&bits,4);return true;
}
bool ParseLine(std::string_view line,std::int32_t* mode,bool* statHud,
               std::int32_t* autofillLimit)noexcept{
 line=Trim(line);
 if(line.empty()||mode==nullptr||statHud==nullptr||autofillLimit==nullptr)return false;
 const auto equals=line.find('=');
 if(equals==std::string_view::npos)return false;
 const auto name=Trim(line.substr(0,equals));
 const auto value=Trim(line.substr(equals+1));
 std::int32_t parsed{};
 if(!ParseInteger(value,&parsed))return false;
 if(name==kAnnouncerName){*mode=parsed;return true;}
 if(name==kStatHudName){
  if(parsed<0||parsed>1)return false;
  *statHud=parsed!=0;return true;
 }
 if(name==kAutofillName){
  if(parsed<console::kConsoleAutofillLimitMinimum||
     parsed>console::kConsoleAutofillLimitMaximum)return false;
  *autofillLimit=parsed;return true;
 }
 return false;
}
bool Dirty()noexcept{
 return g_State.mode!=g_State.persisted||
        g_State.autofillLimit!=g_State.persistedAutofillLimit||
        g_State.statHud!=g_State.persistedStatHud;
}
Status SetResult(StatusCode code)noexcept{g_State.last=code;return Status{code};}
bool Matches(const char*name,std::string_view expected)noexcept{
 return name&&expected.data()&&!std::strcmp(name,expected.data());
}
void RequireReady(lua_State*state){
 if(!g_State.ready||g_State.provider!=SessionSaveFilePort())
  luaL_error(state,"Options runtime setting is not loaded (status %u)",static_cast<unsigned>(g_State.last));
}
}
Status LoadRuntimeOptions() noexcept{
 auto*port=SessionSaveFilePort();
 if(g_State.ready&&g_State.provider==port)return Status::Ok();
 // 不允许提供方切换静默丢掉尚未保存的设置。
 if(g_State.ready&&Dirty())return SetResult(StatusCode::InvalidState);
 g_State={port,0,0,console::kConsoleAutofillLimitDefault,
          console::kConsoleAutofillLimitDefault,true,true,false,
          StatusCode::Unsupported};
 console::SetConsoleAutofillLimit(std::int32_t{
     console::kConsoleAutofillLimitDefault});
 if(!port)return SetResult(StatusCode::Unsupported);
 std::array<char,128> text{};std::size_t size{};++g_Reads;
 const auto status=port->Read(kRuntimeOptionsFileName,text.data(),text.size(),&size);
 if(status.code()==StatusCode::NotFound){g_State.ready=true;return SetResult(StatusCode::Ok);}
 if(!status.ok())return SetResult(status.code());
 if(size>text.size())return SetResult(StatusCode::Corrupted);
 const std::string_view contents(text.data(),size);
 std::size_t cursor=0;
 while(cursor<contents.size()){
  const auto end=contents.find('\n',cursor);
  const auto line=contents.substr(cursor,end==std::string_view::npos?contents.size()-cursor:end-cursor);
  if(!Trim(line).empty()&&
     !ParseLine(line,&g_State.mode,&g_State.statHud,&g_State.autofillLimit))
   return SetResult(StatusCode::Corrupted);
  if(end==std::string_view::npos)break;
  cursor=end+1;
 }
 console::SetConsoleAutofillLimit(g_State.autofillLimit);
 g_State.persisted=g_State.mode;
 g_State.persistedAutofillLimit=g_State.autofillLimit;
 g_State.persistedStatHud=g_State.statHud;
 g_State.ready=true;return SetResult(StatusCode::Ok);
}
Status FlushRuntimeOptions() noexcept{
 if(!g_State.ready)return SetResult(StatusCode::Unsupported);
 if(!Dirty())return SetResult(StatusCode::Ok);
 if(!g_State.provider||g_State.provider!=SessionSaveFilePort())return SetResult(StatusCode::InvalidState);
 std::array<char,128> text{};
 std::size_t used=0;
 const auto append=[&](const char* format,std::int32_t value)noexcept{
  const auto written=std::snprintf(text.data()+used,text.size()-used,
                                   format,static_cast<int>(value));
  if(written<=0||static_cast<std::size_t>(written)>=text.size()-used)
   return false;
  used+=static_cast<std::size_t>(written);return true;
 };
 if(!append("AnnouncerVoiceMode=%d\r\n",static_cast<std::int32_t>(g_State.mode))||
    !append("StatHUDPlanetarium=%d\r\n",
            static_cast<std::int32_t>(g_State.statHud?1:0))||
    !append("ConsoleAutofillLimit=%d\r\n",g_State.autofillLimit))
  return SetResult(StatusCode::CapacityExceeded);
 ++g_Writes;
 const auto status=g_State.provider->Write(kRuntimeOptionsFileName,std::string_view(text.data(),used));
 if(!status.ok())return SetResult(status.code());
 g_State.persisted=g_State.mode;
 g_State.persistedAutofillLimit=g_State.autofillLimit;
 g_State.persistedStatHud=g_State.statHud;
 return SetResult(StatusCode::Ok);
}
void ClearRuntimeOptions() noexcept{
 g_State={nullptr,0,0,console::kConsoleAutofillLimitDefault,
          console::kConsoleAutofillLimitDefault,true,true,false,
          StatusCode::Unsupported};
 console::SetConsoleAutofillLimit(std::int32_t{
     console::kConsoleAutofillLimitDefault});
}
int TryPushRuntimeOption(lua_State*state,const char*name){
 if(Matches(name,kAnnouncerName)){
  RequireReady(state);lua_pushinteger(state,g_State.mode);return 1;
 }
 if(Matches(name,kStatHudName)){
  if(!RepentogonEnvironmentActive())return 0;
  RequireReady(state);lua_pushboolean(state,g_State.statHud);return 1;
 }
 return 0;
}
bool TryWriteRuntimeOption(lua_State*state,const char*name){
 if(Matches(name,kAnnouncerName)){
  const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,3));std::int32_t value{};
  std::memcpy(&value,&bits,4);
  if(value<0)value=0;
  if(value>2)value=2;
  RequireReady(state);g_State.mode=value;return true;
 }
 if(Matches(name,kStatHudName)){
  if(!RepentogonEnvironmentActive())
   luaL_error(state,"Options.StatHUDPlanetarium requires REPENTOGON");
  luaL_checktype(state,3,LUA_TBOOLEAN);
  RequireReady(state);g_State.statHud=lua_toboolean(state,3)!=0;return true;
 }
 return false;
}
bool RuntimeOptionStatHudPlanetarium() noexcept{return g_State.statHud;}
void SetRuntimeOptionStatHudPlanetarium(bool value) noexcept{g_State.statHud=value;}
std::int32_t RuntimeOptionConsoleAutofillLimit() noexcept{return g_State.autofillLimit;}
void SetRuntimeOptionConsoleAutofillLimit(std::int32_t value) noexcept{
 g_State.autofillLimit=std::clamp(value,
     console::kConsoleAutofillLimitMinimum,
     console::kConsoleAutofillLimitMaximum);
 console::SetConsoleAutofillLimit(g_State.autofillLimit);
}
RuntimeOptionStats RuntimeOptionStatsSnapshot() noexcept{
 return {g_State.mode,g_State.persisted,g_State.autofillLimit,
         g_State.persistedAutofillLimit,g_State.statHud,
         g_State.persistedStatHud,g_State.ready,Dirty(),
         g_Reads,g_Writes,g_State.last};
}
}
