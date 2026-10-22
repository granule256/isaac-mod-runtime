#pragma once
#include "game_file_reader.hpp"
namespace isaac::runtime {
using ModShaderPathResolver = bool (*)(void*, const char*, char*, std::size_t);
// resolver只查询路径表：答不存在时不打开文件；答存在时提供挂载绝对路径。
bool LoadModShaderFile(const GameFileReader::Bindings&, const char* root,
                       ModShaderPathResolver resolver, void* context) noexcept;
}
