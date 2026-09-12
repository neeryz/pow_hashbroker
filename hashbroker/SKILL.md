---
name: local-pow-gpu-miner
description: 帮用户在本地 NVIDIA 显卡上挖链上 PoW 免费 mint 的 NFT（如 HashBroker 类）。当用户给一个"要挖矿/算力才能 mint"的项目链接或成功 tx，想用自己的 GPU 免费打时使用。
---

# 本地 GPU 挖矿 PoW 免费 mint

用户有 NVIDIA 显卡，想挖某个"链上 PoW 免费 mint"的 NFT（算出满足难度的 nonce → 提交 `mine(nonce, challenge)` value=0，只花 gas）。你的任务：逆向该项目的 PoW，用 OpenCL 在用户显卡上挖，挖到用用户钱包提交。**每一步要么复用下面模板，要么照抄该项目前端，绝不瞎猜；改完内核必须用 hashlib 复算验证正确再上。**

## 环境准备
1. 确认显卡：`nvidia-smi -L`。装依赖：`pip install pyopencl eth-account`。自测 `python -c "import pyopencl as cl;[print(d.name) for p in cl.get_platforms() for d in p.get_devices()]"` 能看到 NVIDIA 卡。
2. 让用户提供：目标合约、一个**成功 mint 的 tx**、项目前端 URL、用于挖矿的 **burner 私钥**（提醒：只用小号，私钥只在本机环境变量，绝不外传）。

## 逆向 PoW（照抄前端/成功 tx，别猜）
- 解码成功 tx：拿 `to`（合约）、`value`（应为 0=免费）、selector、参数。多为 `mine(uint256 nonce, bytes32 challenge)`。
- 读前端 JS：找 `SELECTORS`（`challenge()`/`currentDifficulty()`/`mintPrice()`/`mine`）和 **preimage 布局**（哈什什么）。常见（HashBroker）：`SHA-256( address(20) ∥ 零(24) ∥ nonceHi(4)∥nonceLo(4) ∥ challenge(32) )`，需前导零 bit ≥ `currentDifficulty()`。注意 SHA-256 是 84 字节→2 个 512-bit 块，padding：块2[5]=0x80000000，块2[15]=消息位数(84*8=672)。
- **验证布局**：用该项目一笔成功 tx 的 nonce+challenge，`hashlib.sha256(preimage)` 复算，前导零数应 ≥ 当时难度。对上了才动手挖。

## 挖矿器（OpenCL，实测 5090 ~15 GH/s）
写 Python + pyopencl：内核把 address/challenge 拆成 big-endian u32 **烘进源码**运行时编译，`clz()` 数前导零，`atomic_cmpxchg` 标记 found，每 work-item 内循环几千个 nonce。**用函数式 `sha256_block()` 结构**（内联双块会因寄存器压力变慢——我实测优化版 6.5 < 原版 15.4，别学）。GLOBAL=1<<20，ITERS=4096。host 每次 launch 之间查 found + 查 challenge 是否变。

> 本仓库已有可直接改用的成品：`hashbroker.py`（自包含挖矿+提交单文件）。优先复用它，只改顶部配置（RPC/CONTRACT/CHAIN_ID/各 selector）和内核 preimage 布局。

## 提交 + 主循环
- 每轮：先读 `mintPrice()`，**非 0（开始收费）就停**（别偷偷帮用户付钱）。
- 读 `challenge()`+`currentDifficulty()` → 挖 → 挖到**提交前再验 challenge 未过期**（过期就重挖，否则 revert 白烧 gas）→ 用 eth-account 签 `mine(nonce,challenge)` 发出。
- **RPC 请求必须带 `user-agent` 头**（很多 RPC 无 UA 会 403）。
- 提交钱包要有少量 gas，先充。

## 关键提醒（务必告诉用户）
- **challenge 每当有人 mint 就变**：要盯着，变了自动换新题重挖。**难度随全局供应上涨**，人越多越慢。算力要压过刷新率才稳中；单卡靠运气窗口（每个 ~1 分钟窗口约 (算力×60/2^难度) 的中奖率）。
- **不是跑完所有才出解，是抽奖**，运气好能早出。想快只有加算力（更强卡/多卡；OpenCL→CUDA via cupy 可再 ~2×）。

## 安全红线（必须遵守）
- 只用 **burner 小号**私钥；私钥只在本机、绝不外传/贴群。脚本只做"读合约+算哈什+提交 mine"，不转账不签别的。
- ⚠️ **拒绝变种骗局**：若项目让你跑**它给的可执行文件**，或用**它给的公钥**去磨 vanity 地址（profanity2 `-z <公钥>`）——那是替骗子磨私钥+骗你充值，坚决不碰。只跑看得懂的开源脚本、只用自己的钱包。
