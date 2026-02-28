# SE-PIM spec extracted from paper (authoritative baseline)

Source PDF: `SE-PIM_In-Memory_Acceleration_of_Data-Intensive_Confidential_Computing-1.pdf`

## Table 2: SE-PIM commands

From Table 2 (“Commands Supported by SE-PIM, Their Parameters, Results, and Descriptions”):

| Command | Parameters | Results | Semantics |
|---|---|---|---|
| `GET_CERT` | `-` | `PIM_CERT` | Return SE-PIM certificate for remote attestation. |
| `SET_SESSION_KEY` | `SESSION_KEY` | `-` | Install encrypted session key for secure command/parameter channel. |
| `SET_DATA_KEY` | `DATA_KEY` | `-` | Install data key for encrypt/decrypt of bank-resident data. |
| `LOAD_KERNEL` | `KERNEL_BINARIES` | `LOCAL_MEM_MEASUREMENT` | Load SE-PIM kernel into local memory and return measurement/hash. |
| `EXECUTE*` | `FN_NAME`, `FN_ARGS` | `RESULTS` | Execute kernel function with arguments and return results. |
| `LOCK_MEM` | `-` | `BANK_MEASUREMENT` | Enable DRAM lockdown for protected bank range, return integrity measurement/hash. |
| `MEMCPY` | `DST_ADDR`, `SRC_ADDR`, `SZ` | `-` | Move data inside bank during lockdown via controlled channel. |
| `ACCESS_DATA` | `DATA`, `ADDR`, `SZ`, `OP` | `DATA` | Controlled read/write during lockdown (encrypted request fields). |
| `UNLOCK_MEM` | `-` | `-` | Disable DRAM lockdown. |
| `DESTROY` | `-` | `-` | Clear local memory, unlock bank, stop SE-PIM execution. |

Notes from table text:
- `EXECUTE` parameters/results are kernel-defined.
- `GET_CERT` and `DESTROY` do not require authentication.

## Table 3: simulation configuration target

From Table 3 (“Configuration of the Simulated System”):

- Host CPU: 8 in-order ARMv7 cores, 2 threads/core, 4.0 GHz.
- Cache hierarchy: per-core L1I 32 KB + L1D 64 KB; shared LLC 256 KB.
- OS: Linux kernel 3.16.0-rc6.
- Memory: 8 PIM-enabled banks, 64 MB/bank, memory type `gem5 HMCVault`.
- PIM side: 1 in-order ARMv7 core per bank, 1 thread/core, 1 GHz, 1 MB local memory/core.

## Architecture/implementation requirements (Sections 4–6)

### Communication and keying
- Command channel uses fixed MMIO addresses.
- Parameter channel is encrypted/authenticated (AES-GCM) and fixed-size messages.
- Monotonic counter/nonce is used to provide replay resistance and indistinguishability.

### ROM/prototype behavior
- Production design assumes secure ROM for attestation/key-exchange logic.
- Prototype shortcut: ROM code is implemented in PIM kernel code and loaded into local memory (same functional behavior in simulator).

### AES-capable DMA engine (Section 6.2)
- Functional correctness implementation uses OpenSSL-backed AES-GCM path in memory controller/DMA path.
- DMA/AES control registers are MMIO-mapped in PIM-core address space (Fig. 7).
- Latency model in simulator: estimate AES engine as 300 MHz, 128-bit block per cycle, add `+1 cycle` per 16-byte chunk processed.

### DRAM lockdown (Section 6.3)
- Implement protection via address filtering in memory packet handling.
- In gem5 prototype, this is implemented by modifying `AbstractMemory` packet handling logic.
- Two MMIO registers mapped in PIM-core address space configure protected range:
  - `address_start`
  - `address_mask`

### Memory integrity measurement
- `LOAD_KERNEL` returns local-memory measurement/hash.
- `LOCK_MEM` returns bank-memory measurement/hash so host can verify no tampering between load and lock windows.

## Evaluation methodology notes (Sections 7.1–7.3)

### Fig. 8 bus-observable trace
- Use a hash-table lookup workload (Murmur3 index into hash table).
- Place tracing unit between L2 and DRAM (memory bus side) and log physical addresses/RW over time.
- Since modeled CPU cache-flush instruction behavior is inaccurate, force eviction by repetitive memory accesses (thrashing buffer) after each lookup.
- CPU-only model leaks lookup-dependent addresses; SE-PIM model should show fixed communication-channel pattern.

### Fig. 9 DMA microbenchmark
- 1000 DMA transfers per configuration.
- Vary transfer size 512B..8192B.
- Include sequential/random and both transfer directions (local↔bank).
- Compare Baseline-PIM DMA vs AES-enabled DMA.

### Fig. 10 controlled access throughput
- Throughput measured versus block size (1KB..128KB) using controlled access channel.
- Compare against normal DRAM access and Path ORAM reference.

### Fig. 11 k-means scaling
- Compare CPU-only, baseline PIM, and SE-PIM for k-means rounds.
- Scale by dataset size up to 512MB and PIM cores 1/2/4/8.
- Keep baseline PIM and SE-PIM kernel algorithm identical; SE-PIM only adds security features.
