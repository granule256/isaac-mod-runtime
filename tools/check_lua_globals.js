#!/usr/bin/env node
// 检查模组脚本里"被调用、但本文件没定义、也不在运行时白名单里"的裸名字。
//
// 为什么需要它：我们没有 Lua 解释器（`check_lua_syntax.js` 只查语法），
// 而这类错——**调用了不存在/已被删掉的函数**——语法上完全合法，只在真机上炸：
// 2026-09-17 就发生过一次（编辑脚本时把 `GrantTestSet` 的定义连同旧代码一起删掉，
// 只剩调用），真机表现是模组第一帧报错、屏幕上什么都没有。
//
// 用法：node tools/check_lua_globals.js <文件…>
const fs = require('fs');
const luaparse = require('/tmp/node_modules/luaparse');

//: 运行时与游戏提供的全局（以及 Lua 标准库），出现这些不算"未定义"。
const WHITELIST = new Set([
  'RegisterMod', 'Game', 'Isaac', 'ModCallbacks', 'Font', 'Color', 'Input',
  // 注意：**没有** `game` —— 我们运行时并不注入它（EID 自己 `local game = Game()`）。
  // 2026-09-17 探针就栽在这个假设上，屏幕上显示"玩家数=?"。`game` 留在下面是刻意保留的
  // 反例提示：谁再写裸 `game` 也不会被白名单放过。
  'EID',
  'ButtonAction', 'EntityType', 'PickupVariant', 'CollectibleType', 'PlayerForm',
  'Vector', 'Sprite', 'MusicManager', 'SFXManager', 'Options', 'Sound',
  'pcall', 'xpcall', 'tostring', 'tonumber', 'type', 'pairs', 'ipairs', 'next',
  'table', 'string', 'math', 'os', 'io', 'print', 'require', 'error', 'assert',
  'setmetatable', 'getmetatable', 'rawget', 'rawset', 'rawequal', 'select',
  'unpack', 'loadstring', 'load', 'collectgarbage', 'tostring', 'utf8',
]);

function walk(node, visit) {
  if (node === null || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach((child) => walk(child, visit)); return; }
  if (typeof node.type === 'string') visit(node);
  for (const value of Object.values(node)) walk(value, visit);
}

let failed = 0;
for (const file of process.argv.slice(2)) {
  const source = fs.readFileSync(file, 'utf8');
  const defined = new Set();
  const called = new Map(); // 名字 → 首次出现的行号

  walk(luaparse.parse(source, { luaVersion: '5.3' }), (node) => {
    if (node.type === 'FunctionDeclaration' && node.identifier &&
        node.identifier.type === 'Identifier') {
      defined.add(node.identifier.name);
    }
    if (node.type === 'Identifier' && node.isLocal) defined.add(node.name);
    if (node.type === 'CallExpression' && node.base &&
        node.base.type === 'Identifier') {
      const name = node.base.name;
      if (!called.has(name)) called.set(name, node.loc ? node.loc.start.line : 0);
    }
  });

  const suspicious = [...called.entries()]
    .filter(([name]) => !defined.has(name) && !WHITELIST.has(name))
    .sort((a, b) => a[1] - b[1]);
  if (suspicious.length === 0) {
    console.log('ok   ' + file);
  } else {
    failed += 1;
    console.error('FAIL ' + file);
    for (const [name, line] of suspicious) {
      console.error(`     第 ${line} 行调用了 ${name}()，但本文件没定义它、也不在白名单里`);
    }
  }
}
process.exit(failed === 0 ? 0 : 1);
