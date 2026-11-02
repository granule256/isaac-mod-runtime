#include "application/shader/shader_pipeline.hpp"
#include "application/shader/shader_identity.hpp"
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>
namespace isaac::runtime {
namespace {
struct Program {
 Program* next;ShaderProgramView view;void* native;ShaderBackend backend;
 char *owner,*name,*vertex,*fragment;ShaderAttribute* attributes;ShaderParameter* parameters;float* vertices;
 std::size_t bytes;
 shader_identity::Kind identity;
};
struct State {
 Program* programs;Program* copyProgram;std::size_t count,bytes;ShaderValueProvider values;
 ShaderTarget targets[2];ShaderFrameInfo frame;const ShaderBackend* frameBackend;
 ShaderBackend targetBackend;std::uint32_t targetWidth,targetHeight;bool active,finishing,unloadPending;
 std::uint64_t frames,passes,valueFailures;ShaderPipelineError error;
};
bool SleeperInterface(const Program& p,std::size_t count) {
 constexpr const char* names[]={"ActiveIn","TargetPositionOne","TargetPositionTwo","FadePositions","WarpCheck","RandomIn","ColorPulseIn"};
 constexpr unsigned components[]={1,4,4,4,2,1,1};
 if(count!=7)return false;
 unsigned seen=0;
 for(std::size_t i=0;i<count;++i){
  unsigned j=0;while(j<7&&std::strcmp(p.parameters[i].name,names[j]))++j;
  if(j==7||p.parameters[i].components!=components[j]||(seen&(1U<<j)))return false;
  seen|=1U<<j;
 }
 return seen==127;
}
State g_State{};
bool Space(char c){return c==' '||c=='\t'||c=='\r'||c=='\n';}
std::string_view Trim(std::string_view v){while(!v.empty()&&Space(v.front()))v.remove_prefix(1);while(!v.empty()&&Space(v.back()))v.remove_suffix(1);return v;}
struct Tag {std::string_view name,attributes;bool end,empty;};
struct Xml {
 std::string_view source;std::size_t position;
 bool Next(Tag* out) {
  while(position<source.size()) {
   const auto open=source.find('<',position);if(open==source.npos)return false;position=open;
   if(source.substr(open,4)=="<!--"){const auto close=source.find("-->",open+4);if(close==source.npos)return false;position=close+3;continue;}
   if(source.substr(open,2)=="<?"){const auto close=source.find("?>",open+2);if(close==source.npos)return false;position=close+2;continue;}
   std::size_t end=open+1;char quote=0;
   for(;end<source.size();++end){const char c=source[end];if(quote){if(c==quote)quote=0;}else if(c=='\''||c=='"')quote=c;else if(c=='>')break;}
   if(end==source.size())return false;
   auto text=Trim(source.substr(open+1,end-open-1));position=end+1;out->end=!text.empty()&&text.front()=='/';
   if(out->end){text.remove_prefix(1);}
   out->empty=!text.empty()&&text.back()=='/';if(out->empty)text.remove_suffix(1);
   std::size_t n=0;while(n<text.size()&&!Space(text[n]))++n;out->name=text.substr(0,n);out->attributes=text.substr(n);return !out->name.empty();
  }
  return false;
 }
 bool Text(std::string_view name,std::string_view* out,bool* entities) {
  *entities=true;
  const auto begin=position;auto content=Trim(source.substr(begin));
  if(content.substr(0,9)=="<![CDATA["){
   const auto cdata=source.find("<![CDATA[",begin);const auto close=source.find("]]>",cdata+9);if(close==source.npos)return false;
   *entities=false;*out=source.substr(cdata+9,close-cdata-9);position=close+3;Tag end{};return Next(&end)&&end.end&&end.name==name;
  }
  const auto close=source.find("</",begin);if(close==source.npos)return false;*out=Trim(source.substr(begin,close-begin));position=close;Tag end{};return Next(&end)&&end.end&&end.name==name;
 }
};
std::string_view Attribute(std::string_view text,std::string_view wanted) {
 while(!text.empty()) {
  text=Trim(text);std::size_t n=0;while(n<text.size()&&!Space(text[n])&&text[n]!='=')++n;
  const auto name=text.substr(0,n);text.remove_prefix(n);text=Trim(text);if(text.empty()||text.front()!='=')return {};
  text.remove_prefix(1);text=Trim(text);if(text.empty()||(text.front()!='\''&&text.front()!='"'))return {};
  const auto quote=text.front();text.remove_prefix(1);const auto end=text.find(quote);if(end==text.npos)return {};
  const auto value=text.substr(0,end);text.remove_prefix(end+1);if(name==wanted)return value;
 }
 return {};
}
char* Copy(std::string_view v) {
 if(v.size()==std::numeric_limits<std::size_t>::max())return nullptr;
 auto* out=static_cast<char*>(std::malloc(v.size()+1));if(out){std::memcpy(out,v.data(),v.size());out[v.size()]=0;}return out;
}
char* DecodeXml(std::string_view value) {
 auto* output=static_cast<char*>(std::malloc(value.size()+1));if(!output){return nullptr;}
 std::size_t n=0;
 for(std::size_t i=0;i<value.size();++i){
  if(value[i]!='&'){output[n++]=value[i];continue;}
  const auto end=value.find(';',i+1);if(end==value.npos){std::free(output);return nullptr;}
  const auto token=value.substr(i+1,end-i-1);std::uint32_t cp{};
  if(token=="amp")cp='&';else if(token=="lt")cp='<';else if(token=="gt")cp='>';
  else if(token=="quot")cp='"';else if(token=="apos")cp='\'';
  else if(!token.empty()&&token.front()=='#'){
   std::size_t digit=1;unsigned radix=10;if(digit<token.size()&&(token[digit]=='x'||token[digit]=='X')){++digit;radix=16;}
   if(digit==token.size()){std::free(output);return nullptr;}
   for(;digit<token.size();++digit){const char c=token[digit];const unsigned v=c>='0'&&c<='9'?unsigned(c-'0'):c>='a'&&c<='f'?unsigned(c-'a'+10):c>='A'&&c<='F'?unsigned(c-'A'+10):radix;
    if(v>=radix||cp>(0x10ffff-v)/radix){std::free(output);return nullptr;}cp=cp*radix+v;
   }
  }else{std::free(output);return nullptr;}
  if(!cp||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff)){std::free(output);return nullptr;}
  if(cp<0x80)output[n++]=static_cast<char>(cp);
  else if(cp<0x800){output[n++]=static_cast<char>(0xc0|(cp>>6));output[n++]=static_cast<char>(0x80|(cp&63));}
  else if(cp<0x10000){output[n++]=static_cast<char>(0xe0|(cp>>12));output[n++]=static_cast<char>(0x80|((cp>>6)&63));output[n++]=static_cast<char>(0x80|(cp&63));}
  else{output[n++]=static_cast<char>(0xf0|(cp>>18));output[n++]=static_cast<char>(0x80|((cp>>12)&63));output[n++]=static_cast<char>(0x80|((cp>>6)&63));output[n++]=static_cast<char>(0x80|(cp&63));}
  i=end;
 }
 output[n]=0;return output;
}
bool WordChar(char c){return(c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_';}
bool HasCodeWord(std::string_view source,std::string_view wanted) {
 for(std::size_t i=0;i<source.size();) {
  if(source.substr(i,2)=="//") {const auto end=source.find('\n',i+2);i=end==source.npos?source.size():end+1;continue;}
  if(source.substr(i,2)=="/*") {const auto end=source.find("*/",i+2);i=end==source.npos?source.size():end+2;continue;}
  if(WordChar(source[i])) {
   auto end=i+1;while(end<source.size()&&WordChar(source[end]))++end;
   if(source.substr(i,end-i)==wanted)return true;
   i=end;
  }else ++i;
 }
 return false;
}
// 只改变表示方式：PC attribute/varying改为NVN GLSL430；Transform保留原值和名字，放入原生ProjectionMatrix块。
char* Translate(std::string_view source,bool vertex) {
 if(source.size()>(SIZE_MAX-512)/3)return nullptr;
 auto* out=static_cast<char*>(std::malloc(source.size()*3+512));if(!out)return nullptr;
 std::size_t used=0;auto emit=[&](std::string_view v){std::memcpy(out+used,v.data(),v.size());used+=v.size();};
 emit("#version 430\n");
 // 原生以分离阶段编译；GLSL150以上须在使用gl_Position前重声明内置输出块。
 if(vertex&&!HasCodeWord(source,"gl_PerVertex"))emit("out gl_PerVertex { vec4 gl_Position; };\n");
 if(!vertex&&source.find("gl_FragColor")!=source.npos)emit("out vec4 RPlusFragmentColor;\n");
 for(std::size_t i=0;i<source.size();) {
  if(source.substr(i,2)=="//"){
   const auto newline=source.find('\n',i);const auto end=newline==source.npos?source.size():newline;emit(source.substr(i,end-i));i=end;continue;
  }
  if(source.substr(i,2)=="/*"){
   const auto close=source.find("*/",i+2);const auto end=close==source.npos?source.size():close+2;emit(source.substr(i,end-i));i=end;continue;
  }
  if(source.substr(i,8)=="#version"){const auto end=source.find('\n',i);i=end==source.npos?source.size():end+1;continue;}
  if(WordChar(source[i])) {
   auto end=i+1;while(end<source.size()&&WordChar(source[end]))++end;const auto word=source.substr(i,end-i);
   if(vertex&&word=="uniform") {
    std::size_t a=end;while(a<source.size()&&Space(source[a]))++a;
    if(source.substr(a,4)=="mat4"&&(a+4==source.size()||!WordChar(source[a+4]))) {
     a+=4;while(a<source.size()&&Space(source[a]))++a;
     if(source.substr(a,9)=="Transform"&&(a+9==source.size()||!WordChar(source[a+9]))) {
      a+=9;while(a<source.size()&&Space(source[a]))++a;
      if(a<source.size()&&source[a]==';'){emit("layout(std140) uniform ProjectionMatrix { mat4 Transform; };");i=a+1;continue;}
     }
    }
   }
   if(word=="attribute")emit("in");else if(word=="varying")emit(vertex?"out":"in");
   else if(word=="texture2D")emit("texture");else if(word=="gl_FragColor")emit("RPlusFragmentColor");else emit(word);
   i=end;
  }else {out[used++]=source[i++];}
 }
 out[used]=0;return out;
}
unsigned Components(std::string_view type) {
 if(type=="float"){return 1;}
 if(type=="vec2"){return 2;}
 if(type=="vec3"){return 3;}
 if(type=="vec4"){return 4;}
 return 0;
}
void Free(Program* p,bool native) {
 if(!p){return;}
 if(native&&p->native)p->backend.destroy(p->native);
 for(std::size_t i=0;i<p->view.parameterCount;++i)std::free(const_cast<char*>(p->parameters[i].name));
 std::free(p->owner);std::free(p->name);std::free(p->vertex);std::free(p->fragment);
 std::free(p->attributes);std::free(p->parameters);std::free(p->vertices);std::free(p);
}
void FreeList(Program* list,bool native){while(list){auto* next=list->next;Free(list,native);list=next;}}
bool Parameters(std::string_view text,std::size_t* count,std::size_t* floats,Program* program=nullptr) {
 Xml parser{text,0};Tag tag{};std::size_t n=0,f=14;
 while(parser.Next(&tag)) {
  if(tag.name!="param"||tag.end||!tag.empty)return false;
  const auto name=Attribute(tag.attributes,"name");const auto width=Components(Attribute(tag.attributes,"type"));
  if(name.empty()||!width)return false;
  if(program) {
   auto* key=DecodeXml(name);if(!key)return false;program->parameters[n]={key,width,static_cast<std::uint32_t>(f)};
   program->attributes[n+5]={key,width,0};program->view.parameterCount=n+1;
  }
  if(f>UINT32_MAX-width){return false;}
  f+=width;++n;
 }
 *count=n;*floats=f;return true;
}
Program* Make(std::string_view owner,std::string_view name,std::string_view vertex,
              std::string_view fragment,std::string_view parameters,const ShaderBackend& backend,bool vertexEntities=false,bool fragmentEntities=false) {
 std::size_t count=0,stride=0;if(!Parameters(parameters,&count,&stride))return nullptr;
 if(count>SIZE_MAX/sizeof(ShaderParameter)||count>SIZE_MAX/sizeof(ShaderAttribute)-6||stride>SIZE_MAX/(4*sizeof(float)))return nullptr;
 auto* p=static_cast<Program*>(std::calloc(1,sizeof(Program)));if(!p)return nullptr;p->backend=backend;
 p->owner=Copy(owner);p->name=DecodeXml(name);
 auto* vertexText=vertexEntities?DecodeXml(vertex):Copy(vertex);auto* fragmentText=fragmentEntities?DecodeXml(fragment):Copy(fragment);
 if(!vertexText||!fragmentText){std::free(vertexText);std::free(fragmentText);Free(p,false);return nullptr;}
 p->identity=shader_identity::Classify(vertexText,fragmentText);
 p->vertex=Translate(vertexText,true);p->fragment=Translate(fragmentText,false);std::free(vertexText);std::free(fragmentText);
 p->parameters=static_cast<ShaderParameter*>(std::calloc(count?count:1,sizeof(ShaderParameter)));
 p->attributes=static_cast<ShaderAttribute*>(std::calloc(count+6,sizeof(ShaderAttribute)));
 p->vertices=static_cast<float*>(std::calloc(4*stride,sizeof(float)));
 if(!p->owner||!p->name||!p->vertex||!p->fragment||!p->parameters||!p->attributes||!p->vertices){Free(p,false);return nullptr;}
 p->attributes[0]={"Position",3,0};p->attributes[1]={"Color",4,0};p->attributes[2]={"TexCoord",2,0};
 p->attributes[3]={"RenderData",4,0};p->attributes[4]={"Scale",1,0};
 if(!Parameters(parameters,&count,&stride,p)){Free(p,false);return nullptr;}
 if((p->identity==shader_identity::Kind::Copy&&count!=0)||
    (p->identity==shader_identity::Kind::Pixelation&&
     (count!=1||p->parameters[0].components!=1||p->parameters[0].offset!=14||
      std::strcmp(p->parameters[0].name,"PixelAmount")))||
    (p->identity==shader_identity::Kind::InactiveSleeper&&!SleeperInterface(*p,count)))
  p->identity=shader_identity::Kind::None;
 p->view={p->owner,p->name,p->vertex,p->fragment,p->attributes,p->parameters,count+5,count,stride};
 p->bytes=sizeof(Program)+(count?count:1)*sizeof(ShaderParameter)+(count+6)*sizeof(ShaderAttribute)+4*stride*sizeof(float)+
  std::strlen(p->owner)+std::strlen(p->name)+std::strlen(p->vertex)+std::strlen(p->fragment)+4;
 for(std::size_t i=0;i<count;++i)p->bytes+=std::strlen(p->parameters[i].name)+1;
 return p;
}
void Insert(Program** list,Program* value) {
 while(*list&&std::strcmp((*list)->name,value->name)<0)list=&(*list)->next;
 if(*list&&!std::strcmp((*list)->name,value->name)){auto* old=*list;value->next=old->next;*list=value;Free(old,true);}
 else {value->next=*list;*list=value;}
}
void Recount(){g_State.count=0;g_State.bytes=0;for(auto* p=g_State.programs;p;p=p->next){++g_State.count;g_State.bytes+=p->bytes;}}
}
bool LoadShaderXml(std::string_view owner,std::string_view xml,const ShaderBackend& backend) noexcept {
 if(g_State.active){g_State.error=ShaderPipelineError::Busy;return false;}
 if(!backend.compile||!backend.destroy||!backend.frameInfo||!backend.createTarget||!backend.releaseTarget||
    !backend.target||!backend.clear||!backend.standardVertices||!backend.draw||!backend.drain){g_State.error=ShaderPipelineError::NativeCompile;return false;}
 Xml parser{xml,0};Tag tag{};Program* added=nullptr;
 if(!parser.Next(&tag)||tag.end||tag.name!="shaders"){g_State.error=ShaderPipelineError::Xml;return false;}
 const bool emptyRoot=tag.empty;
 while(!emptyRoot&&parser.Next(&tag)) {
  if(tag.end&&tag.name=="shaders")break;
  if(tag.end||tag.empty||tag.name!="shader")goto xml_failed;
  const auto name=Attribute(tag.attributes,"name");std::string_view vertex,fragment,parameters;bool closed=false,vertexEntities=false,fragmentEntities=false;
  while(parser.Next(&tag)) {
   if(tag.end&&tag.name=="shader"){closed=true;break;}
   if(tag.end)goto xml_failed;
   if(tag.empty){if(tag.name=="parameters"){parameters={};continue;}goto xml_failed;}
   if(tag.name=="vertex"){if(!parser.Text("vertex",&vertex,&vertexEntities))goto xml_failed;}
   else if(tag.name=="fragment"){if(!parser.Text("fragment",&fragment,&fragmentEntities))goto xml_failed;}
   else if(tag.name=="parameters") {
    const auto begin=parser.position;Tag param{};
    while(parser.Next(&param)&&!(param.end&&param.name=="parameters")){}
    if(!param.end||param.name!="parameters")goto xml_failed;
    const auto close=xml.rfind("</parameters",parser.position);if(close==xml.npos||close<begin)goto xml_failed;parameters=xml.substr(begin,close-begin);
   }else goto xml_failed;
  }
  if(!closed||vertex.empty()||fragment.empty())goto xml_failed;
  std::size_t parameterCount{},stride{};
  if(!Parameters(parameters,&parameterCount,&stride)){g_State.error=ShaderPipelineError::Type;FreeList(added,true);return false;}
  auto* program=Make(owner,name,vertex,fragment,parameters,backend,vertexEntities,fragmentEntities);
  if(!program){g_State.error=ShaderPipelineError::OutOfMemory;FreeList(added,true);return false;}
  if(!backend.compile(program->view,&program->native)||!program->native){g_State.error=ShaderPipelineError::NativeCompile;Free(program,true);FreeList(added,true);return false;}
  Insert(&added,program);
 }
 if(!emptyRoot&&(tag.name!="shaders"||!tag.end))goto xml_failed;
 // 发布新版本前先等待旧绘制结束。替换同owner时保留其他模组并按PC名字排序。
 if(!emptyRoot&&!g_State.copyProgram){
  auto* copy=Make("runtime","__copy_capture",
   "attribute vec3 Position; attribute vec2 TexCoord; varying vec2 RPlusUV; uniform mat4 Transform;void main(){gl_Position=Transform*vec4(Position,1.0);RPlusUV=TexCoord;}",
   "uniform sampler2D Texture0;varying vec2 RPlusUV;void main(){gl_FragColor=texture2D(Texture0,RPlusUV);}",{},backend);
  if(!copy){g_State.error=ShaderPipelineError::OutOfMemory;FreeList(added,true);return false;}
  if(!backend.compile(copy->view,&copy->native)||!copy->native){Free(copy,true);FreeList(added,true);g_State.error=ShaderPipelineError::NativeCompile;return false;}
  g_State.copyProgram=copy;
 }
 backend.drain();
 for(auto** slot=&g_State.programs;*slot;){auto* p=*slot;if(std::string_view(p->owner)==owner){*slot=p->next;Free(p,true);}else slot=&p->next;}
 while(added){auto* next=added->next;added->next=nullptr;Insert(&g_State.programs,added);added=next;}
 Recount();g_State.error=ShaderPipelineError::None;return true;
xml_failed:
 FreeList(added,true);g_State.error=ShaderPipelineError::Xml;return false;
}
void SetShaderValueProvider(ShaderValueProvider provider) noexcept {g_State.values=provider;}
namespace {
bool IdentityOutput(const Program& p,const float* before) {
 if(p.identity==shader_identity::Kind::None)return false;
 std::size_t activeOffset=0;
 if(p.identity==shader_identity::Kind::InactiveSleeper){
  for(std::size_t i=0;i<p.view.parameterCount;++i)
   if(!std::strcmp(p.parameters[i].name,"ActiveIn"))activeOffset=p.parameters[i].offset;
  if(!activeOffset)return false;
 }
 for(unsigned i=0;i<4;++i){
  const auto* v=p.vertices+i*p.view.strideFloats;
  if(std::memcmp(v,before+i*14,14*sizeof(float)))return false;
  for(unsigned component=3;component<7;++component)if(v[component]!=1.f)return false;
  if(p.identity==shader_identity::Kind::Pixelation&&
     (!std::isfinite(v[14])||v[14]>0.001f||v[14]!=p.vertices[14]))return false;
  if(p.identity==shader_identity::Kind::InactiveSleeper&&v[activeOffset]!=0.f)return false;
 }
 return true;
}
}
bool BeginShaderFrame() noexcept {
 if(!g_State.programs||g_State.active){return false;}
 const auto& backend=g_State.programs->backend;
 ShaderFrameInfo frame{};if(!backend.frameInfo(&frame)||!frame.width||!frame.height){g_State.error=ShaderPipelineError::Target;return false;}
 if(g_State.targetWidth!=frame.width||g_State.targetHeight!=frame.height||g_State.targetBackend.createTarget!=backend.createTarget) {
  backend.drain();if(g_State.targetBackend.releaseTarget)for(auto& target:g_State.targets)g_State.targetBackend.releaseTarget(&target);
  g_State.targetBackend=backend;
  g_State.targetWidth=0;g_State.targetHeight=0;
  if(!backend.createTarget(frame.width,frame.height,"PC custom shader capture",&g_State.targets[0])||
     !backend.createTarget(frame.width,frame.height,"PC custom shader intermediate",&g_State.targets[1])) {
   for(auto& target:g_State.targets){backend.releaseTarget(&target);}
   g_State.error=ShaderPipelineError::Target;return false;
  }
  g_State.targetWidth=frame.width;g_State.targetHeight=frame.height;
 }
 g_State.frame=frame;g_State.frameBackend=&backend;g_State.active=true;++g_State.frames;
 return true;
}
bool CaptureShaderScreenTarget() noexcept {
 if(!g_State.active||g_State.finishing){return false;}
 g_State.frame.previous={};g_State.frame.previousFlag=true;
 g_State.frameBackend->target(g_State.targets[0],true);g_State.frameBackend->clear();return true;
}
void FinishShaderFrame(std::uintptr_t manager) noexcept {
 if(!g_State.active||g_State.finishing){return;}
 g_State.finishing=true;
 const auto& backend=*g_State.frameBackend;unsigned source=0;bool pendingCopy=false;
 for(auto* p=g_State.programs;p;p=p->next) {
  for(unsigned i=0;i<4;++i)std::memset(p->vertices+i*p->view.strideFloats+14,0,(p->view.strideFloats-14)*sizeof(float));
  if(!backend.standardVertices(g_State.targets[source],g_State.frame,p->vertices,p->view.strideFloats)){
   g_State.error=ShaderPipelineError::Target;g_State.finishing=false;AbortShaderFrame();return;
  }
  float standardBefore[4*14];
  if(p->identity!=shader_identity::Kind::None)
   for(unsigned i=0;i<4;++i)std::memcpy(standardBefore+i*14,p->vertices+i*p->view.strideFloats,14*sizeof(float));
  const bool valuesOk=!g_State.values||g_State.values(p->view,p->vertices,manager);
  if(!valuesOk){
   ++g_State.valueFailures;g_State.error=ShaderPipelineError::Values;
   for(unsigned i=0;i<4;++i)std::memset(p->vertices+i*p->view.strideFloats+14,0,(p->view.strideFloats-14)*sizeof(float));
  }
  if(backend.flushPending)backend.flushPending();
  if(g_State.unloadPending){
   // Lua回调返回后才释放Program；先用原生标准shader拷回已画好的场景。
   backend.target(g_State.frame.previous,g_State.frame.previousFlag);backend.clear();
   float standard[4*14]{};
   if(backend.standardVertices(g_State.targets[source],g_State.frame,standard,14))
    backend.draw(g_State.targets[source],g_State.copyProgram->native,standard,4,14*sizeof(float));
   g_State.active=false;g_State.finishing=false;return; // 原Present结束后才释放GPU对象。
  }
  // 作者回调与其绘制批次已经按原顺序提交。原图输出无需另清目标/绘制；
  // 保留同一源图供下一项消费，末尾只做一次必要的屏幕输出。
  if(valuesOk&&IdentityOutput(*p,standardBefore)){pendingCopy=true;continue;}
  const auto destination=p->next?g_State.targets[1-source]:g_State.frame.previous;
  backend.target(destination,p->next?true:g_State.frame.previousFlag);backend.clear();
  backend.draw(g_State.targets[source],p->native,p->vertices,4,static_cast<unsigned>(p->view.strideFloats*sizeof(float)));
  ++g_State.passes;source=1-source;pendingCopy=false;
 }
 if(pendingCopy){
  float standard[4*14]{};
  if(!backend.standardVertices(g_State.targets[source],g_State.frame,standard,14)){
   g_State.error=ShaderPipelineError::Target;g_State.finishing=false;AbortShaderFrame();return;
  }
  backend.target(g_State.frame.previous,g_State.frame.previousFlag);backend.clear();
  backend.draw(g_State.targets[source],g_State.copyProgram->native,standard,4,14*sizeof(float));
  ++g_State.passes;
 }
 backend.target(g_State.frame.previous,g_State.frame.previousFlag);g_State.active=false;g_State.finishing=false;
}
void AbortShaderFrame() noexcept {
 if(g_State.active){g_State.frameBackend->target(g_State.frame.previous,g_State.frame.previousFlag);g_State.active=false;}
 if(g_State.unloadPending&&!g_State.finishing){g_State.unloadPending=false;UnloadShaderPrograms();}
}
void UnloadShaderPrograms() noexcept {
 if(g_State.active){g_State.unloadPending=true;return;}
 AbortShaderFrame();if(g_State.targetBackend.drain)g_State.targetBackend.drain();
 if(g_State.targetBackend.releaseTarget)for(auto& target:g_State.targets)g_State.targetBackend.releaseTarget(&target);
 if(g_State.programs){g_State.programs->backend.drain();FreeList(g_State.programs,true);}
 Free(g_State.copyProgram,true);g_State.copyProgram=nullptr;
 g_State.programs=nullptr;g_State.count=0;g_State.bytes=0;g_State.targetWidth=0;g_State.targetHeight=0;
}
ShaderPipelineStats ShaderPipelineStatsSnapshot() noexcept {return{g_State.count,g_State.bytes,g_State.frames,g_State.passes,g_State.valueFailures,g_State.error};}
}
