#include "application/shader/mod_shader_loader.hpp"
#include "application/shader/shader_pipeline.hpp"
#include "application/shader/native_shader_backend.hpp"
#include <array>
#include <cstdlib>
#include <cstring>
#include <limits>
namespace isaac::runtime {
bool LoadModShaderFile(const GameFileReader::Bindings& files, const char* root,
                       ModShaderPathResolver resolver, void* context) noexcept {
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
 if (!root || !root[0] || !resolver || !files.construct || !files.openRead ||
     !files.getLength || !files.read || !files.close || !files.destroy) return false;
 constexpr char suffix[] = "/content/shaders.xml";
 std::array<char, 512> path{}, mounted{};
 const auto length = std::strlen(root);
 if (length > path.size() - sizeof(suffix)) return false;
 std::memcpy(path.data(), root, length);
 std::memcpy(path.data() + length, suffix, sizeof(suffix));
 // KAGE File::OpenRead对无效挂载名/缺文件会Abort，不能用它探测可选声明。
 // 与metadata/角色/道具名字读取复用同一个先解析再读取的来源。
 if (!resolver(context, path.data(), mounted.data(), mounted.size())) return true;
 if (!std::memchr(mounted.data(), '\0', mounted.size())) return false;
 const auto* colon = std::strchr(mounted.data(), ':');
 if (!colon || colon == mounted.data() || std::strchr(mounted.data(), '/') != colon + 1)
     return false;
 std::size_t capacity=4096,size=0;
 auto* buffer=static_cast<unsigned char*>(std::malloc(capacity));if(!buffer)return false;
 auto result=GameFileReader::ReadTextFile(files,mounted.data(),buffer,capacity,&size);
 if(result==GameFileReader::TextReadResult::LengthOutOfRange&&size>capacity&&
    size<static_cast<std::size_t>(std::numeric_limits<int>::max())) {
  std::free(buffer);capacity=size+1;buffer=static_cast<unsigned char*>(std::malloc(capacity));
  if(!buffer)return false;
  result=GameFileReader::ReadTextFile(files,mounted.data(),buffer,capacity,&size);
 }
 // 已确认存在却读取失败必须报失败，不能与合法无声明混为一谈。
 const bool success=result==GameFileReader::TextReadResult::Success&&
  LoadShaderXml(root,{reinterpret_cast<const char*>(buffer),size},NativeShaderBackend());
 std::free(buffer);return success;
#else
 static_cast<void>(files);static_cast<void>(root);static_cast<void>(resolver);
 static_cast<void>(context);return true;
#endif
}
}
