---
name: local-pow-gpu-miner
description: Helps the user mine on-chain PoW free-mint NFTs (HashBroker-style) with a local NVIDIA GPU. Use when the user brings a "requires mining/hashrate to mint" project link or successful tx and wants to hit it free with their own GPU.
---

# Local GPU mining for on-chain PoW free mints

The user has an NVIDIA GPU and wants to mine an "on-chain PoW free mint" NFT (find a nonce meeting the difficulty → submit `mine(nonce, challenge)` value=0, gas only). Your task: reverse-engineer the project's PoW, mine it with OpenCL on the user's GPU, and submit with the user's wallet when found. **Every step either reuses the template below or copies directly from the project's frontend — never guess. After changing the kernel, always re-verify with hashlib before deploying.**

## Environment setup
1. Confirm the GPU: `nvidia-smi -L`. Install deps: `pip install pyopencl eth-account`. Self-test with `python -c "import pyopencl as cl;[print(d.name) for p in cl.get_platforms() for d in p.get_devices()]"` — an NVIDIA card should be listed.
2. Ask the user for: target contract, one **successful mint tx**, the project's frontend URL, and a **burner private key** for mining (reminder: small wallet only; the key stays in a local environment variable, never shared).

## Reverse-engineering the PoW (copy the frontend / successful tx, don't guess)
- Decode the successful tx: get `to` (contract), `value` (should be 0 = free), selector, args. Usually `mine(uint256 nonce, bytes32 challenge)`.
- Read the frontend JS: find the `SELECTORS` (`challenge()` / `currentDifficulty()` / `mintPrice()` / `mine`) and the **preimage layout** (what gets hashed). Common pattern (HashBroker): `SHA-256( address(20) ∥ zeros(24) ∥ nonceHi(4) ∥ nonceLo(4) ∥ challenge(32) )`, needs leading zero bits ≥ `currentDifficulty()`. Note SHA-256 of 84 bytes → 2 × 512-bit blocks; padding: block2[5] = 0x80000000, block2[15] = message bit count (84*8=672).
- **Verify the layout**: recompute `hashlib.sha256(preimage)` using the nonce+challenge from the project's successful tx; the leading-zero count must be ≥ the difficulty at that time. Only start mining once it checks out.

## The miner (OpenCL, measured ~15 GH/s on a 5090)
Write Python + pyopencl: the kernel bakes address/challenge split into big-endian u32 **into the source**, compiled at runtime; `clz()` counts leading zeros, `atomic_cmpxchg` marks found, each work-item loops over a few thousand nonces. **Use a functional `sha256_block()` structure** (inlining both blocks slows down from register pressure — I measured 6.5 < 15.4 for the "optimized" version; don't repeat that). GLOBAL=1<<20, ITERS=4096. Between launches, the host checks found + whether the challenge changed.

> This repo ships a ready-made starting point: `hashbroker.py` (self-contained mining + submission, single file). Prefer reusing it — only change the top-level config (RPC/CONTRACT/CHAIN_ID/selectors) and the kernel preimage layout.

## Submission + main loop
- Each round: read `mintPrice()` first; **if non-zero (paid minting started), stop** (don't quietly pay for the user).
- Read `challenge()` + `currentDifficulty()` → mine → once found, **verify the challenge hasn't expired before submitting** (if expired, re-mine, otherwise it reverts and burns gas) → sign `mine(nonce, challenge)` with eth-account and send.
- **RPC requests must include a `user-agent` header** (many RPCs return 403 without one).
- The submitting wallet needs a little gas; top it up first.

## Key reminders (make sure to tell the user)
- **The challenge changes every time someone mints**: you must watch it and automatically switch to the new one and re-mine. **Difficulty rises with global supply** — more people = slower. Your hashrate needs to beat the challenge refresh rate for consistent hits; a single card relies on luck windows (per ~1-minute window, hit probability ≈ hashrate×60/2^difficulty).
- **A solution can appear before exhausting the search — it's a lottery.** With luck it comes early. The only way to be faster is more hashrate (stronger cards / multiple cards; OpenCL→CUDA via cupy can add another ~2×).

## Safety rules (must follow)
- Use a **burner** private key only; the key stays local, never shared or pasted anywhere. The script only does "read contract + hash + submit mine" — no transfers, no other signatures.
- ⚠️ **Reject variant scams**: if a project tells you to run **its executable**, or grind a vanity address with **its public key** (profanity2 `-z <pubkey>`) — that's grinding a private key for the scammer + baiting you to deposit. Hard pass. Only run open-source scripts you can read, only with your own wallet.
