#pragma once
#include <array>
#include <cstdint>
#include <string_view>
namespace isaac::runtime::shader_identity {
enum class Kind : unsigned char {
 None, Copy, Pixelation, InactiveSleeper, ExtendedCopy, ReverieGeneral, ReverieTimeWarp, ReverieBloodboon
};
// 已核对的完整作者程序，仅以源码和接口识别，不依赖owner或shader名称。
// 来源：BOIStageAPI15/content/shaders.xml。加载时比较；帧上不解析GLSL。
inline constexpr std::string_view kCopyVertex = R"GLSL(
            attribute vec3 Position;
            attribute vec4 Color;
            attribute vec2 TexCoord;
            attribute vec4 RenderData;
            attribute float Scale;

            varying lowp vec4 Color0;
            varying mediump vec2 TexCoord0;
            varying lowp vec4 RenderDataOut;
            varying lowp float ScaleOut;
            uniform sampler2D Texture0;

            uniform mat4 Transform;
            void main(void)
            {
                RenderDataOut = RenderData;
                ScaleOut = Scale;
                Color0 = Color;
                TexCoord0 = TexCoord;
                gl_Position = Transform * vec4(Position.xyz, 1.0);
            }
        )GLSL";
inline constexpr std::string_view kCopyFragment = R"GLSL(
            varying lowp vec4 Color0;
            varying mediump vec2 TexCoord0;
            varying lowp vec4 RenderDataOut;
            varying lowp float ScaleOut;
            uniform sampler2D Texture0;
            void main(void)
            {
                vec4 Color = Color0 * texture2D(Texture0, TexCoord0);
                gl_FragColor = Color;
            }
        )GLSL";
// Same copy operation with the smaller interface used by completion-mark HUDs.
inline constexpr std::string_view kSimpleCopyVertex = R"GLSL(
attribute vec3 Position; attribute vec4 Color; attribute vec2 TexCoord;
varying vec4 Color0; varying vec2 TexCoord0; uniform mat4 Transform;
void main(void) {Color0=Color;TexCoord0=TexCoord;gl_Position=Transform*vec4(Position.xyz,1.0);}
)GLSL";
inline constexpr std::string_view kSimpleCopyFragment = R"GLSL(
varying lowp vec4 Color0; varying mediump vec2 TexCoord0;
uniform sampler2D Texture0;
void main(void) {vec4 col=texture2D(Texture0,TexCoord0);gl_FragColor=Color0*col;}
)GLSL";
inline constexpr std::string_view kPixelVertex = R"GLSL(

    attribute vec3 Position;
    attribute vec4 Color;
    attribute vec2 TexCoord;
    attribute float PixelAmount;
    attribute vec4 RenderData;
    attribute float Scale;

    varying vec4 Color0;
    varying vec2 TexCoord0;
    varying float OutPixelAmount;
    varying vec4 RenderDataOut;
    varying float ScaleOut;

    uniform mat4 Transform;

    void main(void) {
        OutPixelAmount = PixelAmount;
        RenderDataOut = RenderData;
        Color0 = Color;
        gl_Position = Transform * vec4(Position.xyz, 1.0);
        TexCoord0 = TexCoord;
    }
    )GLSL";
inline constexpr std::string_view kPixelFragment = R"GLSL(
    varying vec4 Color0;
    varying vec2 TexCoord0;
    varying float OutPixelAmount;
    varying vec4 RenderDataOut;
    varying float ScaleOut;
    uniform sampler2D Texture0;

    void main(void)
    {
    if (OutPixelAmount > 0.001) {
        vec2 pa = OutPixelAmount * 0.5 * min(RenderDataOut.z, RenderDataOut.w) / RenderDataOut.zw;

        vec2 center = RenderDataOut.xy * 0.5 / RenderDataOut.zw;
        vec2 snapCoord = TexCoord0.st - mod(TexCoord0.st - center, pa) + pa * 0.5;

        vec4 Color = Color0 * texture2D(Texture0, snapCoord);

        gl_FragColor = Color; //Color0 * texture2D(Texture0, snapCoord);
    } else {
        vec4 Color = Color0 * texture2D(Texture0, TexCoord0);
        gl_FragColor = Color; //Color0 * texture2D(Texture0, TexCoord0);
    }
    }
    )GLSL";

inline bool Space(char c){return c==' '||c=='\t'||c=='\r'||c=='\n';}
inline bool Word(char c){return(c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_';}
inline std::string_view Token(std::string_view& source) {
 while(!source.empty()) {
  if(Space(source.front())){source.remove_prefix(1);continue;}
  if(source.substr(0,2)=="//"){
   const auto end=source.find('\n');source=end==source.npos?std::string_view{}:source.substr(end+1);continue;
  }
  if(source.substr(0,2)=="/*"){
   const auto end=source.find("*/",2);
   if(end==source.npos){const auto invalid=source;source={};return invalid;}
   source.remove_prefix(end+2);continue;
  }
  break;
 }
 if(source.empty())return {};
 std::size_t n=1;
 const char c=source.front();
 if((c>='0'&&c<='9')||(c=='.'&&source.size()>1&&source[1]>='0'&&source[1]<='9')){
  while(n<source.size()){
   const char next=source[n],previous=source[n-1];
   if(Word(next)||next=='.'||((next=='+'||next=='-')&&(previous=='e'||previous=='E'||previous=='p'||previous=='P')))++n;
   else break;
  }
 }else if(Word(c)){
  while(n<source.size()&&Word(source[n]))++n;
 }else {
  const auto two=source.substr(0,2),three=source.substr(0,3);
  if(three=="<<="||three==">>=")n=3;
  else if(two=="++"||two=="--"||two=="<="||two==">="||two=="=="||two=="!="||
          two=="&&"||two=="||"||two=="^^"||two=="<<"||two==">>"||
          two=="+="||two=="-="||two=="*="||two=="/="||two=="%="||two=="&="||two=="|="||two=="^=")n=2;
 }
 const auto token=source.substr(0,n);source.remove_prefix(n);return token;
}
inline bool SameCode(std::string_view left,std::string_view right) {
 for(;;){const auto a=Token(left),b=Token(right);if(a!=b)return false;if(a.empty())return true;}
}
// Identify the complete known token stream at load time without embedding the
// mod's program. This is a content fingerprint, not an authorization digest.
inline std::array<std::uint64_t,3> Fingerprint(std::string_view source) {
 std::array<std::uint64_t,3> out{0xcbf29ce484222325ULL,0x84222325cbf29ce4ULL,0};
 while(!source.empty()){
  const auto token=Token(source);if(token.empty())break;
  for(const unsigned char c:token){out[0]=(out[0]^c)*0x100000001b3ULL;out[1]=(out[1]^c)*0x9e3779b185ebca87ULL;}
  out[0]*=0x100000001b3ULL;out[1]*=0x9e3779b185ebca87ULL;++out[2];
 }
 return out;
}
inline Kind Classify(std::string_view vertex,std::string_view fragment) {
 if(SameCode(vertex,kCopyVertex)&&SameCode(fragment,kCopyFragment))return Kind::Copy;
 if(SameCode(vertex,kSimpleCopyVertex)&&SameCode(fragment,kSimpleCopyFragment))return Kind::Copy;
 if(SameCode(vertex,kPixelVertex)&&SameCode(fragment,kPixelFragment))return Kind::Pixelation;
 using Code = std::array<std::uint64_t,3>;
 const auto vertexCode = Fingerprint(vertex);
 const auto fragmentCode = Fingerprint(fragment);
 // These complete token streams copy the source when their effect controls are idle.
 if ((vertexCode == Code{0xba149295e49edea6ULL,0x2f4b26df74b3551bULL,76} &&
      fragmentCode == Code{0x14020f1c1a164bcbULL,0xf306a94956a901a4ULL,43}) ||
     (vertexCode == Code{0xcdc72f96bb1e8316ULL,0x07a77cdcf3fe5bebULL,52} &&
      fragmentCode == Code{0xd3b3deb299b4ab42ULL,0x737fdd4f1a9d9bafULL,37}))
  return Kind::ExtendedCopy;
 if (vertexCode == Code{0x4956901e045b1fb1ULL,0x6e69305d803b72ecULL,129} &&
     fragmentCode == Code{0xa5c3dc22c98140fcULL,0x61c57fc0e9da96e3ULL,373})
  return Kind::ReverieGeneral;
 if (vertexCode == Code{0x48e4763bb1e97d61ULL,0x2c674072dbdd82b8ULL,103} &&
     fragmentCode == Code{0x716902d3fcf84befULL,0x07a5758dc51996b62ULL,393})
  return Kind::ReverieTimeWarp;
 if (vertexCode == Code{0xd9a747604472f728ULL,0x6d055091a834b1dbULL,207} &&
     fragmentCode == Code{0xa9dea9bcd00bcc61ULL,0x96417c8fb3e6b4ecULL,544})
  return Kind::ReverieBloodboon;
 // Fiend Folio content/shaders.xml: full vertex/fragment token fingerprints.
 if(vertexCode==Code{0x500de42fc82865a8ULL,0x5ab439d0570becadULL,392}&&
    fragmentCode==Code{0xe45705619995a5e8ULL,0x952c900d8aea0eafULL,978})
  return Kind::InactiveSleeper;
 return Kind::None;
}
} // namespace isaac::runtime::shader_identity
