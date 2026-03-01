# SE-PIM Cleaning Extension: Spec Notes from Paper

Source: `SE-PIM_In-Memory_Acceleration_of_Data-Intensive_Confidential_Computing-1.pdf`.

## Controlled Access Semantics
- Table 2 command surface includes `MEMCPY` and `ACCESS_DATA(DATA, ADDR, SZ, OP)` for controlled memory operations while secrecy is maintained.
- Parameters travel on the protected parameter channel (encrypted/fixed-size semantics in the paper model).
- This extension keeps host-side cleaning traffic on `ACCESS_DATA` (and optional dummy operations) so the host does not directly map locked bank memory.

## DRAM Lockdown + Integrity
- Paper Section 6.3 models lockdown in memory filtering logic and uses lock registers (`address_start`, `address_mask`) mapped to PIM-visible space.
- Host direct accesses to locked ranges are denied; authenticated SE-PIM channel accesses are allowed.
- This extension keeps lockdown active for the full cleaning window and only unlocks after cleaning + k-means complete.

## Fixed Channel / Bus-Trace Property (Fig. 8 Narrative)
- Paper evaluation highlights that secure mode should expose fixed command/parameter channel behavior rather than lookup-dependent bank-address patterns.
- This extension preserves that property by routing hybrid host cleaning through fixed MMIO/CMD + controlled-channel operations instead of direct memory mappings.
- Optional dummy semantics are provided to approximate ORAM-like behavior (extra dummy reads) when stronger traffic shaping is desired.

## Practical Mapping in This Repo
- `pim_cleaner.*`: PIM-side scan + PIM-only cleaning pass.
- `host_cleaner.*`: Hybrid path where host reads/writes dirty points using `ACCESS_DATA` only.
- `kmeans_sepim_fs --cleaning=off|pim|hybrid`: toggles pipeline while keeping k-means computation model unchanged.
