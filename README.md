# pow_hashbroker

本地 GPU 挖 **链上 PoW 免费 mint** 的 NFT（如 HashBroker 类）。算出满足难度的 nonce → 提交 `mine(nonce, challenge)`，value=0，**只花 gas**。

- `hashbroker/hashbroker.py` — 自包含挖矿器（pyopencl 算 SHA-256 + eth-account 提交），单文件，改顶部配置即可换项目。
- `hashbroker/SKILL.md` — 一个 Claude Code skill，让你自己的 Claude 帮你从零建一个本地挖矿器。

## 原理

```
preimage = 地址(20) || 零(24) || nonce(8) || challenge(32)   ->  SHA-256
需前导零 bit >= 链上 currentDifficulty()，满足就提交 mine(nonce, challenge)
```

challenge 每当有人 mint 就变，脚本会盯着自动换新题重挖；提交前再验一次没过期。难度随全局供应上涨，人越多越慢——**这是抽奖，不是跑完所有**，运气好早出，想快只有加算力。

## 用法

```bash
pip install pyopencl eth-account numpy

# 只用小号 burner 私钥！
export PK=0x你的burner私钥        # Windows PowerShell: $env:PK="0x..."
export COUNT=1                    # 可选，挖几个（默认一直挖到开始收费）
python hashbroker/hashbroker.py
```

实测 RTX 5090 ≈ 15.4 GH/s。期望解题时间 = `2^难度 / 算力`：难度 42 约 5 分钟，每升 1 级翻倍。

换别的 PoW 项目：改 `hashbroker.py` 顶部的 `RPC / CONTRACT / CHAIN_ID / 各 selector`，并按该项目前端核对 preimage 布局。

## ⚠️ 安全红线

- **只用 burner 小号私钥**，私钥只放本机环境变量，绝不硬编码、绝不贴群/上传。脚本只做"读合约 + 算哈什 + 提交 mine"，不转账、不签别的。
- **拒绝变种骗局**：若某项目让你跑*它给的可执行文件*，或用*它给的公钥*去磨 vanity 地址（如 `profanity2 -z <公钥>`）——那是替骗子磨私钥+骗你充值，坚决不碰。只跑看得懂的开源脚本、只用自己的钱包。
- 开始收费（`mintPrice != 0`）脚本会自动停，不会偷偷帮你付钱。

## License

[MIT](LICENSE) — 按原样提供，作者不对任何损失负责，风险自负。
