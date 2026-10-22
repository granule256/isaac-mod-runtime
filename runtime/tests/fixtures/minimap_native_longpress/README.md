# 原生地图长短按机器码夹具

也就是说，这两段逐字节游戏代码用于在Apple ARM64上复现旧补丁把长按误判成短按的结果，不以C++重写状态机替代原件。

来源：主目录游戏原件 `/Users/kelinls/code/github/isaac mod/The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro`，SHA256 cc363208c220f65547edda6d8268b3b6c0f7373b14c91ae6ffb378018de4b66a。

- counter.bin：44B，模块偏移0x41ce60至0x41ce8c（不含末端），SHA256 fb7c37c82b7d3cc9d92618fa82e89d212c2e5f23f1c3a583f1c71fcbcb4c6897。
- state.bin：480B，模块偏移0x41cf00至0x41d0e0（不含末端），SHA256 cc0740332f6e6a72c5621b9c238da665a79c687bd9ca431e8a6a685d5765cd0c。

测试先校验SHA，再把当前生产第三处补丁值写入运行副本；源夹具本身不变。ShowName外部调用改为仅记录调用次数/参数的测试入口，片段末端及原跳向0x41d0f4的位置放返回指令，其余状态转移直接执行原件。调用方提供w20按住/命中信号，未执行前段触摸几何、GoodTrip Lua或真实传送；不能把持续按住跨区间用例称为真机传送通过。
