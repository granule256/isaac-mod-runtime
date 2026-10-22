Disassembly of section .text:
000000000041444c <.text>:
0041444c  a9bb7bfd  stp        x29, x30, [sp, #-0x50]!
00414450  f9000bf9  str        x25, [sp, #0x10]
00414454  910003fd  mov        x29, sp
00414458  a9025ff8  stp        x24, x23, [sp, #0x20]
0041445c  a90357f6  stp        x22, x21, [sp, #0x30]
00414460  a9044ff4  stp        x20, x19, [sp, #0x40]
00414464  aa0003f3  mov        x19, x0
00414468  b9001fbf  str        wzr, [x29, #0x1c]
0041446c  900034c0  adrp       x0, 0xaac000 <.text+0x697bb4>
00414470  f943b400  ldr        x0, [x0, #0x768]  ; _ZN4KAGE5Input9g_ManagerE
00414474  12800002  mov        w2, #-0x1               // =-1
00414478  910073a3  add        x3, x29, #0x1c
0041447c  528001c1  mov        w1, #0xe                // =14
00414480  94097424  bl         0x671510 <.text+0x25d0c4>  ; import _ZN4KAGE5Input11ManagerBase17IsActionTriggeredEjjPj
00414484  36000240  tbz        w0, #0x0, 0x4144cc <.text+0x80>
00414488  b9400268  ldr        w8, [x19]
0041448c  71000d1f  cmp        w8, #0x3
00414490  54002f00  b.eq       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
00414494  7100091f  cmp        w8, #0x2
00414498  54000be0  b.eq       0x414614 <.text+0x1c8>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x1c8
0041449c  7100051f  cmp        w8, #0x1
004144a0  54000f21  b.ne       0x414684 <.text+0x238>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x238
004144a4  52800048  mov        w8, #0x2                // =2
004144a8  911b8260  add        x0, x19, #0x6e0
004144ac  b9000268  str        w8, [x19]
004144b0  d0002421  adrp       x1, 0x89a000 <.text+0x485bb4>
004144b4  91330021  add        x1, x1, #0xcc0  ; "DeleteConfirmationAppear"
004144b8  2a1f03e2  mov        w2, wzr
004144bc  94096de9  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
004144c0  52800028  mov        w8, #0x1                // =1
004144c4  b9000a68  str        w8, [x19, #0x8]
004144c8  1400016a  b          0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
004144cc  900034c0  adrp       x0, 0xaac000 <.text+0x697bb4>
004144d0  f943b400  ldr        x0, [x0, #0x768]  ; _ZN4KAGE5Input9g_ManagerE
004144d4  52800221  mov        w1, #0x11               // =17
004144d8  12800002  mov        w2, #-0x1               // =-1
004144dc  aa1f03e3  mov        x3, xzr
004144e0  9409912c  bl         0x678990 <.text+0x264544>  ; import _ZN4KAGE5Input11ManagerBase15IsActionPressedEjjPj
004144e4  36000600  tbz        w0, #0x0, 0x4145a4 <.text+0x158>
004144e8  b9400e68  ldr        w8, [x19, #0xc]
004144ec  34000148  cbz        w8, 0x414514 <.text+0xc8>
004144f0  7100c91f  cmp        w8, #0x32
004144f4  54002be3  b.lo       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
004144f8  529999a9  mov        w9, #0xcccd             // =52429
004144fc  72b99989  movk       w9, #0xcccc, lsl #16
00414500  9ba97d09  umull      x9, w8, w9
00414504  d363fd29  lsr        x9, x9, #35
00414508  5280014a  mov        w10, #0xa               // =10
0041450c  1b0aa128  msub       w8, w9, w10, w8
00414510  35002b08  cbnz       w8, 0x414a70 <.text+0x624>
00414514  b9400268  ldr        w8, [x19]
00414518  71000d1f  cmp        w8, #0x3
0041451c  54002aa0  b.eq       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
00414520  7100091f  cmp        w8, #0x2
00414524  540006e0  b.eq       0x414600 <.text+0x1b4>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x1b4
00414528  b9800668  ldrsw      x8, [x19, #0x4]
0041452c  7100091f  cmp        w8, #0x2
00414530  54002a0c  b.gt       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
00414534  7100091f  cmp        w8, #0x2
00414538  540000e8  b.hi       0x414554 <.text+0x108>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x108
0041453c  90003129  adrp       x9, 0xa38000 <.text+0x623bb4>
00414540  9137e129  add        x9, x9, #0xdf8
00414544  91006260  add        x0, x19, #0x18
00414548  f8687921  ldr        x1, [x9, x8, lsl #3]
0041454c  2a1f03e2  mov        w2, wzr
00414550  94096dc4  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414554  d0002454  adrp       x20, 0x89e000 <.text+0x489bb4>
00414558  913c3694  add        x20, x20, #0xf0d  ; "Idle"
0041455c  9105c260  add        x0, x19, #0x170
00414560  aa1403e1  mov        x1, x20
00414564  2a1f03e2  mov        w2, wzr
00414568  94096dbe  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
0041456c  910b2260  add        x0, x19, #0x2c8
00414570  aa1403e1  mov        x1, x20
00414574  2a1f03e2  mov        w2, wzr
00414578  94096dba  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
0041457c  91108260  add        x0, x19, #0x420
00414580  aa1403e1  mov        x1, x20
00414584  2a1f03e2  mov        w2, wzr
00414588  94096db6  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
0041458c  b9400668  ldr        w8, [x19, #0x4]
00414590  71000508  subs       w8, w8, #0x1
00414594  52800049  mov        w9, #0x2                // =2
00414598  1a88b128  csel       w8, w9, w8, lt
0041459c  b9000668  str        w8, [x19, #0x4]
004145a0  14000134  b          0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
004145a4  900034c0  adrp       x0, 0xaac000 <.text+0x697bb4>
004145a8  f943b400  ldr        x0, [x0, #0x768]  ; _ZN4KAGE5Input9g_ManagerE
004145ac  52800241  mov        w1, #0x12               // =18
004145b0  12800002  mov        w2, #-0x1               // =-1
004145b4  aa1f03e3  mov        x3, xzr
004145b8  940990f6  bl         0x678990 <.text+0x264544>  ; import _ZN4KAGE5Input11ManagerBase15IsActionPressedEjjPj
004145bc  360007e0  tbz        w0, #0x0, 0x4146b8 <.text+0x26c>
004145c0  b9400e68  ldr        w8, [x19, #0xc]
004145c4  34000148  cbz        w8, 0x4145ec <.text+0x1a0>
004145c8  7100c91f  cmp        w8, #0x32
004145cc  54002523  b.lo       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
004145d0  529999a9  mov        w9, #0xcccd             // =52429
004145d4  72b99989  movk       w9, #0xcccc, lsl #16
004145d8  9ba97d09  umull      x9, w8, w9
004145dc  d363fd29  lsr        x9, x9, #35
004145e0  5280014a  mov        w10, #0xa               // =10
004145e4  1b0aa128  msub       w8, w9, w10, w8
004145e8  35002448  cbnz       w8, 0x414a70 <.text+0x624>
004145ec  b9400268  ldr        w8, [x19]
004145f0  71000d1f  cmp        w8, #0x3
004145f4  540023e0  b.eq       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
004145f8  7100091f  cmp        w8, #0x2
004145fc  54001041  b.ne       0x414804 <.text+0x3b8>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x3b8
00414600  b9400a68  ldr        w8, [x19, #0x8]
00414604  7100011f  cmp        w8, #0x0
00414608  1a9f17e8  cset       w8, eq
0041460c  b9000a68  str        w8, [x19, #0x8]
00414610  14000118  b          0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
00414614  911b8274  add        x20, x19, #0x6e0
00414618  900024c1  adrp       x1, 0x8ac000 <.text+0x497bb4>
0041461c  911af021  add        x1, x1, #0x6bc  ; "DeleteConfirmationIdle"
00414620  aa1403e0  mov        x0, x20
00414624  9409784f  bl         0x672760 <.text+0x25e314>  ; import _ZNK15IsaacRepentance4ANM29IsPlayingEPKc
00414628  36002240  tbz        w0, #0x0, 0x414a70 <.text+0x624>
0041462c  b9400a68  ldr        w8, [x19, #0x8]
00414630  35002168  cbnz       w8, 0x414a5c <.text+0x610>
00414634  900034d9  adrp       x25, 0xaac000 <.text+0x697bb4>
00414638  f9432739  ldr        x25, [x25, #0x648]  ; _ZN15IsaacRepentance9g_ManagerE
0041463c  b9400668  ldr        w8, [x19, #0x4]
00414640  11000501  add        w1, w8, #0x1
00414644  f9400320  ldr        x0, [x25]
00414648  9409a54a  bl         0x67db70 <.text+0x269724>  ; import _ZN15IsaacRepentance7Manager14DeleteSaveSlotENS0_9eSaveSlotE
0041464c  f9400320  ldr        x0, [x25]
00414650  52800021  mov        w1, #0x1                // =1
00414654  b9401015  ldr        w21, [x0, #0x10]
00414658  9409a1b2  bl         0x67cd20 <.text+0x2688d4>  ; import _ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE
0041465c  9105c276  add        x22, x19, #0x170
00414660  aa1603e1  mov        x1, x22
00414664  9409a52f  bl         0x67db20 <.text+0x2696d4>  ; import _ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E
00414668  f9400328  ldr        x8, [x25]
0041466c  91006100  add        x0, x8, #0x18
00414670  52804fa1  mov        w1, #0x27d              // =637
00414674  940971ff  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
00414678  360011e0  tbz        w0, #0x0, 0x4148b4 <.text+0x468>
0041467c  52800048  mov        w8, #0x2                // =2
00414680  140000a2  b          0x414908 <.text+0x4bc>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x4bc
00414684  b9400668  ldr        w8, [x19, #0x4]
00414688  71000d1f  cmp        w8, #0x3
0041468c  54001f28  b.hi       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
00414690  f0002549  adrp       x9, 0x8bf000 <.text+0x4aabb4>
00414694  912ecd29  add        x9, x9, #0xbb3
00414698  1000008a  adr        x10, 0x4146a8 <.text+0x25c>
0041469c  3868692b  ldrb       w11, [x9, x8]
004146a0  8b0b094a  add        x10, x10, x11, lsl #2
004146a4  d61f0140  br         x10
004146a8  aa1303e0  mov        x0, x19
004146ac  52800021  mov        w1, #0x1                // =1
004146b0  9409a534  bl         0x67db80 <.text+0x269734>  ; import _ZN15IsaacRepentance9Menu_Save16select_save_slotEi
004146b4  140000ef  b          0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
004146b8  900034c0  adrp       x0, 0xaac000 <.text+0x697bb4>
004146bc  f943b400  ldr        x0, [x0, #0x768]  ; _ZN4KAGE5Input9g_ManagerE
004146c0  52800281  mov        w1, #0x14               // =20
004146c4  12800002  mov        w2, #-0x1               // =-1
004146c8  aa1f03e3  mov        x3, xzr
004146cc  94097391  bl         0x671510 <.text+0x25d0c4>  ; import _ZN4KAGE5Input11ManagerBase17IsActionTriggeredEjjPj
004146d0  36000440  tbz        w0, #0x0, 0x414758 <.text+0x30c>
004146d4  b9800668  ldrsw      x8, [x19, #0x4]
004146d8  7100091f  cmp        w8, #0x2
004146dc  54001ca8  b.hi       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
004146e0  b9400269  ldr        w9, [x19]
004146e4  35001c69  cbnz       w9, 0x414a70 <.text+0x624>
004146e8  7100091f  cmp        w8, #0x2
004146ec  540000e8  b.hi       0x414708 <.text+0x2bc>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x2bc
004146f0  90003129  adrp       x9, 0xa38000 <.text+0x623bb4>
004146f4  9137e129  add        x9, x9, #0xdf8
004146f8  91006260  add        x0, x19, #0x18
004146fc  f8687921  ldr        x1, [x9, x8, lsl #3]
00414700  52800022  mov        w2, #0x1                // =1
00414704  94096d57  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414708  d0002454  adrp       x20, 0x89e000 <.text+0x489bb4>
0041470c  913c3694  add        x20, x20, #0xf0d  ; "Idle"
00414710  9105c260  add        x0, x19, #0x170
00414714  aa1403e1  mov        x1, x20
00414718  2a1f03e2  mov        w2, wzr
0041471c  94096d51  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414720  910b2260  add        x0, x19, #0x2c8
00414724  aa1403e1  mov        x1, x20
00414728  2a1f03e2  mov        w2, wzr
0041472c  94096d4d  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414730  91108260  add        x0, x19, #0x420
00414734  aa1403e1  mov        x1, x20
00414738  2a1f03e2  mov        w2, wzr
0041473c  94096d49  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414740  52800068  mov        w8, #0x3                // =3
00414744  b9000668  str        w8, [x19, #0x4]
00414748  91160260  add        x0, x19, #0x580
0041474c  f00024a1  adrp       x1, 0x8ab000 <.text+0x496bb4>
00414750  9112f421  add        x1, x1, #0x4bd  ; "DeleteSelect"
00414754  140000c5  b          0x414a68 <.text+0x61c>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x61c
00414758  900034c0  adrp       x0, 0xaac000 <.text+0x697bb4>
0041475c  f943b400  ldr        x0, [x0, #0x768]  ; _ZN4KAGE5Input9g_ManagerE
00414760  52800261  mov        w1, #0x13               // =19
00414764  12800002  mov        w2, #-0x1               // =-1
00414768  aa1f03e3  mov        x3, xzr
0041476c  94097369  bl         0x671510 <.text+0x25d0c4>  ; import _ZN4KAGE5Input11ManagerBase17IsActionTriggeredEjjPj
00414770  36000260  tbz        w0, #0x0, 0x4147bc <.text+0x370>
00414774  b9400668  ldr        w8, [x19, #0x4]
00414778  71000d1f  cmp        w8, #0x3
0041477c  540017a1  b.ne       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
00414780  91160260  add        x0, x19, #0x580
00414784  d0002421  adrp       x1, 0x89a000 <.text+0x485bb4>
00414788  91336421  add        x1, x1, #0xcd9  ; "DeleteDeselect"
0041478c  2a1f03e2  mov        w2, wzr
00414790  94096d34  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414794  91006260  add        x0, x19, #0x18
00414798  90002441  adrp       x1, 0x89c000 <.text+0x487bb4>
0041479c  9103f021  add        x1, x1, #0xfc  ; "File1Select"
004147a0  2a1f03e2  mov        w2, wzr
004147a4  b900067f  str        wzr, [x19, #0x4]
004147a8  94096d2e  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
004147ac  9105c260  add        x0, x19, #0x170
004147b0  d00024e1  adrp       x1, 0x8b2000 <.text+0x49dbb4>
004147b4  91308421  add        x1, x1, #0xc21  ; "Animated"
004147b8  140000ac  b          0x414a68 <.text+0x61c>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x61c
004147bc  900034c0  adrp       x0, 0xaac000 <.text+0x697bb4>
004147c0  f943b400  ldr        x0, [x0, #0x768]  ; _ZN4KAGE5Input9g_ManagerE
004147c4  12800002  mov        w2, #-0x1               // =-1
004147c8  528001e1  mov        w1, #0xf                // =15
004147cc  aa1f03e3  mov        x3, xzr
004147d0  94097350  bl         0x671510 <.text+0x25d0c4>  ; import _ZN4KAGE5Input11ManagerBase17IsActionTriggeredEjjPj
004147d4  360014e0  tbz        w0, #0x0, 0x414a70 <.text+0x624>
004147d8  b9400268  ldr        w8, [x19]
004147dc  7100051f  cmp        w8, #0x1
004147e0  54001d00  b.eq       0x414b80 <.text+0x734>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x734
004147e4  71000d1f  cmp        w8, #0x3
004147e8  54001d00  b.eq       0x414b88 <.text+0x73c>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x73c
004147ec  7100091f  cmp        w8, #0x2
004147f0  54001d21  b.ne       0x414b94 <.text+0x748>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x748
004147f4  911b8260  add        x0, x19, #0x6e0
004147f8  f00024a1  adrp       x1, 0x8ab000 <.text+0x496bb4>
004147fc  91128421  add        x1, x1, #0x4a1  ; "DeleteConfirmationDissapear"
00414800  1400009a  b          0x414a68 <.text+0x61c>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x61c
00414804  b9800668  ldrsw      x8, [x19, #0x4]
00414808  7100091f  cmp        w8, #0x2
0041480c  5400132c  b.gt       0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
00414810  7100091f  cmp        w8, #0x2
00414814  540000e8  b.hi       0x414830 <.text+0x3e4>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x3e4
00414818  90003129  adrp       x9, 0xa38000 <.text+0x623bb4>
0041481c  9137e129  add        x9, x9, #0xdf8
00414820  91006260  add        x0, x19, #0x18
00414824  f8687921  ldr        x1, [x9, x8, lsl #3]
00414828  2a1f03e2  mov        w2, wzr
0041482c  94096d0d  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414830  d0002454  adrp       x20, 0x89e000 <.text+0x489bb4>
00414834  913c3694  add        x20, x20, #0xf0d  ; "Idle"
00414838  9105c260  add        x0, x19, #0x170
0041483c  aa1403e1  mov        x1, x20
00414840  2a1f03e2  mov        w2, wzr
00414844  94096d07  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414848  910b2260  add        x0, x19, #0x2c8
0041484c  aa1403e1  mov        x1, x20
00414850  2a1f03e2  mov        w2, wzr
00414854  94096d03  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414858  91108260  add        x0, x19, #0x420
0041485c  aa1403e1  mov        x1, x20
00414860  2a1f03e2  mov        w2, wzr
00414864  94096cff  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414868  b9400668  ldr        w8, [x19, #0x4]
0041486c  7100051f  cmp        w8, #0x1
00414870  1a88c7e8  csinc      w8, wzr, w8, gt
00414874  b9000668  str        w8, [x19, #0x4]
00414878  1400007e  b          0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
0041487c  aa1303e0  mov        x0, x19
00414880  52800041  mov        w1, #0x2                // =2
00414884  9409a4bf  bl         0x67db80 <.text+0x269734>  ; import _ZN15IsaacRepentance9Menu_Save16select_save_slotEi
00414888  1400007a  b          0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
0041488c  aa1303e0  mov        x0, x19
00414890  52800061  mov        w1, #0x3                // =3
00414894  9409a4bb  bl         0x67db80 <.text+0x269734>  ; import _ZN15IsaacRepentance9Menu_Save16select_save_slotEi
00414898  14000076  b          0x414a70 <.text+0x624>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x624
0041489c  52800028  mov        w8, #0x1                // =1
004148a0  f9000268  str        x8, [x19]
004148a4  91160260  add        x0, x19, #0x580
004148a8  d0002421  adrp       x1, 0x89a000 <.text+0x485bb4>
004148ac  91336421  add        x1, x1, #0xcd9  ; "DeleteDeselect"
004148b0  1400006e  b          0x414a68 <.text+0x61c>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x61c
004148b4  f9400328  ldr        x8, [x25]
004148b8  91006100  add        x0, x8, #0x18
004148bc  52802a61  mov        w1, #0x153              // =339
004148c0  9409716c  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
004148c4  36000200  tbz        w0, #0x0, 0x414904 <.text+0x4b8>
004148c8  f9400328  ldr        x8, [x25]
004148cc  91006100  add        x0, x8, #0x18
004148d0  52804fa1  mov        w1, #0x27d              // =637
004148d4  94097167  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
004148d8  37000160  tbnz       w0, #0x0, 0x414904 <.text+0x4b8>
004148dc  f9400328  ldr        x8, [x25]
004148e0  b94a7109  ldr        w9, [x8, #0xa70]
004148e4  35000109  cbnz       w9, 0x414904 <.text+0x4b8>
004148e8  b94e9d09  ldr        w9, [x8, #0xe9c]
004148ec  7100013f  cmp        w9, #0x0
004148f0  540000ac  b.gt       0x414904 <.text+0x4b8>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x4b8
004148f4  91006100  add        x0, x8, #0x18
004148f8  52804f61  mov        w1, #0x27b              // =635
004148fc  9409715d  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
00414900  36001560  tbz        w0, #0x0, 0x414bac <.text+0x760>
00414904  2a1f03e8  mov        w8, wzr
00414908  3915e268  strb       w8, [x19, #0x578]
0041490c  f9400320  ldr        x0, [x25]
00414910  52800041  mov        w1, #0x2                // =2
00414914  52800058  mov        w24, #0x2               // =2
00414918  9409a102  bl         0x67cd20 <.text+0x2688d4>  ; import _ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE
0041491c  910b2277  add        x23, x19, #0x2c8
00414920  aa1703e1  mov        x1, x23
00414924  9409a47f  bl         0x67db20 <.text+0x2696d4>  ; import _ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E
00414928  f9400328  ldr        x8, [x25]
0041492c  91006100  add        x0, x8, #0x18
00414930  52804fa1  mov        w1, #0x27d              // =637
00414934  9409714f  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
00414938  370002c0  tbnz       w0, #0x0, 0x414990 <.text+0x544>
0041493c  f9400328  ldr        x8, [x25]
00414940  91006100  add        x0, x8, #0x18
00414944  52802a61  mov        w1, #0x153              // =339
00414948  9409714a  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
0041494c  36000200  tbz        w0, #0x0, 0x41498c <.text+0x540>
00414950  f9400328  ldr        x8, [x25]
00414954  91006100  add        x0, x8, #0x18
00414958  52804fa1  mov        w1, #0x27d              // =637
0041495c  94097145  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
00414960  37000160  tbnz       w0, #0x0, 0x41498c <.text+0x540>
00414964  f9400328  ldr        x8, [x25]
00414968  b94a7109  ldr        w9, [x8, #0xa70]
0041496c  35000109  cbnz       w9, 0x41498c <.text+0x540>
00414970  b94e9d09  ldr        w9, [x8, #0xe9c]
00414974  7100013f  cmp        w9, #0x0
00414978  540000ac  b.gt       0x41498c <.text+0x540>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x540
0041497c  91006100  add        x0, x8, #0x18
00414980  52804f61  mov        w1, #0x27b              // =635
00414984  9409713b  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
00414988  36001160  tbz        w0, #0x0, 0x414bb4 <.text+0x768>
0041498c  2a1f03f8  mov        w24, wzr
00414990  3915e678  strb       w24, [x19, #0x579]
00414994  f9400320  ldr        x0, [x25]
00414998  52800061  mov        w1, #0x3                // =3
0041499c  9409a0e1  bl         0x67cd20 <.text+0x2688d4>  ; import _ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE
004149a0  91108278  add        x24, x19, #0x420
004149a4  aa1803e1  mov        x1, x24
004149a8  9409a45e  bl         0x67db20 <.text+0x2696d4>  ; import _ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E
004149ac  f9400328  ldr        x8, [x25]
004149b0  91006100  add        x0, x8, #0x18
004149b4  52804fa1  mov        w1, #0x27d              // =637
004149b8  9409712e  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
004149bc  36000060  tbz        w0, #0x0, 0x4149c8 <.text+0x57c>
004149c0  52800048  mov        w8, #0x2                // =2
004149c4  14000016  b          0x414a1c <.text+0x5d0>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x5d0
004149c8  f9400328  ldr        x8, [x25]
004149cc  91006100  add        x0, x8, #0x18
004149d0  52802a61  mov        w1, #0x153              // =339
004149d4  94097127  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
004149d8  36000200  tbz        w0, #0x0, 0x414a18 <.text+0x5cc>
004149dc  f9400328  ldr        x8, [x25]
004149e0  91006100  add        x0, x8, #0x18
004149e4  52804fa1  mov        w1, #0x27d              // =637
004149e8  94097122  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
004149ec  37000160  tbnz       w0, #0x0, 0x414a18 <.text+0x5cc>
004149f0  f9400328  ldr        x8, [x25]
004149f4  b94a7109  ldr        w9, [x8, #0xa70]
004149f8  35000109  cbnz       w9, 0x414a18 <.text+0x5cc>
004149fc  b94e9d09  ldr        w9, [x8, #0xe9c]
00414a00  7100013f  cmp        w9, #0x0
00414a04  540000ac  b.gt       0x414a18 <.text+0x5cc>  ; -> ~_ZN15IsaacRepentance9Menu_Save6UpdateEv+0x5cc
00414a08  91006100  add        x0, x8, #0x18
00414a0c  52804f61  mov        w1, #0x27b              // =635
00414a10  94097118  bl         0x670e70 <.text+0x25ca24>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
00414a14  36000d40  tbz        w0, #0x0, 0x414bbc <.text+0x770>
00414a18  2a1f03e8  mov        w8, wzr
00414a1c  aa1303e0  mov        x0, x19
00414a20  3915ea68  strb       w8, [x19, #0x57a]
00414a24  9409a44b  bl         0x67db50 <.text+0x269704>  ; import _ZN15IsaacRepentance9Menu_Save29update_final_achievement_iconEv
00414a28  aa1603e0  mov        x0, x22
00414a2c  94096c9d  bl         0x66fca0 <.text+0x25b854>  ; import _ZN15IsaacRepentance4ANM212LoadGraphicsEv
00414a30  aa1703e0  mov        x0, x23
00414a34  94096c9b  bl         0x66fca0 <.text+0x25b854>  ; import _ZN15IsaacRepentance4ANM212LoadGraphicsEv
00414a38  aa1803e0  mov        x0, x24
00414a3c  94096c99  bl         0x66fca0 <.text+0x25b854>  ; import _ZN15IsaacRepentance4ANM212LoadGraphicsEv
00414a40  f9400320  ldr        x0, [x25]
00414a44  2a1503e1  mov        w1, w21
00414a48  9409a0b6  bl         0x67cd20 <.text+0x2688d4>  ; import _ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE
00414a4c  b00034c8  adrp       x8, 0xaad000 <.text+0x698bb4>
00414a50  f940d908  ldr        x8, [x8, #0x1b0]  ; _ZN15IsaacRepentance13g_MenuManagerE
00414a54  f9400100  ldr        x0, [x8]
00414a58  94099b7e  bl         0x67b850 <.text+0x267404>  ; import _ZN15IsaacRepentance11MenuManager18ResetCharacterMenuEv
00414a5c  f00024a1  adrp       x1, 0x8ab000 <.text+0x496bb4>
00414a60  91128421  add        x1, x1, #0x4a1  ; "DeleteConfirmationDissapear"
00414a64  aa1403e0  mov        x0, x20
00414a68  2a1f03e2  mov        w2, wzr
00414a6c  94096c7d  bl         0x66fc60 <.text+0x25b814>  ; import _ZN15IsaacRepentance4ANM24PlayEPKcb
00414a70  900034c0  adrp       x0, 0xaac000 <.text+0x697bb4>
00414a74  f943b400  ldr        x0, [x0, #0x768]  ; _ZN4KAGE5Input9g_ManagerE
00414a78  52800221  mov        w1, #0x11               // =17
00414a7c  12800002  mov        w2, #-0x1               // =-1
00414a80  aa1f03e3  mov        x3, xzr
00414a84  94098fc3  bl         0x678990 <.text+0x264544>  ; import _ZN4KAGE5Input11ManagerBase15IsActionPressedEjjPj
00414a88  37000100  tbnz       w0, #0x0, 0x414aa8 <.text+0x65c>
