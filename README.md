# pow_hashbroker

Local GPU mining for **on-chain PoW free mint** NFTs (HashBroker-style). Find a nonce meeting the difficulty → submit `mine(nonce, challenge)`, value=0, **gas only**.

- `hashbroker/hashbroker.py` — self-contained miner (pyopencl SHA-256 + eth-account submission). Single file; change the config at the top to repurpose for another project.
- `hashbroker/SKILL.md` — a [CC] skill so your own Claude can build a local miner from scratch.

## How it works

```
preimage = address(20) || zeros(24) || nonce(8) || challenge(32)   ->  SHA-256
needs leading zero bits >= on-chain currentDifficulty(); when satisfied, submit mine(nonce, challenge)
```

The challenge changes every time someone mints; the script watches for it and automatically switches to the new one and re-mines. Before submitting it verifies the challenge hasn't expired. Difficulty rises with global supply — the more people, the slower. **This is a lottery, not a finite search**: with luck a solution comes early; the only way to be faster is more hashrate.

## Usage

```bash
pip install pyopencl eth-account numpy

# use a small burner private key ONLY!
export PK=0xyourburnerkey        # Windows PowerShell: $env:PK="0x..."
export COUNT=1                    # optional, how many to mine (default: keep going until paid minting starts)
python hashbroker/hashbroker.py
```

Measured on an RTX 5090: ≈ 15.4 GH/s per card. **Multi-GPU is supported**: every OpenCL device found is used automatically — one thread per GPU with disjoint nonce ranges, so N cards ≈ N× the hashrate. Expected time to solve = `2^difficulty / total hashrate`: difficulty 42 ≈ 5 minutes on one 5090, doubling with each +1 level.

To repurpose for another PoW project: edit `RPC / CONTRACT / CHAIN_ID / selectors` at the top of `hashbroker.py`, and verify the preimage layout against that project's frontend.

## ⚠️ Safety rules

- **Use a burner private key only**; keep the key in a local environment variable — never hardcode it, never paste it into chats or upload it. The script only does "read contract + hash + submit mine" — no transfers, no other signatures.
- **Reject variant scams**: if a project asks you to run *its executable*, or grind a vanity address with *its public key* (e.g. `profanity2 -z <pubkey>`) — that's grinding a private key for the scammer + baiting you to deposit. Hard pass. Only run open-source scripts you can read, only with your own wallet.
- If paid minting starts (`mintPrice != 0`), the script stops automatically — it will never quietly pay for you.

## License

[MIT](LICENSE) — provided as-is, the author is not responsible for any losses. Use at your own risk.
