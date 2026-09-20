#!/usr/bin/env node
// Lua 语法检查（luaparse，Lua 5.3）：改模组脚本前后都跑一次。
//
// 为什么需要它：我们的环境里**没有 Lua 解释器**（本机没有 lua/luajit，devkitpro 容器里也没有），
// 而模组脚本写错语法 → 模组整体不加载 → 真机上表现为"屏幕上一个字都没有"，
// 只能靠用户重启游戏来发现，代价太高（2026-09-17 就是这么绕了一圈）。
//
// 用法：node tools/check_lua_syntax.js <文件…>
//       （依赖 /tmp/node_modules/luaparse：npm install --prefix /tmp luaparse）
const fs = require('fs');
const path = require('path');
let luaparse;
try {
  luaparse = require('/tmp/node_modules/luaparse');
} catch (error) {
  console.error('缺少 luaparse：npm install --prefix /tmp luaparse');
  process.exit(2);
}
let failed = 0;
for (const file of process.argv.slice(2)) {
  try {
    luaparse.parse(fs.readFileSync(file, 'utf8'), { luaVersion: '5.3' });
    console.log('ok   ' + path.basename(file));
  } catch (error) {
    failed += 1;
    console.error('FAIL ' + file + '\n     ' + error.message);
  }
}
process.exit(failed === 0 ? 0 : 1);
