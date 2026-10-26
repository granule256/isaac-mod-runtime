"""剩余字段的生产访问器合约；只证明宿主Lua/原生缓冲，不冒称真机。

独立布局来源冻结于SOURCE_LEDGER；全对象比较保护邻近字节。
不从生产字段表生成期望；缺少入口或版本依据的12项保留在delegated-unresolved.json。
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

SOURCE_LEDGER = {'GridEntityDoor:Busted': {'kind': 'Bool',
                           'ns_accesses': [{'file': 'dist/apis500-20261016/ns/GridEntity_Door-InitSubclass-0x385f98.txt',
                                            'instruction': '00386000  7906101f  strh       wzr, [x0, #0x308]',
                                            'paired_lane': True},
                                           {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Door-InitSubclass-0x385f98.txt',
                                            'instruction': '00386000  7906101f  strh       wzr, [x0, #0x308]',
                                            'paired_lane': True},
                                           {'file': 'dist/apis500-20261016/ns-proof/GridEntity_Door-TryBlowOpen-0x384700.txt',
                                            'instruction': '00384860  390c2674  strb       w20, [x19, '
                                                           '#0x309]',
                                            'paired_lane': False},
                                           {'file': 'dist/apis500-20261016/ns-proof/GridEntity_Door-TryBlowOpen-0x384700.txt',
                                            'instruction': '00384a88  390c2674  strb       w20, [x19, '
                                                           '#0x309]',
                                            'paired_lane': False},
                                           {'file': 'dist/apis500-20261016/ns-proof/GridEntity_Door-TryBlowOpen-0x384700.txt',
                                            'instruction': '00384d38  390c2668  strb       w8, [x19, #0x309]',
                                            'paired_lane': False}],
                           'ns_semantics': 'PC Slot getter7fa7e0/原setter及ExtraVisible278/Busted279 bool登记；NS '
                                           'Door::SetRoomTypes/SetDirection及InitSubclass核Slot1a0、Extra '
                                           'ANM2从1b0起至308，308/309为可见/打破单byte；PreviousState/Variant为PC坏userdata，未冒充整数。',
                           'offset': 777,
                           'pc': {'call': '0x80835f',
                                  'name': 'Busted',
                                  'native_or_field': '0x279',
                                  'owner': 'Grid',
                                  'registrar': '0x827f00',
                                  'ret': 12,
                                  'values': [1, 633, 11877144],
                                  'wrapper': '0x85b670'}},
 'GridEntityDoor:CloseAnimation': {'kind': 'field',
                                   'ns_complete_files': ['ns-additional/GridEntity_Door-InitSubclass-0x385f98.txt',
                                                         'ns-additional/GridEntity_Door-SetDirection-0x385f7c.txt',
                                                         'ns-additional/GridEntity_Door-SetRoomTypes-0x385a78.txt',
                                                         'ns-additional/GridEntity_Door-Update-0x38175c.txt',
                                                         'ns-extra/GridEntity_Door-~GridEntity_Door-386138.txt',
                                                         'ns-extra/GridEntity_Door-~GridEntity_Door-3861cc.txt'],
                                   'ns_semantics': 'PC4个std::string字段偏移28C/2A4/2BC/2D4，对照NS '
                                                   'Update/SetRoomTypes消费与析构四个独立string320/338/350/368；写入复用游戏libc++赋值。锁门判断读真实Variant '
                                                   'C，Busted309，偏移为Grid Sprite48+ANM2 '
                                                   'offsetD4，GetSpriteOffset const借用并校验原网格owner。',
                                   'offset': 824,
                                   'pc': {'call': '0x808382',
                                          'name': 'CloseAnimation',
                                          'native_or_field': '0x2a4',
                                          'owner': 'all',
                                          'registrar': '0x828370',
                                          'ret': 12,
                                          'values': [1, 676, 11877072],
                                          'wrapper': '0x85b9a0'},
                                   'value_kind': 'String'},
 'GridEntityDoor:ExtraVisible': {'kind': 'Bool',
                                 'ns_accesses': [{'file': 'dist/apis500-20261016/ns/GridEntity_Door-InitSubclass-0x385f98.txt',
                                                  'instruction': '00386000  7906101f  strh       wzr, [x0, '
                                                                 '#0x308]',
                                                  'paired_lane': False},
                                                 {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Door-InitSubclass-0x385f98.txt',
                                                  'instruction': '00386000  7906101f  strh       wzr, [x0, '
                                                                 '#0x308]',
                                                  'paired_lane': False}],
                                 'ns_semantics': 'PC Slot getter7fa7e0/原setter及ExtraVisible278/Busted279 '
                                                 'bool登记；NS '
                                                 'Door::SetRoomTypes/SetDirection及InitSubclass核Slot1a0、Extra '
                                                 'ANM2从1b0起至308，308/309为可见/打破单byte；PreviousState/Variant为PC坏userdata，未冒充整数。',
                                 'offset': 776,
                                 'pc': {'call': '0x808358',
                                        'name': 'ExtraVisible',
                                        'native_or_field': '0x278',
                                        'owner': 'Grid',
                                        'registrar': '0x827f00',
                                        'ret': 12,
                                        'values': [1, 632, 11877188],
                                        'wrapper': '0x85b670'}},
 'GridEntityDoor:LockedAnimation': {'kind': 'field',
                                    'ns_complete_files': ['ns-additional/GridEntity_Door-InitSubclass-0x385f98.txt',
                                                          'ns-additional/GridEntity_Door-SetDirection-0x385f7c.txt',
                                                          'ns-additional/GridEntity_Door-SetRoomTypes-0x385a78.txt',
                                                          'ns-additional/GridEntity_Door-Update-0x38175c.txt',
                                                          'ns-extra/GridEntity_Door-~GridEntity_Door-386138.txt',
                                                          'ns-extra/GridEntity_Door-~GridEntity_Door-3861cc.txt'],
                                    'ns_semantics': 'PC4个std::string字段偏移28C/2A4/2BC/2D4，对照NS '
                                                    'Update/SetRoomTypes消费与析构四个独立string320/338/350/368；写入复用游戏libc++赋值。锁门判断读真实Variant '
                                                    'C，Busted309，偏移为Grid Sprite48+ANM2 '
                                                    'offsetD4，GetSpriteOffset const借用并校验原网格owner。',
                                    'offset': 848,
                                    'pc': {'call': '0x808389',
                                           'name': 'LockedAnimation',
                                           'native_or_field': '0x2bc',
                                           'owner': 'all',
                                           'registrar': '0x828370',
                                           'ret': 12,
                                           'values': [1, 700, 11877088],
                                           'wrapper': '0x85b9a0'},
                                    'value_kind': 'String'},
 'GridEntityDoor:OpenAnimation': {'kind': 'field',
                                  'ns_complete_files': ['ns-additional/GridEntity_Door-InitSubclass-0x385f98.txt',
                                                        'ns-additional/GridEntity_Door-SetDirection-0x385f7c.txt',
                                                        'ns-additional/GridEntity_Door-SetRoomTypes-0x385a78.txt',
                                                        'ns-additional/GridEntity_Door-Update-0x38175c.txt',
                                                        'ns-extra/GridEntity_Door-~GridEntity_Door-386138.txt',
                                                        'ns-extra/GridEntity_Door-~GridEntity_Door-3861cc.txt'],
                                  'ns_semantics': 'PC4个std::string字段偏移28C/2A4/2BC/2D4，对照NS '
                                                  'Update/SetRoomTypes消费与析构四个独立string320/338/350/368；写入复用游戏libc++赋值。锁门判断读真实Variant '
                                                  'C，Busted309，偏移为Grid Sprite48+ANM2 '
                                                  'offsetD4，GetSpriteOffset const借用并校验原网格owner。',
                                  'offset': 800,
                                  'pc': {'call': '0x80837b',
                                         'name': 'OpenAnimation',
                                         'native_or_field': '0x28c',
                                         'owner': 'all',
                                         'registrar': '0x828370',
                                         'ret': 12,
                                         'values': [1, 652, 11877128],
                                         'wrapper': '0x85b9a0'},
                                  'value_kind': 'String'},
 'GridEntityDoor:OpenLockedAnimation': {'kind': 'field',
                                        'ns_complete_files': ['ns-additional/GridEntity_Door-InitSubclass-0x385f98.txt',
                                                              'ns-additional/GridEntity_Door-SetDirection-0x385f7c.txt',
                                                              'ns-additional/GridEntity_Door-SetRoomTypes-0x385a78.txt',
                                                              'ns-additional/GridEntity_Door-Update-0x38175c.txt',
                                                              'ns-extra/GridEntity_Door-~GridEntity_Door-386138.txt',
                                                              'ns-extra/GridEntity_Door-~GridEntity_Door-3861cc.txt'],
                                        'ns_semantics': 'PC4个std::string字段偏移28C/2A4/2BC/2D4，对照NS '
                                                        'Update/SetRoomTypes消费与析构四个独立string320/338/350/368；写入复用游戏libc++赋值。锁门判断读真实Variant '
                                                        'C，Busted309，偏移为Grid Sprite48+ANM2 '
                                                        'offsetD4，GetSpriteOffset const借用并校验原网格owner。',
                                        'offset': 872,
                                        'pc': {'call': '0x808390',
                                               'name': 'OpenLockedAnimation',
                                               'native_or_field': '0x2d4',
                                               'owner': 'all',
                                               'registrar': '0x828370',
                                               'ret': 12,
                                               'values': [1, 724, 11877292],
                                               'wrapper': '0x85b9a0'},
                                        'value_kind': 'String'},
 'GridEntityPit:HasLadder': {'kind': 'Bool',
                             'ns_accesses': [{'file': 'dist/apis500-20261016/ns/GridEntity_Pit-InitSubclass-0x388744.txt',
                                              'instruction': '003887b0  3906827f  strb       wzr, [x19, '
                                                             '#0x1a0]',
                                              'paired_lane': False},
                                             {'file': 'dist/apis500-20261016/ns/GridEntity_Pit-SetLadder-0x38966c.txt',
                                              'instruction': '0038967c  39068008  strb       w8, [x0, '
                                                             '#0x1a0]',
                                              'paired_lane': False},
                                             {'file': 'dist/apis500-20261016/ns/GridEntity_Pit-SetLadder-0x38966c.txt',
                                              'instruction': '00389748  39468268  ldrb       w8, [x19, '
                                                             '#0x1a0]',
                                              'paired_lane': False},
                                             {'file': 'dist/apis500-20261016/ns/GridEntity_Pit-Update-0x387bec.txt',
                                              'instruction': '00387e3c  39468268  ldrb       w8, [x19, '
                                                             '#0x1a0]',
                                              'paired_lane': False},
                                             {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Pit-InitSubclass-0x388744.txt',
                                              'instruction': '003887b0  3906827f  strb       wzr, [x19, '
                                                             '#0x1a0]',
                                              'paired_lane': False},
                                             {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Pit-SetLadder-0x38966c.txt',
                                              'instruction': '0038967c  39068008  strb       w8, [x0, '
                                                             '#0x1a0]',
                                              'paired_lane': False},
                                             {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Pit-SetLadder-0x38966c.txt',
                                              'instruction': '00389748  39468268  ldrb       w8, [x19, '
                                                             '#0x1a0]',
                                              'paired_lane': False},
                                             {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Pit-Update-0x387bec.txt',
                                              'instruction': '00387e3c  39468268  ldrb       w8, [x19, '
                                                             '#0x1a0]',
                                              'paired_lane': False}],
                             'ns_semantics': 'PC154 HasLadder的bool裸字段setter；NS '
                                             'SetLadder38967c直接写1a0且389748读取该字节更新格子碰撞。属性本身按PC裸赋值，和SetLadder方法副作用区分。',
                             'offset': 416,
                             'pc': {'call': '0x80847d',
                                    'name': 'HasLadder',
                                    'native_or_field': '0x154',
                                    'owner': 'Grid',
                                    'registrar': '0x828b20',
                                    'ret': 12,
                                    'values': [1, 340, 11877408],
                                    'wrapper': '0x85be30'}},
 'GridEntityPoop:ReviveTimer': {'kind': 'Int',
                                'ns_accesses': [{'file': 'dist/apis500-20261016/ns/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a59c  b901a27f  str        wzr, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389b10  b901a27f  str        wzr, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389be4  b941a268  ldr        w8, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389bf0  b901a268  str        w8, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a59c  b901a27f  str        wzr, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389b10  b901a27f  str        wzr, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389be4  b941a268  ldr        w8, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389bf0  b901a268  str        w8, [x19, '
                                                                '#0x1a0]',
                                                 'paired_lane': False}],
                                'ns_semantics': 'PC ReviveTimer154 i32、UnderPlayer170 bool；NS '
                                                'Update389be4递减1a0重生计数，389f10/389fd8读写1c0的玩家占用状态；按相同玩家位置碰撞算法与PC '
                                                'InitSubclass/Update交叉。',
                                'offset': 416,
                                'pc': {'call': '0x808406',
                                       'name': 'ReviveTimer',
                                       'native_or_field': '0x154',
                                       'owner': 'Grid',
                                       'registrar': '0x828560',
                                       'ret': 12,
                                       'values': [1, 340, 11877232],
                                       'wrapper': '0x85bb20'}},
 'GridEntityPoop:StateAnimation': {'kind': 'field',
                                   'ns_complete_files': ['ns-additional/GridEntity_Poop-GetPoopAnimation-0x38a268.txt',
                                                         'ns-additional/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                         'ns-additional/GridEntity_Poop-Update-0x389828.txt',
                                                         'ns-extra/GridEntity_Poop-GetPoopAnimation-38a268.txt',
                                                         'ns-extra/GridEntity_Poop-~GridEntity_Poop-3897a0.txt',
                                                         'ns-extra/GridEntity_Poop-~GridEntity_Poop-3897e0.txt'],
                                   'ns_semantics': 'StateAnimation为PC std::string158，NS Poop析构明确测试1A8的libc++ '
                                                   'SSO long bit、解放1B8数据指针；结合完整对象尾部和Init/Update，按同字符串ABI读写。',
                                   'offset': 424,
                                   'pc': {'call': '0x80840d',
                                          'name': 'StateAnimation',
                                          'native_or_field': '0x158',
                                          'owner': 'all',
                                          'registrar': '0x8286e0',
                                          'ret': 12,
                                          'values': [1, 344, 11877244],
                                          'wrapper': '0x85bbe0'},
                                   'value_kind': 'String'},
 'GridEntityPoop:UnderPlayer': {'kind': 'Bool',
                                'ns_accesses': [{'file': 'dist/apis500-20261016/ns/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a3f4  7903801f  strh       wzr, [x0, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a4c0  39070269  strb       w9, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a4d8  39470268  ldrb       w8, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389f10  39470268  ldrb       w8, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389fd8  3907027f  strb       wzr, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a3f4  7903801f  strh       wzr, [x0, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a4c0  39070269  strb       w9, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-InitSubclass-0x38a3cc.txt',
                                                 'instruction': '0038a4d8  39470268  ldrb       w8, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389f10  39470268  ldrb       w8, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False},
                                                {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Poop-Update-0x389828.txt',
                                                 'instruction': '00389fd8  3907027f  strb       wzr, [x19, '
                                                                '#0x1c0]',
                                                 'paired_lane': False}],
                                'ns_semantics': 'PC ReviveTimer154 i32、UnderPlayer170 bool；NS '
                                                'Update389be4递减1a0重生计数，389f10/389fd8读写1c0的玩家占用状态；按相同玩家位置碰撞算法与PC '
                                                'InitSubclass/Update交叉。',
                                'offset': 448,
                                'pc': {'call': '0x808414',
                                       'name': 'UnderPlayer',
                                       'native_or_field': '0x170',
                                       'owner': 'Grid',
                                       'registrar': '0x828860',
                                       'ret': 12,
                                       'values': [1, 368, 11877204],
                                       'wrapper': '0x85bd60'}},
 'GridEntityRock:FrameCnt': {'kind': 'field',
                             'ns_complete_files': ['ns-additional/GridEntity_Rock-InitSubclass-0x392e40.txt',
                                                   'ns-additional/GridEntity_Rock-Update-0x38f418.txt',
                                                   'ns-extra/GridEntity_Rock-~GridEntity_Rock-3939ec.txt',
                                                   'ns-extra/GridEntity_Rock-~GridEntity_Rock-393a64.txt'],
                             'ns_semantics': 'PC Anim154/RubbleAnim16C/FrameCnt190；NS '
                                             'InitSubclass/析构依次构造/消费1A0/1B8/1D0三string，1E8计时。字段保完整binary '
                                             'string，GetRubbleAnim按PC c_str在首NUL截断。',
                             'offset': 488,
                             'pc': {'call': '0x80851d',
                                    'name': 'FrameCnt',
                                    'native_or_field': '0x190',
                                    'owner': 'all',
                                    'registrar': '0x829050',
                                    'ret': 12,
                                    'values': [1, 400, 11877516],
                                    'wrapper': '0x85c080'},
                             'value_kind': 'Int'},
 'GridEntityRock:RubbleAnim': {'kind': 'field',
                               'ns_complete_files': ['ns-additional/GridEntity_Rock-InitSubclass-0x392e40.txt',
                                                     'ns-additional/GridEntity_Rock-Update-0x38f418.txt',
                                                     'ns-extra/GridEntity_Rock-~GridEntity_Rock-3939ec.txt',
                                                     'ns-extra/GridEntity_Rock-~GridEntity_Rock-393a64.txt'],
                               'ns_semantics': 'PC Anim154/RubbleAnim16C/FrameCnt190；NS '
                                               'InitSubclass/析构依次构造/消费1A0/1B8/1D0三string，1E8计时。字段保完整binary '
                                               'string，GetRubbleAnim按PC c_str在首NUL截断。',
                               'offset': 440,
                               'pc': {'call': '0x808516',
                                      'name': 'RubbleAnim',
                                      'native_or_field': '0x16c',
                                      'owner': 'all',
                                      'registrar': '0x828ee0',
                                      'ret': 12,
                                      'values': [1, 364, 11877504],
                                      'wrapper': '0x85bf00'},
                               'value_kind': 'String'},
 'GridEntitySpikes:Timeout': {'kind': 'Int',
                              'ns_accesses': [{'file': 'dist/apis500-20261016/ns/GridEntity_Spikes-InitSubclass-0x393b34.txt',
                                               'instruction': '00393cc8  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns/GridEntity_Spikes-InitSubclass-0x393b34.txt',
                                               'instruction': '00393d0c  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns/GridEntity_Spikes-InitSubclass-0x393b34.txt',
                                               'instruction': '00393f20  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '00394304  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '003943b8  b941a268  ldr        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '003943c4  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '003943d0  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Spikes-InitSubclass-0x393b34.txt',
                                               'instruction': '00393cc8  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Spikes-InitSubclass-0x393b34.txt',
                                               'instruction': '00393d0c  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Spikes-InitSubclass-0x393b34.txt',
                                               'instruction': '00393f20  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '00394304  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '003943b8  b941a268  ldr        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '003943c4  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False},
                                              {'file': 'dist/apis500-20261016/ns-additional/GridEntity_Spikes-Update-0x3941e4.txt',
                                               'instruction': '003943d0  b901a268  str        w8, [x19, '
                                                              '#0x1a0]',
                                               'paired_lane': False}],
                              'ns_semantics': 'PC Timeout154 i32；NS '
                                              'InitSubclass393cc8写1a0，Update3943b8..3943d0倒计时控制刺伸缩。',
                              'offset': 416,
                              'pc': {'call': '0x808605',
                                     'name': 'Timeout',
                                     'native_or_field': '0x154',
                                     'owner': 'Grid',
                                     'registrar': '0x829890',
                                     'ret': 12,
                                     'values': [1, 340, 11874308],
                                     'wrapper': '0x85c570'}},
 'GridEntityTNT:FrameCnt': {'kind': 'Int',
                            'ns_accesses': [{'file': 'dist/apis500-20261016/ns/GridEntity_TNT-InitSubclass-0x395758.txt',
                                             'instruction': '00395834  b901a268  str        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False},
                                            {'file': 'dist/apis500-20261016/ns/GridEntity_TNT-Update-0x395848.txt',
                                             'instruction': '003958d8  b941a268  ldr        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False},
                                            {'file': 'dist/apis500-20261016/ns/GridEntity_TNT-Update-0x395848.txt',
                                             'instruction': '003958e4  b901a268  str        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False},
                                            {'file': 'dist/apis500-20261016/ns/GridEntity_TNT-Update-0x395848.txt',
                                             'instruction': '00395900  b941a268  ldr        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False},
                                            {'file': 'dist/apis500-20261016/ns-additional/GridEntity_TNT-InitSubclass-0x395758.txt',
                                             'instruction': '00395834  b901a268  str        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False},
                                            {'file': 'dist/apis500-20261016/ns-additional/GridEntity_TNT-Update-0x395848.txt',
                                             'instruction': '003958d8  b941a268  ldr        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False},
                                            {'file': 'dist/apis500-20261016/ns-additional/GridEntity_TNT-Update-0x395848.txt',
                                             'instruction': '003958e4  b901a268  str        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False},
                                            {'file': 'dist/apis500-20261016/ns-additional/GridEntity_TNT-Update-0x395848.txt',
                                             'instruction': '00395900  b941a268  ldr        w8, [x19, '
                                                            '#0x1a0]',
                                             'paired_lane': False}],
                            'ns_semantics': 'PC FrameCnt154 i32；NS '
                                            'InitSubclass395834写1a0，Update3958d8..3958e4读取、递增同一计时并控制爆炸动画。',
                            'offset': 416,
                            'pc': {'call': '0x808556',
                                   'name': 'FrameCnt',
                                   'native_or_field': '0x154',
                                   'owner': 'Grid',
                                   'registrar': '0x8291f0',
                                   'ret': 12,
                                   'values': [1, 340, 11877516],
                                   'wrapper': '0x85c140'}},
 'PlayerTypesPosVel:Position': {'kind': 'field',
                                'ns_semantics': '拥有16字节PosVel；Vector读取副本，整值setter',
                                'pc': {'offset': '0x0',
                                       'registrar': 'pc-posvel-registrar.txt',
                                       'registration': 'pc-registration-params.txt:0x80513E..0x80517C',
                                       'value_copy': True,
                                       'wrapper': 'pc-posvel-wrapper.txt',
                                       'writable': True},
                                'switch': {'evidence': 'ns-GetMultiShotPositionVelocity.txt',
                                           'offset': '0x0',
                                           'type': 'HFA4float'}},
 'PlayerTypesPosVel:Velocity': {'kind': 'field',
                                'ns_semantics': '拥有16字节PosVel；Vector读取副本，整值setter',
                                'pc': {'offset': '0x8',
                                       'registrar': 'pc-posvel-registrar.txt',
                                       'registration': 'pc-registration-params.txt:0x80513E..0x80517C',
                                       'value_copy': True,
                                       'wrapper': 'pc-posvel-wrapper.txt',
                                       'writable': True},
                                'switch': {'evidence': 'ns-GetMultiShotPositionVelocity.txt',
                                           'offset': '0x8',
                                           'type': 'HFA4float'}}}

MAIN = r'''
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/api500_config.guards.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::abort();}}
static void* AssignString(void*dest,const void*source){
 auto*d=static_cast<unsigned char*>(dest);auto*s=static_cast<const unsigned char*>(source);
 std::uint64_t n{};const char*p{};std::memcpy(&n,s+8,8);std::memcpy(&p,s+16,8);
 if(d[0]&1){void*old{};std::memcpy(&old,d+16,8);std::free(old);}
 std::memset(d,0,24);
 if(n<23){d[0]=static_cast<unsigned char>(n*2);std::memcpy(d+1,p,n);}
 else{auto*q=static_cast<char*>(std::malloc(n+1));std::memcpy(q,p,n);q[n]=0;std::uint64_t cap=(n+1)|1;std::memcpy(d,&cap,8);std::memcpy(d+8,&n,8);std::memcpy(d+16,&q,8);}return dest;
}

#include <cassert>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
std::vector<std::vector<unsigned char>> grids(6,std::vector<unsigned char>(0x500));
std::vector<unsigned char> roomConfig(0x80),pillPool(0x1300);
void* Api500WorldRoom(){return g_RoomBytes.data();}
void* Api500WorldPool(){return pillPool.data();}

namespace {
using namespace isaac::runtime;
template<class T>void Change(lua_State*L,unsigned slot,unsigned offset,T value,const char*script){auto expected=grids;WriteAt<T>(expected[slot],offset,value);Run(L,script);assert(expected==grids);}
void Unchanged(lua_State*L,const char*script){auto before=grids;Run(L,script);assert(before==grids);}
void StringChange(lua_State*L,unsigned slot,unsigned offset,const char*script){auto before=grids;Run(L,script);auto expected=before;std::memcpy(expected[slot].data()+offset,grids[slot].data()+offset,24);assert(expected==grids);}
}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
WriteAt<std::uint32_t>(g_RoomBytes,kRoomGridWidthOffset,13);WriteAt<std::uint32_t>(g_RoomBytes,kRoomGridHeightOffset,7);
WriteAt<std::uint32_t>(g_GameBytes,0x21510,1);WriteAt<std::uint32_t>(g_GameBytes,kLevelCurrentRoomIndexOffset,84);WriteAt<std::uint32_t>(g_GameBytes,kLevelCurrentRoomDimensionOffset,0);
WriteAt<std::uint32_t>(g_GameBytes,0x18,84);WriteAt<std::uint32_t>(g_GameBytes,0x1c,84);WriteAt<std::uint32_t>(g_GameBytes,0x20,0);WriteWord(g_GameBytes,0x28,AddressOf(roomConfig));
WriteWord(g_RoomBytes,8,AddressOf(g_GameBytes)+0x18);
WriteWord(grids[0],0,g_EngineBase+kGridEntity_RockVtableOffset);WriteAt<std::uint32_t>(grids[0],8,2);WriteAt<std::uint32_t>(grids[0],0xc,2);WriteAt<std::int32_t>(grids[0],0x10,19);WriteAt<std::uint32_t>(grids[0],0x28,1);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+1*8,AddressOf(grids[0]));
WriteWord(grids[1],0,g_EngineBase+kGridEntity_DoorVtableOffset);WriteAt<std::uint32_t>(grids[1],8,16);WriteAt<std::uint32_t>(grids[1],0xc,2);WriteAt<std::int32_t>(grids[1],0x10,19);WriteAt<std::uint32_t>(grids[1],0x28,2);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+2*8,AddressOf(grids[1]));
WriteWord(grids[2],0,g_EngineBase+kGridEntity_PoopVtableOffset);WriteAt<std::uint32_t>(grids[2],8,14);WriteAt<std::uint32_t>(grids[2],0xc,2);WriteAt<std::int32_t>(grids[2],0x10,19);WriteAt<std::uint32_t>(grids[2],0x28,3);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+3*8,AddressOf(grids[2]));
WriteWord(grids[3],0,g_EngineBase+kGridEntity_PitVtableOffset);WriteAt<std::uint32_t>(grids[3],8,7);WriteAt<std::uint32_t>(grids[3],0xc,2);WriteAt<std::int32_t>(grids[3],0x10,19);WriteAt<std::uint32_t>(grids[3],0x28,4);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+4*8,AddressOf(grids[3]));
WriteWord(grids[4],0,g_EngineBase+kGridEntity_TNTVtableOffset);WriteAt<std::uint32_t>(grids[4],8,12);WriteAt<std::uint32_t>(grids[4],0xc,2);WriteAt<std::int32_t>(grids[4],0x10,19);WriteAt<std::uint32_t>(grids[4],0x28,5);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+5*8,AddressOf(grids[4]));
WriteWord(grids[5],0,g_EngineBase+kGridEntity_SpikesVtableOffset);WriteAt<std::uint32_t>(grids[5],8,8);WriteAt<std::uint32_t>(grids[5],0xc,2);WriteAt<std::int32_t>(grids[5],0x10,19);WriteAt<std::uint32_t>(grids[5],0x28,6);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+6*8,AddressOf(grids[5]));
const unsigned char guardGrid[]={40,36,64,169,243,3,0,170,42,44,65,169,31,64,0,185};std::memcpy(g_ModuleBytes.data()+3663048,guardGrid,16);
const unsigned char guardDoor[]={232,127,96,178,9,0,128,18,31,164,1,185,8,212,0,249};std::memcpy(g_ModuleBytes.data()+3694572,guardDoor,16);
const unsigned char guardPoop[]={41,0,128,82,232,3,31,42,105,2,7,57,104,66,0,185};std::memcpy(g_ModuleBytes.data()+3712184,guardPoop,16);
const unsigned char guardPit[]={40,0,0,18,8,128,6,57,20,57,0,240,148,78,67,249};std::memcpy(g_ModuleBytes.data()+3708536,guardPit,16);
const unsigned char guardTnt[]={104,162,1,185,244,79,67,169,253,123,66,169,255,3,1,145};std::memcpy(g_ModuleBytes.data()+3758132,guardTnt,16);
const unsigned char guardSpikes[]={104,162,1,185,104,10,64,185,31,37,0,113,127,18,0,185};std::memcpy(g_ModuleBytes.data()+3751112,guardSpikes,16);
const unsigned char guardRoomConfig[]={104,7,64,249,31,1,0,241,64,3,136,154,114,129,7,148};std::memcpy(g_ModuleBytes.data()+4781548,guardRoomConfig,16);
const unsigned char guardDescriptor[]={97,66,1,145,130,0,128,82,35,0,128,82,8,0,64,249};std::memcpy(g_ModuleBytes.data()+3573892,guardDescriptor,16);
const unsigned char guardPill[]={224,3,19,170,226,3,31,42,167,162,10,148,96,1,0,55};std::memcpy(g_ModuleBytes.data()+3966412,guardPill,16);

 const unsigned char doorGuard[]={8,160,77,57,243,3,0,170,232,1,0,55,104,66,77,57};std::memcpy(g_ModuleBytes.data()+0x386154,doorGuard,16);
 const unsigned char poopGuard[]={8,160,70,57,243,3,0,170,104,0,0,54,96,222,64,249};std::memcpy(g_ModuleBytes.data()+0x3897bc,poopGuard,16);
 const unsigned char rockGuard[]={26,128,6,145,243,3,0,170,65,40,0,240,33,28,10,145};std::memcpy(g_ModuleBytes.data()+0x392e68,rockGuard,16);
 std::memcpy(g_ModuleBytes.data()+api500_config::kStringAssignOffset,api500_config::kStringAssignGuard.data(),16);
 SetApi500ConfigStringAssignmentForTesting(AssignString);
 for(auto&g:grids)for(unsigned i=0x1a0;i<g.size();++i)g[i]=static_cast<unsigned char>(0x51+i%71);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridEntityIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_pushcfunction(L,GridEntityDoorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_pop(L,1);
 for(unsigned i=0;i<6;++i){if(i==1){auto*h=static_cast<LuaRuntime::DoorHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::DoorHandle)));*h={grids[i].data(),0,0};luaL_getmetatable(L,LuaRuntime::kGridEntityDoorMetatable);}else{auto*h=static_cast<LuaRuntime::GridEntityHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GridEntityHandle)));h->entity=grids[i].data();luaL_getmetatable(L,LuaRuntime::kGridEntityMetatable);}lua_setmetatable(L,-2);const char*names[]={"rock","door","poop","pit","tnt","spikes"};lua_setglobal(L,names[i]);}
// GridEntityDoor:ExtraVisible; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::uint8_t>(grids[1],776,0x7d);Unchanged(L,"assert(door.ExtraVisible==true,'GridEntityDoor:ExtraVisible read')");
Change<std::uint8_t>(L,1,776,0,"door.ExtraVisible=false;assert(door.ExtraVisible==false)");
Change<std::uint8_t>(L,1,776,1,"door.ExtraVisible=0;assert(door.ExtraVisible==true)");
Change<std::uint8_t>(L,1,776,0,"door.ExtraVisible=nil;assert(door.ExtraVisible==false)");
// GridEntityDoor:Busted; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::uint8_t>(grids[1],777,0x7d);Unchanged(L,"assert(door.Busted==true,'GridEntityDoor:Busted read')");
Change<std::uint8_t>(L,1,777,0,"door.Busted=false;assert(door.Busted==false)");
Change<std::uint8_t>(L,1,777,1,"door.Busted=0;assert(door.Busted==true)");
Change<std::uint8_t>(L,1,777,0,"door.Busted=nil;assert(door.Busted==false)");
// GridEntityPoop:ReviveTimer; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::int32_t>(grids[2],416,-17003);Unchanged(L,"assert(poop.ReviveTimer==-17003,'GridEntityPoop:ReviveTimer read')");
Change<std::int32_t>(L,2,416,-29,"poop.ReviveTimer=-29;assert(poop.ReviveTimer==-29)");
Change<std::int32_t>(L,2,416,1,"poop.ReviveTimer=0x100000001;assert(poop.ReviveTimer==1)");
Unchanged(L,"assert(not pcall(function()poop.ReviveTimer=1.5 end));assert(not pcall(function()poop.ReviveTimer={}end));assert(not pcall(function()poop.ReviveTimer=false end))");
// GridEntityPoop:UnderPlayer; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::uint8_t>(grids[2],448,0x7d);Unchanged(L,"assert(poop.UnderPlayer==true,'GridEntityPoop:UnderPlayer read')");
Change<std::uint8_t>(L,2,448,0,"poop.UnderPlayer=false;assert(poop.UnderPlayer==false)");
Change<std::uint8_t>(L,2,448,1,"poop.UnderPlayer=0;assert(poop.UnderPlayer==true)");
Change<std::uint8_t>(L,2,448,0,"poop.UnderPlayer=nil;assert(poop.UnderPlayer==false)");
// GridEntityPit:HasLadder; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::uint8_t>(grids[3],416,0x7d);Unchanged(L,"assert(pit.HasLadder==true,'GridEntityPit:HasLadder read')");
Change<std::uint8_t>(L,3,416,0,"pit.HasLadder=false;assert(pit.HasLadder==false)");
Change<std::uint8_t>(L,3,416,1,"pit.HasLadder=0;assert(pit.HasLadder==true)");
Change<std::uint8_t>(L,3,416,0,"pit.HasLadder=nil;assert(pit.HasLadder==false)");
// GridEntityTNT:FrameCnt; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::int32_t>(grids[4],416,-17003);Unchanged(L,"assert(tnt.FrameCnt==-17003,'GridEntityTNT:FrameCnt read')");
Change<std::int32_t>(L,4,416,-29,"tnt.FrameCnt=-29;assert(tnt.FrameCnt==-29)");
Change<std::int32_t>(L,4,416,1,"tnt.FrameCnt=0x100000001;assert(tnt.FrameCnt==1)");
Unchanged(L,"assert(not pcall(function()tnt.FrameCnt=1.5 end));assert(not pcall(function()tnt.FrameCnt={}end));assert(not pcall(function()tnt.FrameCnt=false end))");
// GridEntitySpikes:Timeout; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::int32_t>(grids[5],416,-17003);Unchanged(L,"assert(spikes.Timeout==-17003,'GridEntitySpikes:Timeout read')");
Change<std::int32_t>(L,5,416,-29,"spikes.Timeout=-29;assert(spikes.Timeout==-29)");
Change<std::int32_t>(L,5,416,1,"spikes.Timeout=0x100000001;assert(spikes.Timeout==1)");
Unchanged(L,"assert(not pcall(function()spikes.Timeout=1.5 end));assert(not pcall(function()spikes.Timeout={}end));assert(not pcall(function()spikes.Timeout=false end))");
// GridEntityRock:FrameCnt; 独立证据见 SOURCE_LEDGER，固定原生偏移，不读取生产字段表。
WriteAt<std::int32_t>(grids[0],488,-17003);Unchanged(L,"assert(rock.FrameCnt==-17003,'GridEntityRock:FrameCnt read')");
Change<std::int32_t>(L,0,488,-29,"rock.FrameCnt=-29;assert(rock.FrameCnt==-29)");
Change<std::int32_t>(L,0,488,1,"rock.FrameCnt=0x100000001;assert(rock.FrameCnt==1)");
Unchanged(L,"assert(not pcall(function()rock.FrameCnt=1.5 end));assert(not pcall(function()rock.FrameCnt={}end));assert(not pcall(function()rock.FrameCnt=false end))");
// GridEntityDoor:OpenAnimation: libc++ 24B string, short/long/NUL/empty均保全二进制长度。
std::memset(grids[1].data()+800,0,24);grids[1][800]=8;std::memcpy(grids[1].data()+801,"Seed",4);
Unchanged(L,"assert(door.OpenAnimation=='Seed','GridEntityDoor:OpenAnimation read')");
StringChange(L,1,800,"door.OpenAnimation='A string longer than the native short string capacity';assert(door.OpenAnimation=='A string longer than the native short string capacity')");
StringChange(L,1,800,"door.OpenAnimation='A'..string.char(0)..'B';assert(#door.OpenAnimation==3 and string.byte(door.OpenAnimation,2)==0)");
StringChange(L,1,800,"door.OpenAnimation='';assert(door.OpenAnimation=='')");
Unchanged(L,"assert(not pcall(function()door.OpenAnimation={}end))");
// GridEntityDoor:CloseAnimation: libc++ 24B string, short/long/NUL/empty均保全二进制长度。
std::memset(grids[1].data()+824,0,24);grids[1][824]=8;std::memcpy(grids[1].data()+825,"Seed",4);
Unchanged(L,"assert(door.CloseAnimation=='Seed','GridEntityDoor:CloseAnimation read')");
StringChange(L,1,824,"door.CloseAnimation='A string longer than the native short string capacity';assert(door.CloseAnimation=='A string longer than the native short string capacity')");
StringChange(L,1,824,"door.CloseAnimation='A'..string.char(0)..'B';assert(#door.CloseAnimation==3 and string.byte(door.CloseAnimation,2)==0)");
StringChange(L,1,824,"door.CloseAnimation='';assert(door.CloseAnimation=='')");
Unchanged(L,"assert(not pcall(function()door.CloseAnimation={}end))");
// GridEntityDoor:LockedAnimation: libc++ 24B string, short/long/NUL/empty均保全二进制长度。
std::memset(grids[1].data()+848,0,24);grids[1][848]=8;std::memcpy(grids[1].data()+849,"Seed",4);
Unchanged(L,"assert(door.LockedAnimation=='Seed','GridEntityDoor:LockedAnimation read')");
StringChange(L,1,848,"door.LockedAnimation='A string longer than the native short string capacity';assert(door.LockedAnimation=='A string longer than the native short string capacity')");
StringChange(L,1,848,"door.LockedAnimation='A'..string.char(0)..'B';assert(#door.LockedAnimation==3 and string.byte(door.LockedAnimation,2)==0)");
StringChange(L,1,848,"door.LockedAnimation='';assert(door.LockedAnimation=='')");
Unchanged(L,"assert(not pcall(function()door.LockedAnimation={}end))");
// GridEntityDoor:OpenLockedAnimation: libc++ 24B string, short/long/NUL/empty均保全二进制长度。
std::memset(grids[1].data()+872,0,24);grids[1][872]=8;std::memcpy(grids[1].data()+873,"Seed",4);
Unchanged(L,"assert(door.OpenLockedAnimation=='Seed','GridEntityDoor:OpenLockedAnimation read')");
StringChange(L,1,872,"door.OpenLockedAnimation='A string longer than the native short string capacity';assert(door.OpenLockedAnimation=='A string longer than the native short string capacity')");
StringChange(L,1,872,"door.OpenLockedAnimation='A'..string.char(0)..'B';assert(#door.OpenLockedAnimation==3 and string.byte(door.OpenLockedAnimation,2)==0)");
StringChange(L,1,872,"door.OpenLockedAnimation='';assert(door.OpenLockedAnimation=='')");
Unchanged(L,"assert(not pcall(function()door.OpenLockedAnimation={}end))");
// GridEntityPoop:StateAnimation: libc++ 24B string, short/long/NUL/empty均保全二进制长度。
std::memset(grids[2].data()+424,0,24);grids[2][424]=8;std::memcpy(grids[2].data()+425,"Seed",4);
Unchanged(L,"assert(poop.StateAnimation=='Seed','GridEntityPoop:StateAnimation read')");
StringChange(L,2,424,"poop.StateAnimation='A string longer than the native short string capacity';assert(poop.StateAnimation=='A string longer than the native short string capacity')");
StringChange(L,2,424,"poop.StateAnimation='A'..string.char(0)..'B';assert(#poop.StateAnimation==3 and string.byte(poop.StateAnimation,2)==0)");
StringChange(L,2,424,"poop.StateAnimation='';assert(poop.StateAnimation=='')");
Unchanged(L,"assert(not pcall(function()poop.StateAnimation={}end))");
// GridEntityRock:RubbleAnim: libc++ 24B string, short/long/NUL/empty均保全二进制长度。
std::memset(grids[0].data()+440,0,24);grids[0][440]=8;std::memcpy(grids[0].data()+441,"Seed",4);
Unchanged(L,"assert(rock.RubbleAnim=='Seed','GridEntityRock:RubbleAnim read')");
StringChange(L,0,440,"rock.RubbleAnim='A string longer than the native short string capacity';assert(rock.RubbleAnim=='A string longer than the native short string capacity')");
StringChange(L,0,440,"rock.RubbleAnim='A'..string.char(0)..'B';assert(#rock.RubbleAnim==3 and string.byte(rock.RubbleAnim,2)==0)");
StringChange(L,0,440,"rock.RubbleAnim='';assert(rock.RubbleAnim=='')");
Unchanged(L,"assert(not pcall(function()rock.RubbleAnim={}end))");

 RegisterApi600PlayerTypes(L);RegisterVectorReferenceMetatable(L);
 luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 // 独立原件：PC posvel registrar/wrapper + NS GetMultiShotPositionVelocity，HFA4float。
 // 生产返回对象有且仅有16B，自有值无parent generation依赖；只构造原生存储，访问器使用生产注册。
 auto*pv=static_cast<unsigned char*>(lua_newuserdata(L,16));const float initial[]={3.25F,-7.5F,11.25F,-13.5F};std::memcpy(pv,initial,16);luaL_getmetatable(L,"IsaacRuntime.PlayerTypesPosVel");lua_setmetatable(L,-2);lua_setglobal(L,"pv");
 unsigned char original[16];std::memcpy(original,pv,16);
 Run(L,"assert(pv.Position.X==3.25 and pv.Position.Y==-7.5);assert(pv.Velocity.X==11.25 and pv.Velocity.Y==-13.5);savedPosition=pv.Position;savedVelocity=pv.Velocity;savedPosition.X=99;savedVelocity.Y=88;assert(pv.Position.X==3.25 and pv.Velocity.Y==-13.5)");assert(!std::memcmp(pv,original,16));
 Run(L,"pv.Position=Vector(-23.25,31.5);assert(pv.Position.X==-23.25 and pv.Position.Y==31.5)");const float position[]={-23.25F,31.5F};std::memcpy(original,position,8);assert(!std::memcmp(pv,original,16));
 Run(L,"pv.Velocity=Vector(41.25,-43.5);assert(pv.Velocity.X==41.25 and pv.Velocity.Y==-43.5)");const float velocity[]={41.25F,-43.5F};std::memcpy(original+8,velocity,8);assert(!std::memcmp(pv,original,16));
 Run(L,"assert(not pcall(function()pv.Position={}end));assert(not pcall(function()pv.Velocity=false end));assert(not pcall(function()pv.Unknown=1 end))");assert(!std::memcmp(pv,original,16));
 RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));LuaRuntime::SetEngineModuleBase(g_EngineBase+0x1000);
 Run(L,"collectgarbage('collect');assert(pv.Position.X==-23.25 and pv.Velocity.Y==-43.5);assert(savedPosition.X==99 and savedVelocity.Y==88)");assert(!std::memcmp(pv,original,16));LuaRuntime::SetEngineModuleBase(g_EngineBase);
// 模块/原生vptr失效后不得返回旧字段；槽位移除不等于原生析构。
// 写入经Api500GridNewIndex/Grid校验抛错。读只允许错误或nil，禁止旧数值。
auto savedSlots=g_RoomBytes;
WriteWord(grids[0],0,0); // 原生vptr失效；槽位移除不等于析构。
Unchanged(L,"local ok,value=pcall(function()return rock.FrameCnt end);assert(not ok or value==nil,'rock.FrameCnt stale read');assert(not pcall(function()rock.FrameCnt=false end),'rock.FrameCnt stale write')");
Unchanged(L,"local ok,value=pcall(function()return rock.RubbleAnim end);assert(not ok or value==nil,'rock.RubbleAnim stale read');assert(not pcall(function()rock.RubbleAnim=false end),'rock.RubbleAnim stale write')");
WriteWord(grids[1],0,0); // 原生vptr失效；槽位移除不等于析构。
Unchanged(L,"local ok,value=pcall(function()return door.ExtraVisible end);assert(not ok or value==nil,'door.ExtraVisible stale read');assert(not pcall(function()door.ExtraVisible=false end),'door.ExtraVisible stale write')");
Unchanged(L,"local ok,value=pcall(function()return door.Busted end);assert(not ok or value==nil,'door.Busted stale read');assert(not pcall(function()door.Busted=false end),'door.Busted stale write')");
Unchanged(L,"local ok,value=pcall(function()return door.OpenAnimation end);assert(not ok or value==nil,'door.OpenAnimation stale read');assert(not pcall(function()door.OpenAnimation=false end),'door.OpenAnimation stale write')");
Unchanged(L,"local ok,value=pcall(function()return door.CloseAnimation end);assert(not ok or value==nil,'door.CloseAnimation stale read');assert(not pcall(function()door.CloseAnimation=false end),'door.CloseAnimation stale write')");
Unchanged(L,"local ok,value=pcall(function()return door.LockedAnimation end);assert(not ok or value==nil,'door.LockedAnimation stale read');assert(not pcall(function()door.LockedAnimation=false end),'door.LockedAnimation stale write')");
Unchanged(L,"local ok,value=pcall(function()return door.OpenLockedAnimation end);assert(not ok or value==nil,'door.OpenLockedAnimation stale read');assert(not pcall(function()door.OpenLockedAnimation=false end),'door.OpenLockedAnimation stale write')");
WriteWord(grids[2],0,0); // 原生vptr失效；槽位移除不等于析构。
Unchanged(L,"local ok,value=pcall(function()return poop.ReviveTimer end);assert(not ok or value==nil,'poop.ReviveTimer stale read');assert(not pcall(function()poop.ReviveTimer=false end),'poop.ReviveTimer stale write')");
Unchanged(L,"local ok,value=pcall(function()return poop.UnderPlayer end);assert(not ok or value==nil,'poop.UnderPlayer stale read');assert(not pcall(function()poop.UnderPlayer=false end),'poop.UnderPlayer stale write')");
Unchanged(L,"local ok,value=pcall(function()return poop.StateAnimation end);assert(not ok or value==nil,'poop.StateAnimation stale read');assert(not pcall(function()poop.StateAnimation=false end),'poop.StateAnimation stale write')");
WriteWord(grids[3],0,0); // 原生vptr失效；槽位移除不等于析构。
Unchanged(L,"local ok,value=pcall(function()return pit.HasLadder end);assert(not ok or value==nil,'pit.HasLadder stale read');assert(not pcall(function()pit.HasLadder=false end),'pit.HasLadder stale write')");
WriteWord(grids[4],0,0); // 原生vptr失效；槽位移除不等于析构。
Unchanged(L,"local ok,value=pcall(function()return tnt.FrameCnt end);assert(not ok or value==nil,'tnt.FrameCnt stale read');assert(not pcall(function()tnt.FrameCnt=false end),'tnt.FrameCnt stale write')");
WriteWord(grids[5],0,0); // 原生vptr失效；槽位移除不等于析构。
Unchanged(L,"local ok,value=pcall(function()return spikes.Timeout end);assert(not ok or value==nil,'spikes.Timeout stale read');assert(not pcall(function()spikes.Timeout=false end),'spikes.Timeout stale write')");
g_RoomBytes=savedSlots;lua_close(L);return 0;}
'''

class RemainingFields(unittest.TestCase):
    def test_grid_native_memory_neighbors_types_and_invalid_vptr(self):
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', 'void* Api500WorldRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t,void** p){*p=Api500WorldRoom();return GameRoomObservation::Success;}')
        with tempfile.TemporaryDirectory(prefix='remaining-fields-') as d:
            binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+MAIN)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
