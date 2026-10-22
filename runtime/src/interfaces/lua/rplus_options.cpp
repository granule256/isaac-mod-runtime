#include "interfaces/lua/rplus_options.hpp"
#include "ports/save_file_port.hpp"
#include <array>
#include <cstdio>
#include <cstring>
#include <string_view>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
struct State {ISaveFilePort* provider;std::int32_t mode,persisted;bool ready;StatusCode last;};
State g_State{};
std::uint64_t g_Reads{},g_Writes{};
constexpr std::string_view kName="AnnouncerVoiceMode";
bool Space(char c)noexcept{return c==' '||c=='\t'||c=='\r'||c=='\n';}
std::string_view Trim(std::string_view text)noexcept{
 while(!text.empty()&&Space(text.front()))text.remove_prefix(1);
 while(!text.empty()&&Space(text.back()))text.remove_suffix(1);
 return text;
}
bool Parse(std::string_view text,std::int32_t* mode)noexcept{
 text=Trim(text);
 if(text.substr(0,kName.size())!=kName)return false;
 text=Trim(text.substr(kName.size()));
 if(text.empty()||text.front()!='=')return false;
 text=Trim(text.substr(1));
 bool negative=false;
 if(!text.empty()&&(text.front()=='-'||text.front()=='+')){negative=text.front()=='-';text.remove_prefix(1);}
 if(text.empty())return false;
 std::uint32_t value=0;const std::uint32_t limit=negative?0x80000000U:0x7fffffffU;
 for(const char c:text){
  if(c<'0'||c>'9')return false;
  const auto digit=static_cast<std::uint32_t>(c-'0');
  if(value>(limit-digit)/10)return false;
  value=value*10+digit;
 }
 const auto bits=negative?std::uint32_t{0}-value:value;
 std::memcpy(mode,&bits,4);return true;
}
Status SetResult(StatusCode code)noexcept{g_State.last=code;return Status{code};}
bool Matches(const char*name)noexcept{return name&&name[0]=='A'&&!std::strcmp(name,kName.data());}
void RequireReady(lua_State*state){
 if(!g_State.ready||g_State.provider!=SessionSaveFilePort())
  luaL_error(state,"Options.AnnouncerVoiceMode is not loaded (status %u)",static_cast<unsigned>(g_State.last));
}
}
Status LoadRuntimeOptions() noexcept{
 auto*port=SessionSaveFilePort();
 if(g_State.ready&&g_State.provider==port)return Status::Ok();
 // 不允许提供方切换静默丢掉尚未保存的设置。
 if(g_State.ready&&g_State.mode!=g_State.persisted)return SetResult(StatusCode::InvalidState);
 g_State={port,0,0,false,StatusCode::Unsupported};
 if(!port)return SetResult(StatusCode::Unsupported);
 std::array<char,128> text{};std::size_t size{};++g_Reads;
 const auto status=port->Read(kRuntimeOptionsFileName,text.data(),text.size(),&size);
 if(status.code()==StatusCode::NotFound){g_State.ready=true;return SetResult(StatusCode::Ok);}
 if(!status.ok())return SetResult(status.code());
 std::int32_t mode{};
 if(size>text.size()||!Parse(std::string_view(text.data(),size),&mode))return SetResult(StatusCode::Corrupted);
 g_State.mode=mode;g_State.persisted=mode;g_State.ready=true;return SetResult(StatusCode::Ok);
}
Status FlushRuntimeOptions() noexcept{
 if(!g_State.ready)return SetResult(StatusCode::Unsupported);
 if(g_State.mode==g_State.persisted)return SetResult(StatusCode::Ok);
 if(!g_State.provider||g_State.provider!=SessionSaveFilePort())return SetResult(StatusCode::InvalidState);
 std::array<char,64> text{};
 const auto size=std::snprintf(text.data(),text.size(),"AnnouncerVoiceMode=%d\r\n",static_cast<int>(g_State.mode));
 if(size<=0||static_cast<std::size_t>(size)>=text.size())return SetResult(StatusCode::CapacityExceeded);
 ++g_Writes;
 const auto status=g_State.provider->Write(kRuntimeOptionsFileName,std::string_view(text.data(),static_cast<std::size_t>(size)));
 if(!status.ok())return SetResult(status.code());
 g_State.persisted=g_State.mode;return SetResult(StatusCode::Ok);
}
void ClearRuntimeOptions() noexcept{g_State={nullptr,0,0,false,StatusCode::Unsupported};}
int TryPushRuntimeOption(lua_State*state,const char*name){
 if(!Matches(name))return 0;
 RequireReady(state);lua_pushinteger(state,g_State.mode);return 1;
}
bool TryWriteRuntimeOption(lua_State*state,const char*name){
 if(!Matches(name))return false;
 const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,3));std::int32_t value{};std::memcpy(&value,&bits,4);
 if(value<0)value=0;
 if(value>2)value=2;
 RequireReady(state);g_State.mode=value;return true;
}
RuntimeOptionStats RuntimeOptionStatsSnapshot() noexcept{return {g_State.mode,g_State.persisted,g_State.ready,g_State.mode!=g_State.persisted,g_Reads,g_Writes,g_State.last};}
}
