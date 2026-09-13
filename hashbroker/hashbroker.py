#!/usr/bin/env python3
# ============================================================================
#  HashBroker local GPU miner (single file, NVIDIA GPU)
#  On-chain SHA-256 proof-of-work -> free mint (gas only). Auto-submits with
#  your wallet when a solution is found.
#
#  Deps:  pip install pyopencl eth-account
#  Usage: set environment variable PK=your wallet private key (0x...), then
#         python hashbroker.py
#         optional COUNT=how many to mine (default: keep going until paid
#         minting starts). Stop: Ctrl+C.
#
#  Principle: preimage = address(20) || zeros(24) || nonce(8) || challenge(32)  ->  SHA-256
#        needs leading zero bits >= on-chain currentDifficulty(); submit mine(nonce, challenge).
#        The challenge changes every time someone mints -> this miner watches for it and
#        automatically switches to the new challenge and re-mines. Before submitting it
#        verifies the challenge hasn't expired (otherwise it gets sniped/reverts).
#  ⚠️ Competition: difficulty rises with global supply; your hashrate needs to beat
#     the challenge refresh rate for consistent hits. A single card relies on luck windows.
# ============================================================================
import os, sys, time, json, struct, urllib.request
import numpy as np
import pyopencl as cl
from eth_account import Account

# ---- Config (edit here to switch projects) ----
RPC      = "https://rpc.mainnet.chain.robinhood.com"
CONTRACT = "0x4272D6f51771839F596082eF48fa84D35239Bab3"
CHAIN_ID = 4663
SEL_CHALLENGE  = "0xd2ef7398"   # challenge() -> bytes32
SEL_DIFFICULTY = "0x5c062d6c"   # currentDifficulty() -> uint256
SEL_PRICE      = "0x6817c76c"   # mintPrice() -> uint256
SEL_MINE       = "0xe43e322c"   # mine(uint256 nonce, bytes32 challenge)

PK = os.environ.get("PK", "").strip()
if not PK:
    sys.exit("Please set the environment variable PK=your wallet private key (0x...)")
acct = Account.from_key(PK)
ADDR = acct.address
COUNT = int(os.environ.get("COUNT", "999"))

def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    # note: many RPCs return 403 without a User-Agent — always send one
    req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
    r = json.loads(urllib.request.urlopen(req, timeout=20).read())
    if "error" in r: raise RuntimeError(r["error"])
    return r["result"]

def call(data):
    return rpc("eth_call", [{"to": CONTRACT, "data": data}, "latest"])

def challenge():   return call(SEL_CHALLENGE)            # 0x + 64 hex
def difficulty():  return int(call(SEL_DIFFICULTY), 16)
def mint_price():  return int(call(SEL_PRICE), 16)

# ---- OpenCL mining (multi-GPU: every device on every platform, one thread per GPU) ----
GPUS = []
for p in cl.get_platforms():
    for d in p.get_devices():
        GPUS.append(d)
if not GPUS:
    sys.exit("❌ no OpenCL devices found")
CTXS = {d: cl.Context([d]) for d in GPUS}
print(f"GPUs: {len(GPUS)}  wallet: {ADDR}", flush=True)
for i, d in enumerate(GPUS):
    print(f"  [gpu{i}] {d.name} ({d.max_compute_units} CU)", flush=True)

KERNEL = r"""
__constant uint K[64]={0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,0xe49b69c1u,0xefbe4786u,
0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,
0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,
0x81c2c92eu,0x92722c85u,0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,0x748f82eeu,0x78a5636fu,
0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
#define ROR(x,n) rotate((uint)(x),(uint)(32-(n)))
#define S0(x) (ROR(x,2)^ROR(x,13)^ROR(x,22))
#define S1(x) (ROR(x,6)^ROR(x,11)^ROR(x,25))
#define s0(x) (ROR(x,7)^ROR(x,18)^((x)>>3))
#define s1(x) (ROR(x,17)^ROR(x,19)^((x)>>10))
void blk(uint* h,const uint* in){uint w[64];for(int i=0;i<16;i++)w[i]=in[i];
 for(int i=16;i<64;i++)w[i]=s1(w[i-2])+w[i-7]+s0(w[i-15])+w[i-16];
 uint a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
 for(int i=0;i<64;i++){uint t1=hh+S1(e)+((e&f)^(~e&g))+K[i]+w[i];uint t2=S0(a)+((a&b)^(a&c)^(b&c));hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}
 h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;}
__kernel void mine(ulong base,__global volatile int* found,__global ulong* out){
 ulong nb=base+(ulong)get_global_id(0)*ITERS;
 for(uint it=0;it<ITERS;it++){ if(*found)return; ulong nonce=nb+it;
  uint b1[16]={A0,A1,A2,A3,A4,0,0,0,0,0,0,(uint)(nonce>>32),(uint)(nonce&0xffffffffu),C0,C1,C2};
  uint b2[16]={C3,C4,C5,C6,C7,0x80000000u,0,0,0,0,0,0,0,0,0,672u};
  uint h[8]={0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
  blk(h,b1);blk(h,b2);
  int lz=0;for(int i=0;i<8;i++){if(h[i]==0u)lz+=32;else{lz+=clz(h[i]);break;}}
  if(lz>=DIFF){if(atomic_cmpxchg(found,0,1)==0)*out=nonce;return;}}}
"""

def mine(ch_hex, diff, check_stale):
    """Mine the current challenge across ALL GPUs. Returns a nonce (int) or None (challenge changed / needs re-mining)."""
    addr_w = struct.unpack(">5I", bytes.fromhex(ADDR[2:]))
    ch_w   = struct.unpack(">8I", bytes.fromhex(ch_hex[2:]))
    ITERS = 4096
    defs = dict(ITERS=ITERS, DIFF=diff, A0=addr_w[0],A1=addr_w[1],A2=addr_w[2],A3=addr_w[3],A4=addr_w[4],
                C0=ch_w[0],C1=ch_w[1],C2=ch_w[2],C3=ch_w[3],C4=ch_w[4],C5=ch_w[5],C6=ch_w[6],C7=ch_w[7])
    src = KERNEL
    for k,v in defs.items(): src = src.replace(k, f"{v}u" if k in ("A0","A1","A2","A3","A4","C0","C1","C2","C3","C4","C5","C6","C7") else str(v))

    import threading
    stop_evt = threading.Event()
    result = [None, None]      # [winning nonce, error]  (list contents get replaced, typed loosely)
    stats = [0] * len(GPUS)
    t0 = time.time()
    GLOBAL = 1<<20; per = GLOBAL*ITERS
    SPACE = 1 << 57            # disjoint nonce space per GPU (no overlap, no double work)
    base0 = int.from_bytes(os.urandom(6), "big")

    def worker(idx, dev, base):
        try:
            ctx = CTXS[dev]; q = cl.CommandQueue(ctx)
            prg = cl.Program(ctx, src).build()
            mf = cl.mem_flags
            found = np.zeros(1, np.int32); out = np.zeros(1, np.uint64)
            fg = cl.Buffer(ctx, mf.READ_WRITE|mf.COPY_HOST_PTR, hostbuf=found)
            og = cl.Buffer(ctx, mf.READ_WRITE|mf.COPY_HOST_PTR, hostbuf=out)
            while not stop_evt.is_set() and result[0] is None:
                prg.mine(q, (GLOBAL,), None, np.uint64(base), fg, og); q.finish()
                cl.enqueue_copy(q, found, fg)
                stats[idx] += per; base = (base + per) & ((1<<64)-1)
                if found[0]:
                    cl.enqueue_copy(q, out, og); q.finish()
                    result[0] = int(out[0]); stop_evt.set(); return
                now = time.time()
                if now - t0 >= 5 and idx == 0:
                    tot = sum(stats)
                    print(f"  {tot/(now-t0)/1e9:.1f} GH/s (all GPUs)  best-effort mining diff {diff}…", flush=True)
                    globals()["_last_report"] = now
        except Exception as e:
            print(f"  [gpu{idx}] error: {e}", flush=True)
            result[1] = f"gpu{idx}: {e}"; stop_evt.set()

    threads = []
    for idx, dev in enumerate(GPUS):
        t = threading.Thread(target=worker, args=(idx, dev, (base0 + idx*SPACE) & ((1<<64)-1)), daemon=True)
        t.start(); threads.append(t)
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.3)
            if result[0] is not None or result[1]: break
            if check_stale():   # challenge changed -> re-mine
                stop_evt.set(); return None
    finally:
        stop_evt.set()
        for t in threads: t.join(timeout=5)
    if result[1]: raise SystemExit(f"❌ {result[1]}")
    return result[0]

def submit(nonce, ch_hex):
    data = SEL_MINE + f"{nonce:064x}" + ch_hex[2:]
    tx = {"nonce": int(rpc("eth_getTransactionCount", [ADDR, "pending"]), 16),
          "to": CONTRACT, "value": 0, "gas": 250000,
          "gasPrice": int(rpc("eth_gasPrice", []), 16), "data": data, "chainId": CHAIN_ID}
    signed = acct.sign_transaction(tx)
    h = rpc("eth_sendRawTransaction", ["0x"+signed.raw_transaction.hex()])
    for _ in range(40):
        r = rpc("eth_getTransactionReceipt", [h])
        if r: return r.get("status") == "0x1", h
        time.sleep(0.4)
    return False, h

got = 0
try:
    while got < COUNT:
        if mint_price() != 0:
            print(f"⛔ mintPrice is non-zero (paid minting started). Free mints so far: {got}. Stopping."); break
        ch = challenge(); diff = difficulty()
        print(f"[{time.strftime('%H:%M:%S')}] mining challenge {ch[:12]}… difficulty {diff}", flush=True)
        stale = lambda: challenge().lower() != ch.lower()
        nonce = mine(ch, diff, stale)
        if nonce is None:
            print("  challenge changed → re-mining"); continue
        if challenge().lower() != ch.lower():
            print("  solved but challenge expired → re-mining"); continue
        ok, txh = submit(nonce, ch)
        if ok: got += 1; print(f"  ✓ found and minted! nonce {nonce}  tx {txh}")
        else:  print(f"  ✗ submission reverted (sniped/expired) → re-mining  {txh[:12]}")
    print(f"=== done · total free mints: {got} ===")
except KeyboardInterrupt:
    print(f"\nstopped · total free mints: {got}")
