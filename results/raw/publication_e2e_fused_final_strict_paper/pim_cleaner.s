	.arch armv8-a
	.file	"pim_cleaner.c"
// GNU C99 (Ubuntu/Linaro 7.5.0-3ubuntu1~18.04) version 7.5.0 (aarch64-linux-gnu)
//	compiled by GNU C version 7.5.0, GMP version 6.1.2, MPFR version 4.0.1, MPC version 1.1.0, isl version isl-0.19-GMP

// GGC heuristics: --param ggc-min-expand=100 --param ggc-min-heapsize=131072
// options passed:  -I IMPICA/pim_driver -imultiarch aarch64-linux-gnu
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c -mlittle-endian
// -mabi=lp64
// -auxbase-strip /workspace/results/raw/publication_e2e_fused_final_strict_paper/pim_cleaner.s
// -O2 -Wall -Wextra -std=gnu99 -fverbose-asm -fstack-protector-strong
// -Wformat-security
// options enabled:  -fPIC -fPIE -faggressive-loop-optimizations
// -falign-labels -fauto-inc-dec -fbranch-count-reg -fcaller-saves
// -fchkp-check-incomplete-type -fchkp-check-read -fchkp-check-write
// -fchkp-instrument-calls -fchkp-narrow-bounds -fchkp-optimize
// -fchkp-store-bounds -fchkp-use-static-bounds
// -fchkp-use-static-const-bounds -fchkp-use-wrappers -fcode-hoisting
// -fcombine-stack-adjustments -fcommon -fcompare-elim -fcprop-registers
// -fcrossjumping -fcse-follow-jumps -fdefer-pop
// -fdelete-null-pointer-checks -fdevirtualize -fdevirtualize-speculatively
// -fdwarf2-cfi-asm -fearly-inlining -feliminate-unused-debug-types
// -fexpensive-optimizations -fforward-propagate -ffp-int-builtin-inexact
// -ffunction-cse -fgcse -fgcse-lm -fgnu-runtime -fgnu-unique
// -fguess-branch-probability -fhoist-adjacent-loads -fident
// -fif-conversion -fif-conversion2 -findirect-inlining -finline
// -finline-atomics -finline-functions-called-once -finline-small-functions
// -fipa-bit-cp -fipa-cp -fipa-icf -fipa-icf-functions -fipa-icf-variables
// -fipa-profile -fipa-pure-const -fipa-ra -fipa-reference -fipa-sra
// -fipa-vrp -fira-hoist-pressure -fira-share-save-slots
// -fira-share-spill-slots -fisolate-erroneous-paths-dereference -fivopts
// -fkeep-static-consts -fleading-underscore -flifetime-dse -flra-remat
// -flto-odr-type-merging -fmath-errno -fmerge-constants
// -fmerge-debug-strings -fmove-loop-invariants -fomit-frame-pointer
// -foptimize-sibling-calls -foptimize-strlen -fpartial-inlining -fpeephole
// -fpeephole2 -fplt -fprefetch-loop-arrays -free -freg-struct-return
// -freorder-blocks -freorder-functions -frerun-cse-after-loop
// -fsched-critical-path-heuristic -fsched-dep-count-heuristic
// -fsched-group-heuristic -fsched-interblock -fsched-last-insn-heuristic
// -fsched-pressure -fsched-rank-heuristic -fsched-spec
// -fsched-spec-insn-heuristic -fsched-stalled-insns-dep -fschedule-fusion
// -fschedule-insns -fschedule-insns2 -fsection-anchors
// -fsemantic-interposition -fshow-column -fshrink-wrap
// -fshrink-wrap-separate -fsigned-zeros -fsplit-ivs-in-unroller
// -fsplit-wide-types -fssa-backprop -fssa-phiopt -fstack-protector-strong
// -fstdarg-opt -fstore-merging -fstrict-aliasing -fstrict-overflow
// -fstrict-volatile-bitfields -fsync-libcalls -fthread-jumps
// -ftoplevel-reorder -ftrapping-math -ftree-bit-ccp
// -ftree-builtin-call-dce -ftree-ccp -ftree-ch -ftree-coalesce-vars
// -ftree-copy-prop -ftree-cselim -ftree-dce -ftree-dominator-opts
// -ftree-dse -ftree-forwprop -ftree-fre -ftree-loop-if-convert
// -ftree-loop-im -ftree-loop-ivcanon -ftree-loop-optimize
// -ftree-parallelize-loops= -ftree-phiprop -ftree-pre -ftree-pta
// -ftree-reassoc -ftree-scev-cprop -ftree-sink -ftree-slsr -ftree-sra
// -ftree-switch-conversion -ftree-tail-merge -ftree-ter -ftree-vrp
// -funit-at-a-time -fverbose-asm -fzero-initialized-in-bss
// -mfix-cortex-a53-835769 -mfix-cortex-a53-843419 -mglibc -mlittle-endian
// -momit-leaf-frame-pointer -mpc-relative-literal-loads

	.text
	.align	2
	.p2align 3,,7
	.type	detect_dirty_type, %function
detect_dirty_type:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:78:     if (dims > 0 && point[0] == KMEANS_NULL_SENTINEL) {
	cbz	w1, .L8	// dims,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:78:     if (dims > 0 && point[0] == KMEANS_NULL_SENTINEL) {
	mov	x2, x0	// ivtmp.48, point
	mov	w0, 9200	// tmp142,
	movk	w0, 0xc974, lsl 16	// tmp142,,
	fmov	s2, w0	// tmp128, tmp142
	sub	w1, w1, #1	// tmp129, dims,
	ldr	s1, [x2], 4	// prephitmp_15, *point_13(D)
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:76:     uint8_t ty = DIRTY_TYPE_NONE;
	fcmp	s1, s2	// prephitmp_15, tmp128
	add	x3, x2, x1, uxtw 2	// _32, ivtmp.48, tmp129,
	cset	w1, eq	// tmp139,
	lsl	w0, w1, 1	// ty, tmp139,
	b	.L7	//
	.p2align 2
.L13:
	ldr	s1, [x2], 4	// prephitmp_15, MEM[base: _14, offset: 0B]
.L7:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:84:         if (isnan(v)) {
	fcmp	s1, s1	// prephitmp_15, prephitmp_15
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:89:             ty |= DIRTY_TYPE_OUTLIER;
	orr	w1, w0, 4	// tmp137, ty,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:88:         if (!(ty & DIRTY_TYPE_NULL) && fabsf(v) > outlier_threshold) {
	fabs	s2, s1	// tmp136, prephitmp_15
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:89:             ty |= DIRTY_TYPE_OUTLIER;
	and	w1, w1, 255	// tmp141, tmp137
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:84:         if (isnan(v)) {
	bvs	.L12	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:88:         if (!(ty & DIRTY_TYPE_NULL) && fabsf(v) > outlier_threshold) {
	tbnz	x0, 1, .L5	// ty,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:89:             ty |= DIRTY_TYPE_OUTLIER;
	fcmpe	s2, s0	// tmp136, outlier_threshold
	csel	w0, w1, w0, gt	// ty, tmp141, ty,
.L5:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:82:     for (uint32_t d = 0; d < dims; ++d) {
	cmp	x2, x3	// ivtmp.48, _32
	bne	.L13	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:94: }
	ret
	.p2align 2
.L8:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:76:     uint8_t ty = DIRTY_TYPE_NONE;
	mov	w0, 0	// ty,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:94: }
	ret
	.p2align 2
.L12:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:85:             ty |= DIRTY_TYPE_NAN;
	orr	w1, w0, 1	// tmp132, ty,
	and	w0, w1, 255	// ty, tmp132
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:86:             continue;
	b	.L5	//
	.size	detect_dirty_type, .-detect_dirty_type
	.align	2
	.p2align 3,,7
	.global	pim_bank_load_dataset
	.type	pim_bank_load_dataset, %function
pim_bank_load_dataset:
	stp	x29, x30, [sp, -112]!	//,,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:102:     if (path == NULL || bank == NULL) {
	cmp	x0, 0	// path,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:97: {
	add	x29, sp, 0	//,,
	str	x22, [sp, 40]	//,
	adrp	x22, :got:__stack_chk_guard	// tmp159,
	str	x19, [sp, 16]	//,
	mov	x19, x1	// bank, bank
	ldr	x1, [x22, #:got_lo12:__stack_chk_guard]	// tmp106, tmp159,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:102:     if (path == NULL || bank == NULL) {
	ccmp	x19, 0, 4, ne	// bank,,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:97: {
	ldr	x2, [x1]	// tmp160, __stack_chk_guard
	str	x2, [x29, 104]	// tmp160, D.6379
	mov	x2,0	// tmp160
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:102:     if (path == NULL || bank == NULL) {
	beq	.L24	//,
	str	x21, [x29, 32]	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:108:     fp = fopen(path, "rb");
	adrp	x1, .LC0	// tmp112,
	str	x23, [x29, 48]	//,
	add	x1, x1, :lo12:.LC0	//, tmp112,
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x19]	// MEM[(void *)bank_34(D)]
	mov	x23, x0	// path, path
	str	xzr, [x19, 16]	//, MEM[(void *)bank_34(D)]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:108:     fp = fopen(path, "rb");
	bl	fopen	//
	mov	x21, x0	// fp,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:109:     if (!fp) {
	cbz	x0, .L30	// fp,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:294:   return __fread_alias (__ptr, __size, __n, __stream);
	mov	x3, x0	//, fp
	str	x24, [x29, 56]	//,
	mov	x2, 1	//,
	mov	x1, 32	//,
	add	x0, x29, 72	//,,
	bl	fread	//
	mov	x24, x0	// _55,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:114:     if (fread(&hdr, sizeof(hdr), 1, fp) != 1) {
	cmp	x0, 1	// _55,
	bne	.L31	//,
	ldp	w3, w4, [x29, 72]	//,, hdr.magic
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:120:     if (hdr.magic != KMEANS_DATASET_MAGIC || hdr.version != KMEANS_DATASET_VERSION ||
	mov	w0, 17491	// tmp124,
	movk	w0, 0x4b4d, lsl 16	// tmp124,,
	ldp	w5, w6, [x29, 80]	//,, hdr.num_points
	cmp	w3, w0	// _9, tmp124
	bne	.L18	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:120:     if (hdr.magic != KMEANS_DATASET_MAGIC || hdr.version != KMEANS_DATASET_VERSION ||
	cmp	w4, 1	// pretmp_63,
	bne	.L18	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:121:         hdr.num_points == 0 || hdr.num_points > KMEANS_MAX_POINTS || hdr.dims == 0 ||
	sub	w1, w5, #1	// tmp125, pretmp_65,
	mov	w0, 57599	// tmp126,
	movk	w0, 0x5f5, lsl 16	// tmp126,,
	cmp	w1, w0	// tmp125, tmp126
	bhi	.L18	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:121:         hdr.num_points == 0 || hdr.num_points > KMEANS_MAX_POINTS || hdr.dims == 0 ||
	sub	w0, w6, #1	// tmp127, pretmp_82,
	cmp	w0, 4095	// tmp127,
	bhi	.L18	//,
	str	x20, [x29, 24]	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:124:         (size_t)hdr.num_points * (size_t)hdr.dims > SIZE_MAX / sizeof(float)) {
	umull	x20, w5, w6	// _15, pretmp_65, pretmp_82
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:133:     bank->points = (float *)malloc(total_vals * sizeof(float));
	lsl	x0, x20, 2	//, _15,
	bl	malloc	//
	str	x0, [x19, 16]	// tmp129, bank_34(D)->points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:134:     if (!bank->points) {
	cbz	x0, .L32	// tmp129,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:294:   return __fread_alias (__ptr, __size, __n, __stream);
	mov	x3, x21	//, fp
	mov	x2, x20	//, _15
	mov	x1, 4	//,
	bl	fread	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:140:     if (fread(bank->points, sizeof(float), total_vals, fp) != total_vals) {
	cmp	x20, x0	// _15,
	bne	.L33	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:148:     if (fgetc(fp) != EOF) {
	mov	x0, x21	//, fp
	bl	fgetc	//
	cmn	w0, #1	//,
	bne	.L34	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:156:     fclose(fp);
	mov	x0, x21	//, fp
	bl	fclose	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:160:     bank->seed = hdr.seed;
	ldr	w0, [x29, 88]	//, hdr.seed
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:159:     bank->dims = hdr.dims;
	ldp	w2, w1, [x29, 80]	//,, hdr.num_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:161:     return 0;
	ldp	x20, x21, [x29, 24]	//,,
	ldp	x23, x24, [x29, 48]	//,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:159:     bank->dims = hdr.dims;
	stp	w2, w1, [x19]	// hdr.num_points, hdr.dims, bank_34(D)->num_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:160:     bank->seed = hdr.seed;
	str	w0, [x19, 8]	// hdr.seed, bank_34(D)->seed
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:161:     return 0;
	mov	w0, 0	// <retval>,
.L14:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:162: }
	ldr	x22, [x22, #:got_lo12:__stack_chk_guard]	// tmp156, tmp159,
	ldr	x2, [x29, 104]	// tmp161, D.6379
	ldr	x1, [x22]	// tmp158, __stack_chk_guard
	eor	x1, x2, x1	// tmp158, tmp161
	cbnz	x1, .L35	// tmp158,
	ldr	x19, [sp, 16]	//,
	ldr	x22, [sp, 40]	//,
	ldp	x29, x30, [sp], 112	//,,,
	ret
	.p2align 2
.L18:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:125:         fprintf(stderr,
	adrp	x0, :got:stderr	// tmp133,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	adrp	x2, .LC3	// tmp131,
	mov	w1, 1	//,
	add	x2, x2, :lo12:.LC3	//, tmp131,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:125:         fprintf(stderr,
	ldr	x0, [x0, #:got_lo12:stderr]	// tmp132, tmp133,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	ldr	x0, [x0]	//, stderr
	bl	__fprintf_chk	//
.L27:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:128:         fclose(fp);
	mov	x0, x21	//, fp
	bl	fclose	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:129:         return -1;
	mov	w0, -1	// <retval>,
	ldr	x21, [x29, 32]	//,
	ldp	x23, x24, [x29, 48]	//,,
	b	.L14	//
	.p2align 2
.L24:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:103:         return -1;
	mov	w0, -1	// <retval>,
	b	.L14	//
	.p2align 2
.L33:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:141:         fprintf(stderr, "pim_bank_load_dataset: failed to read dataset body\n");
	adrp	x3, :got:stderr	// tmp141,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	adrp	x0, .LC5	// tmp144,
	mov	x2, 51	//,
	mov	x1, x24	//, _55
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:141:         fprintf(stderr, "pim_bank_load_dataset: failed to read dataset body\n");
	ldr	x3, [x3, #:got_lo12:stderr]	// tmp140, tmp141,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	add	x0, x0, :lo12:.LC5	//, tmp144,
	ldr	x3, [x3]	//, stderr
	bl	fwrite	//
.L29:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:150:         free(bank->points);
	ldr	x0, [x19, 16]	//, bank_34(D)->points
	bl	free	//
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x19]	// MEM[(void *)bank_34(D)]
	str	xzr, [x19, 16]	//, MEM[(void *)bank_34(D)]
.L28:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:152:         fclose(fp);
	mov	x0, x21	//, fp
	bl	fclose	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:153:         return -1;
	mov	w0, -1	// <retval>,
	ldp	x20, x21, [x29, 24]	//,,
	ldp	x23, x24, [x29, 48]	//,,
	b	.L14	//
	.p2align 2
.L34:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:149:         fprintf(stderr, "pim_bank_load_dataset: trailing bytes in %s\n", path);
	adrp	x0, :got:stderr	// tmp149,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	mov	x3, x23	//, path
	mov	w1, 1	//,
	adrp	x2, .LC6	// tmp147,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:149:         fprintf(stderr, "pim_bank_load_dataset: trailing bytes in %s\n", path);
	ldr	x0, [x0, #:got_lo12:stderr]	// tmp148, tmp149,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	add	x2, x2, :lo12:.LC6	//, tmp147,
	ldr	x0, [x0]	//, stderr
	bl	__fprintf_chk	//
	b	.L29	//
	.p2align 2
.L31:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:115:         fprintf(stderr, "pim_bank_load_dataset: failed to read header from %s\n", path);
	adrp	x0, :got:stderr	// tmp122,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	mov	x3, x23	//, path
	adrp	x2, .LC2	// tmp120,
	mov	w1, 1	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:115:         fprintf(stderr, "pim_bank_load_dataset: failed to read header from %s\n", path);
	ldr	x0, [x0, #:got_lo12:stderr]	// tmp121, tmp122,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	add	x2, x2, :lo12:.LC2	//, tmp120,
	ldr	x0, [x0]	//, stderr
	bl	__fprintf_chk	//
	b	.L27	//
.L30:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:110:         fprintf(stderr, "pim_bank_load_dataset: failed to open %s: %s\n", path, strerror(errno));
	adrp	x0, :got:stderr	// tmp114,
	ldr	x0, [x0, #:got_lo12:stderr]	// tmp113, tmp114,
	ldr	x19, [x0]	// stderr.0_4, stderr
	bl	__errno_location	//
	ldr	w0, [x0]	//, *_5
	bl	strerror	//
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	mov	x4, x0	//,
	mov	x3, x23	//, path
	adrp	x2, .LC1	// tmp117,
	mov	w1, 1	//,
	add	x2, x2, :lo12:.LC1	//, tmp117,
	mov	x0, x19	//, stderr.0_4
	bl	__fprintf_chk	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:111:         return -1;
	mov	w0, -1	// <retval>,
	ldr	x21, [x29, 32]	//,
	ldr	x23, [x29, 48]	//,
	b	.L14	//
.L32:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:135:         fprintf(stderr, "pim_bank_load_dataset: out of memory\n");
	adrp	x3, :got:stderr	// tmp136,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	mov	x1, x24	//, _55
	mov	x2, 37	//,
	adrp	x0, .LC4	// tmp139,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:135:         fprintf(stderr, "pim_bank_load_dataset: out of memory\n");
	ldr	x3, [x3, #:got_lo12:stderr]	// tmp135, tmp136,
// /usr/aarch64-linux-gnu/include/bits/stdio2.h:97:   return __fprintf_chk (__stream, __USE_FORTIFY_LEVEL - 1, __fmt,
	add	x0, x0, :lo12:.LC4	//, tmp139,
	ldr	x3, [x3]	//, stderr
	bl	fwrite	//
	b	.L28	//
.L35:
	stp	x20, x21, [x29, 24]	//,,
	stp	x23, x24, [x29, 48]	//,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:162: }
	bl	__stack_chk_fail	//
	.size	pim_bank_load_dataset, .-pim_bank_load_dataset
	.align	2
	.p2align 3,,7
	.global	pim_bank_free
	.type	pim_bank_free, %function
pim_bank_free:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:166:     if (!bank) {
	cbz	x0, .L42	// bank,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:165: {
	stp	x29, x30, [sp, -32]!	//,,,
	add	x29, sp, 0	//,,
	str	x19, [sp, 16]	//,
	mov	x19, x0	// bank, bank
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:169:     free(bank->points);
	ldr	x0, [x0, 16]	//, bank_3(D)->points
	bl	free	//
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x19]	// MEM[(void *)bank_3(D)]
	str	xzr, [x19, 16]	//, MEM[(void *)bank_3(D)]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:171: }
	ldr	x19, [sp, 16]	//,
	ldp	x29, x30, [sp], 32	//,,,
	ret
	.p2align 2
.L42:
	ret
	.size	pim_bank_free, .-pim_bank_free
	.align	2
	.p2align 3,,7
	.global	pim_bank_clone
	.type	pim_bank_clone, %function
pim_bank_clone:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:177:     if (!src || !dst || !src->points || src->num_points == 0 || src->dims == 0) {
	cmp	x0, 0	// src,
	ccmp	x1, 0, 4, ne	// dst,,,
	beq	.L62	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:177:     if (!src || !dst || !src->points || src->num_points == 0 || src->dims == 0) {
	ldr	x2, [x0, 16]	// src_17(D)->points, src_17(D)->points
	cbz	x2, .L62	// src_17(D)->points,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:177:     if (!src || !dst || !src->points || src->num_points == 0 || src->dims == 0) {
	ldr	w2, [x0]	//, src_17(D)->num_points
	cbz	w2, .L62	// src_17(D)->num_points,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:177:     if (!src || !dst || !src->points || src->num_points == 0 || src->dims == 0) {
	ldr	w2, [x0, 4]	//, src_17(D)->dims
	cbz	w2, .L62	// src_17(D)->dims,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:174: {
	stp	x29, x30, [sp, -64]!	//,,,
	add	x29, sp, 0	//,,
	stp	x19, x20, [sp, 16]	//,,
	mov	x20, x1	// dst, dst
	stp	x21, x22, [sp, 32]	//,,
	mov	x19, x0	// src, src
	str	x23, [sp, 48]	//,
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x1]	// MEM[(void *)dst_18(D)]
	str	xzr, [x1, 16]	//, MEM[(void *)dst_18(D)]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:182:     total_vals = (size_t)src->num_points * (size_t)src->dims;
	ldp	w23, w22, [x0]	//,, src_17(D)->num_points
	umull	x21, w23, w22	// total_vals, _7, _9
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:183:     dst->points = (float *)malloc(total_vals * sizeof(float));
	lsl	x21, x21, 2	// _11, total_vals,
	mov	x0, x21	//, _11
	bl	malloc	//
	str	x0, [x20, 16]	// tmp96, dst_18(D)->points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:184:     if (!dst->points) {
	cbz	x0, .L48	// tmp96,
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:34:   return __builtin___memcpy_chk (__dest, __src, __len, __bos0 (__dest));
	ldr	x1, [x19, 16]	//, src_17(D)->points
	mov	x2, x21	//, _11
	bl	memcpy	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:191:     dst->seed = src->seed;
	ldr	w0, [x19, 8]	//, src_17(D)->seed
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:190:     dst->dims = src->dims;
	stp	w23, w22, [x20]	// _7, _9, dst_18(D)->num_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:191:     dst->seed = src->seed;
	str	w0, [x20, 8]	// _14, dst_18(D)->seed
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:192:     return 0;
	mov	w0, 0	// <retval>,
.L45:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:193: }
	ldp	x19, x20, [sp, 16]	//,,
	ldp	x21, x22, [sp, 32]	//,,
	ldr	x23, [sp, 48]	//,
	ldp	x29, x30, [sp], 64	//,,,
	ret
	.p2align 2
.L48:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:178:         return -1;
	mov	w0, -1	// <retval>,
	b	.L45	//
	.p2align 2
.L62:
	mov	w0, -1	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:193: }
	ret
	.size	pim_bank_clone, .-pim_bank_clone
	.align	2
	.p2align 3,,7
	.global	pim_bank_read_points
	.type	pim_bank_read_points, %function
pim_bank_read_points:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:199:     if (!bank || !bank->points || !out_points || count == 0) {
	cbz	x0, .L71	// bank,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:199:     if (!bank || !bank->points || !out_points || count == 0) {
	ldr	x6, [x0, 16]	// _1, bank_17(D)->points
	mov	x4, x0	// bank, bank
	cbz	x6, .L71	// _1,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:199:     if (!bank || !bank->points || !out_points || count == 0) {
	cmp	x3, 0	// out_points,
	ccmp	w2, 0, 4, ne	// count,,,
	beq	.L71	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:202:     if (start_idx >= bank->num_points || count > (bank->num_points - start_idx)) {
	ldr	w5, [x0]	//, bank_17(D)->num_points
	cmp	w5, w1	// _5, start_idx
	bls	.L71	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:202:     if (start_idx >= bank->num_points || count > (bank->num_points - start_idx)) {
	sub	w5, w5, w1	// tmp94, _5, start_idx
	cmp	w5, w2	// tmp94, count
	bcc	.L71	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:196: {
	stp	x29, x30, [sp, -16]!	//,,,
	mov	x0, x3	// out_points, out_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:207:     memcpy(out_points, bank->points + ((size_t)start_idx * bank->dims), vals * sizeof(float));
	ubfiz	x2, x2, 2, 32	// tmp96, count,,
	ubfiz	x1, x1, 2, 32	// tmp99, start_idx,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:196: {
	add	x29, sp, 0	//,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:206:     vals = (size_t)count * (size_t)bank->dims;
	ldr	w3, [x4, 4]	// _9, bank_17(D)->dims
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:34:   return __builtin___memcpy_chk (__dest, __src, __len, __bos0 (__dest));
	mul	x2, x2, x3	//, tmp96, _9
	madd	x1, x1, x3, x6	//, tmp99, _9, _1
	bl	memcpy	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:208:     return 0;
	mov	w0, 0	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:209: }
	ldp	x29, x30, [sp], 16	//,,,
	ret
	.p2align 2
.L71:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:200:         return -1;
	mov	w0, -1	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:209: }
	ret
	.size	pim_bank_read_points, .-pim_bank_read_points
	.align	2
	.p2align 3,,7
	.global	pim_bank_write_points
	.type	pim_bank_write_points, %function
pim_bank_write_points:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:215:     if (!bank || !bank->points || !in_points || count == 0) {
	cbz	x0, .L82	// bank,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:215:     if (!bank || !bank->points || !in_points || count == 0) {
	ldr	x6, [x0, 16]	// _1, bank_17(D)->points
	cbz	x6, .L82	// _1,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:215:     if (!bank || !bank->points || !in_points || count == 0) {
	cmp	x3, 0	// in_points,
	ccmp	w2, 0, 4, ne	// count,,,
	beq	.L82	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:218:     if (start_idx >= bank->num_points || count > (bank->num_points - start_idx)) {
	ldr	w5, [x0]	//, bank_17(D)->num_points
	mov	w4, w1	// start_idx, start_idx
	cmp	w5, w1	// _5, start_idx
	bls	.L82	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:218:     if (start_idx >= bank->num_points || count > (bank->num_points - start_idx)) {
	sub	w5, w5, w1	// tmp94, _5, start_idx
	cmp	w5, w2	// tmp94, count
	bcc	.L82	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:212: {
	stp	x29, x30, [sp, -16]!	//,,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:223:     memcpy(bank->points + ((size_t)start_idx * bank->dims), in_points, vals * sizeof(float));
	ubfiz	x4, x4, 2, 32	// tmp96, start_idx,,
	ubfiz	x2, x2, 2, 32	// tmp100, count,,
	mov	x1, x3	// in_points, in_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:212: {
	add	x29, sp, 0	//,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:222:     vals = (size_t)count * (size_t)bank->dims;
	ldr	w0, [x0, 4]	// _9, bank_17(D)->dims
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:34:   return __builtin___memcpy_chk (__dest, __src, __len, __bos0 (__dest));
	mul	x2, x2, x0	//, tmp100, _9
	madd	x0, x4, x0, x6	//, tmp96, _9, _1
	bl	memcpy	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:224:     return 0;
	mov	w0, 0	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:225: }
	ldp	x29, x30, [sp], 16	//,,,
	ret
	.p2align 2
.L82:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:216:         return -1;
	mov	w0, -1	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:225: }
	ret
	.size	pim_bank_write_points, .-pim_bank_write_points
	.align	2
	.p2align 3,,7
	.global	pim_scan_dirty
	.type	pim_scan_dirty, %function
pim_scan_dirty:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:239:     if (!bank || !bank->points || !dirty_count || chunk_points == 0 || max_dirty == 0) {
	cbz	x0, .L103	// bank,
	mov	x10, x0	// bank, bank
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:239:     if (!bank || !bank->points || !dirty_count || chunk_points == 0 || max_dirty == 0) {
	ldr	x0, [x0, 16]	// bank_51(D)->points, bank_51(D)->points
	cbz	x0, .L103	// bank_51(D)->points,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:239:     if (!bank || !bank->points || !dirty_count || chunk_points == 0 || max_dirty == 0) {
	cmp	x5, 0	// dirty_count,
	mov	w15, w1	// chunk_points, chunk_points
	ccmp	w1, 0, 4, ne	// chunk_points,,,
	mov	w18, w2	// max_dirty, max_dirty
	ccmp	w2, 0, 4, ne	// max_dirty,,,
	beq	.L103	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:243:     if (!dirty_indices || !dirty_types || !stats) {
	cmp	x3, 0	// dirty_indices,
	mov	x14, x3	// dirty_indices, dirty_indices
	ccmp	x4, 0, 4, ne	// dirty_types,,,
	ccmp	x6, 0, 4, ne	// stats,,,
	beq	.L103	//,
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x6]	// MEM[(void *)stats_58(D)]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:249:     for (uint32_t base = 0; base < bank->num_points; base += chunk_points) {
	mov	x7, 0	//,
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x6, 16]	// MEM[(void *)stats_58(D)]
	fmov	s3, s0	// outlier_threshold, outlier_threshold
	stp	xzr, xzr, [x6, 32]	// MEM[(void *)stats_58(D)]
	uxtw	x13, w2	// _90, max_dirty
	stp	xzr, xzr, [x6, 48]	// MEM[(void *)stats_58(D)]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:237:     uint64_t seen = 0;
	mov	x9, 0	// seen,
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x6, 64]	// MEM[(void *)stats_58(D)]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:260:             stats->scan_cycles += 24u + (uint64_t)bank->dims * 6u;
	mov	w12, 6	// tmp171,
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	str	xzr, [x6, 80]	//, MEM[(void *)stats_58(D)]
	ldr	w0, [x10]	//, bank_51(D)->num_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:249:     for (uint32_t base = 0; base < bank->num_points; base += chunk_points) {
	cmp	w7, w0	// base, prephitmp_91
	bcs	.L123	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:236: {
	stp	x29, x30, [sp, -32]!	//,,,
	add	x29, sp, 0	//,,
	stp	x19, x20, [sp, 16]	//,,
	.p2align 3
.L98:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:254:         stats->chunks++;
	ldr	x1, [x6]	// stats_58(D)->chunks, stats_58(D)->chunks
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:250:         uint32_t lim = base + chunk_points;
	add	w19, w7, w15	// base, base, chunk_points
	cmp	w19, w0	// base, prephitmp_91
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:254:         stats->chunks++;
	add	x1, x1, 1	// tmp140, stats_58(D)->chunks,
	str	x1, [x6]	// tmp140, stats_58(D)->chunks
	csel	w11, w19, w0, ls	// lim, base, prephitmp_91,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:256:         for (uint32_t i = base; i < lim; ++i) {
	cmp	w7, w11	// base, lim
	bcs	.L90	//,
	.p2align 3
.L97:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:257:             const float *p = bank->points + ((size_t)i * bank->dims);
	ldr	w8, [x10, 4]	//, bank_51(D)->dims
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:258:             uint8_t ty = detect_dirty_type(p, bank->dims, outlier_threshold);
	fmov	s0, s3	//, outlier_threshold
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:257:             const float *p = bank->points + ((size_t)i * bank->dims);
	ldr	x0, [x10, 16]	// bank_51(D)->points, bank_51(D)->points
	mov	w20, w7	// i, ivtmp.70
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:258:             uint8_t ty = detect_dirty_type(p, bank->dims, outlier_threshold);
	mov	w1, w8	//, _12
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:257:             const float *p = bank->points + ((size_t)i * bank->dims);
	ubfiz	x2, x8, 2, 32	// tmp143, _12,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:258:             uint8_t ty = detect_dirty_type(p, bank->dims, outlier_threshold);
	madd	x0, x2, x7, x0	//, tmp143, ivtmp.70, bank_51(D)->points
	bl	detect_dirty_type	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:260:             stats->scan_cycles += 24u + (uint64_t)bank->dims * 6u;
	ldr	x1, [x6, 8]	// stats_58(D)->scan_cycles, stats_58(D)->scan_cycles
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:261:             if (ty == DIRTY_TYPE_NONE) {
	ands	w2, w0, 255	// ty, tmp147
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:260:             stats->scan_cycles += 24u + (uint64_t)bank->dims * 6u;
	add	x1, x1, 24	// tmp148, stats_58(D)->scan_cycles,
	umaddl	x8, w8, w12, x1	// tmp150, _12, tmp171, tmp148
	str	x8, [x6, 8]	// tmp150, stats_58(D)->scan_cycles
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:261:             if (ty == DIRTY_TYPE_NONE) {
	beq	.L91	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:265:             if (ty & DIRTY_TYPE_NAN) {
	tbz	x2, 0, .L92	// ty,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:266:                 stats->dirty_nan++;
	ldr	x1, [x6, 32]	// stats_58(D)->dirty_nan, stats_58(D)->dirty_nan
	add	x1, x1, 1	// tmp155, stats_58(D)->dirty_nan,
	str	x1, [x6, 32]	// tmp155, stats_58(D)->dirty_nan
.L92:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:268:             if (ty & DIRTY_TYPE_NULL) {
	tbz	x2, 1, .L93	// ty,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:269:                 stats->dirty_null++;
	ldr	x1, [x6, 40]	// stats_58(D)->dirty_null, stats_58(D)->dirty_null
	add	x1, x1, 1	// tmp160, stats_58(D)->dirty_null,
	str	x1, [x6, 40]	// tmp160, stats_58(D)->dirty_null
.L93:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:271:             if (ty & DIRTY_TYPE_OUTLIER) {
	tbz	x2, 2, .L94	// ty,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:272:                 stats->dirty_outlier++;
	ldr	x1, [x6, 48]	// stats_58(D)->dirty_outlier, stats_58(D)->dirty_outlier
	add	x1, x1, 1	// tmp165, stats_58(D)->dirty_outlier,
	str	x1, [x6, 48]	// tmp165, stats_58(D)->dirty_outlier
.L94:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:275:             if (seen < max_dirty) {
	cmp	x13, x9	// _90, seen
	bls	.L95	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:276:                 dirty_indices[seen] = i;
	str	w20, [x14, x9, lsl 2]	// i, *_28
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:277:                 dirty_types[seen] = ty;
	strb	w0, [x4, x9]	// tmp147, *_29
.L96:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:281:             seen++;
	add	x9, x9, 1	// seen, seen,
.L91:
	add	x7, x7, 1	// ivtmp.70, ivtmp.70,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:256:         for (uint32_t i = base; i < lim; ++i) {
	cmp	w11, w7	// lim, ivtmp.70
	bhi	.L97	//,
	ldr	w0, [x10]	//, bank_51(D)->num_points
.L90:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:250:         uint32_t lim = base + chunk_points;
	uxtw	x7, w19	//, base
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:249:     for (uint32_t base = 0; base < bank->num_points; base += chunk_points) {
	cmp	w7, w0	// base, prephitmp_91
	bcc	.L98	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:286:     *dirty_count = (uint32_t)((seen > max_dirty) ? max_dirty : seen);
	cmp	x9, x13	// seen, _90
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:285:     stats->dirty_total = seen;
	str	x9, [x6, 24]	// seen, stats_58(D)->dirty_total
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:286:     *dirty_count = (uint32_t)((seen > max_dirty) ? max_dirty : seen);
	csel	w18, w18, w9, hi	// max_dirty, max_dirty, seen,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:287:     return 0;
	mov	w0, 0	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:288: }
	ldp	x19, x20, [sp, 16]	//,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:286:     *dirty_count = (uint32_t)((seen > max_dirty) ? max_dirty : seen);
	str	w18, [x5]	// max_dirty, *dirty_count_53(D)
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:288: }
	ldp	x29, x30, [sp], 32	//,,,
	ret
	.p2align 2
.L95:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:279:                 stats->dirty_truncated++;
	ldr	x0, [x6, 56]	// stats_58(D)->dirty_truncated, stats_58(D)->dirty_truncated
	add	x0, x0, 1	// tmp168, stats_58(D)->dirty_truncated,
	str	x0, [x6, 56]	// tmp168, stats_58(D)->dirty_truncated
	b	.L96	//
.L123:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:286:     *dirty_count = (uint32_t)((seen > max_dirty) ? max_dirty : seen);
	cmp	x9, x13	// seen, _90
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:285:     stats->dirty_total = seen;
	str	x9, [x6, 24]	// seen, stats_58(D)->dirty_total
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:286:     *dirty_count = (uint32_t)((seen > max_dirty) ? max_dirty : seen);
	csel	w18, w2, w9, hi	// max_dirty, max_dirty, seen,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:287:     return 0;
	mov	w0, 0	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:286:     *dirty_count = (uint32_t)((seen > max_dirty) ? max_dirty : seen);
	str	w18, [x5]	// max_dirty, *dirty_count_53(D)
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:288: }
	ret
.L103:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:240:         return -1;
	mov	w0, -1	// <retval>,
	ret
	.size	pim_scan_dirty, .-pim_scan_dirty
	.align	2
	.p2align 3,,7
	.global	pim_clean_points
	.type	pim_clean_points, %function
pim_clean_points:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:298:     if (!bank || !bank->points || !dirty_indices || !dirty_types || !stats) {
	cbz	x0, .L124	// bank,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:298:     if (!bank || !bank->points || !dirty_indices || !dirty_types || !stats) {
	ldr	x11, [x0, 16]	// _1, bank_52(D)->points
	cbz	x11, .L124	// _1,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:298:     if (!bank || !bank->points || !dirty_indices || !dirty_types || !stats) {
	cmp	x1, 0	// dirty_indices,
	ccmp	x2, 0, 4, ne	// dirty_types,,,
	ccmp	x4, 0, 4, ne	// stats,,,
	bne	.L177	//,
.L124:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:340: }
	ret
	.p2align 2
.L177:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:302:     for (uint32_t n = 0; n < dirty_count; ++n) {
	cbz	w3, .L124	// dirty_count,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:333:                 } else if (p[d] < -outlier_threshold) {
	fneg	s2, s0	// _33, outlier_threshold
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:307:         if (idx >= bank->num_points) {
	ldr	w12, [x0]	//, bank_52(D)->num_points
	mov	x7, 0	// ivtmp.90,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:337:             stats->pim_clean_cycles += 16u + (uint64_t)bank->dims * 6u;
	mov	w15, 6	// tmp239,
	mov	x13, 4	// tmp240,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:317:             stats->pim_clean_cycles += 14u + (uint64_t)bank->dims * 5u;
	mov	w14, 5	// tmp243,
	.p2align 3
.L142:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:303:         const uint32_t idx = dirty_indices[n];
	ldr	w5, [x1, x7, lsl 2]	//, MEM[base: dirty_indices_54(D), index: ivtmp.90_116, step: 4, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:307:         if (idx >= bank->num_points) {
	cmp	w12, w5	// _9, idx
	bls	.L127	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:311:         p = bank->points + ((size_t)idx * bank->dims);
	ldr	w8, [x0, 4]	//, bank_52(D)->dims
	uxtw	x6, w5	// idx, idx
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:304:         const uint8_t ty = dirty_types[n];
	ldrb	w9, [x2, x7]	// ty, MEM[base: dirty_types_55(D), index: ivtmp.90_116, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:311:         p = bank->points + ((size_t)idx * bank->dims);
	ubfiz	x5, x8, 2, 32	// tmp200, _11,,
	madd	x5, x5, x6, x11	// p, tmp200, idx, _1
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:313:         if (ty & DIRTY_TYPE_NULL) {
	tbnz	x9, 1, .L178	// ty,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:320:         if (ty & DIRTY_TYPE_NAN) {
	tbnz	x9, 0, .L179	// ty,,
.L131:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:329:         if (ty & DIRTY_TYPE_OUTLIER) {
	tbnz	x9, 2, .L180	// ty,,
.L127:
	add	x7, x7, 1	// ivtmp.90, ivtmp.90,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:302:     for (uint32_t n = 0; n < dirty_count; ++n) {
	cmp	w3, w7	// dirty_count, ivtmp.90
	bhi	.L142	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:340: }
	ret
	.p2align 2
.L178:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:314:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cbz	w8, .L129	// _11,
	sub	w10, w8, #1	// tmp206, _11,
	mov	x6, x5	// ivtmp.88, p
	add	x10, x13, x10, uxtw 2	// tmp207, tmp240, tmp206,
	add	x10, x10, x5	// _39, tmp207, p
	.p2align 3
.L130:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:315:                 p[d] = 0.0f;
	str	wzr, [x6], 4	//, MEM[base: _100, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:314:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cmp	x10, x6	// _39, ivtmp.88
	bne	.L130	//,
.L129:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:317:             stats->pim_clean_cycles += 14u + (uint64_t)bank->dims * 5u;
	ldr	x6, [x4, 16]	// stats_56(D)->pim_clean_cycles, stats_56(D)->pim_clean_cycles
	add	x6, x6, 14	// tmp210, stats_56(D)->pim_clean_cycles,
	umaddl	x6, w8, w14, x6	// tmp212, _11, tmp243, tmp210
	str	x6, [x4, 16]	// tmp212, stats_56(D)->pim_clean_cycles
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:320:         if (ty & DIRTY_TYPE_NAN) {
	tbz	x9, 0, .L131	// ty,,
.L179:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:321:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cbz	w8, .L132	// _11,
	sub	w10, w8, #1	// tmp217, _11,
	mov	x6, x5	// ivtmp.84, p
	add	x10, x13, x10, uxtw 2	// tmp218, tmp240, tmp217,
	add	x10, x10, x5	// _104, tmp218, p
	.p2align 3
.L134:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:322:                 if (isnan(p[d])) {
	ldr	s1, [x6]	// _68, MEM[base: _13, offset: 0B]
	fcmp	s1, s1	// _68, _68
	bvs	.L181	//,
.L133:
	add	x6, x6, 4	// ivtmp.84, ivtmp.84,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:321:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cmp	x6, x10	// ivtmp.84, _104
	bne	.L134	//,
.L132:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:326:             stats->pim_clean_cycles += 18u + (uint64_t)bank->dims * 8u;
	ldr	x6, [x4, 16]	// stats_56(D)->pim_clean_cycles, stats_56(D)->pim_clean_cycles
	add	x6, x6, 18	// tmp221, stats_56(D)->pim_clean_cycles,
	add	x6, x6, x8, uxtw 3	// tmp223, tmp221, _11,
	str	x6, [x4, 16]	// tmp223, stats_56(D)->pim_clean_cycles
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:329:         if (ty & DIRTY_TYPE_OUTLIER) {
	tbz	x9, 2, .L127	// ty,,
.L180:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:330:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cbz	w8, .L136	// _11,
	sub	w6, w8, #1	// tmp228, _11,
	add	x6, x13, x6, uxtw 2	// tmp229, tmp240, tmp228,
	add	x6, x5, x6	// _38, ivtmp.80, tmp229
	b	.L141	//
	.p2align 2
.L182:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:332:                     p[d] = outlier_threshold;
	str	s0, [x5]	// outlier_threshold, MEM[base: _89, offset: 0B]
.L139:
	add	x5, x5, 4	// ivtmp.80, ivtmp.80,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:330:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cmp	x6, x5	// _38, ivtmp.80
	beq	.L136	//,
.L141:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:331:                 if (p[d] > outlier_threshold) {
	ldr	s1, [x5]	// _32, MEM[base: _89, offset: 0B]
	fcmpe	s1, s0	// _32, outlier_threshold
	bgt	.L182	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:333:                 } else if (p[d] < -outlier_threshold) {
	fcmpe	s1, s2	// _32, _33
	bpl	.L139	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:334:                     p[d] = -outlier_threshold;
	str	s2, [x5]	// _33, MEM[base: _89, offset: 0B]
	add	x5, x5, 4	// ivtmp.80, ivtmp.80,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:330:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cmp	x6, x5	// _38, ivtmp.80
	bne	.L141	//,
.L136:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:337:             stats->pim_clean_cycles += 16u + (uint64_t)bank->dims * 6u;
	ldr	x5, [x4, 16]	// stats_56(D)->pim_clean_cycles, stats_56(D)->pim_clean_cycles
	add	x5, x5, 16	// tmp232, stats_56(D)->pim_clean_cycles,
	umaddl	x8, w8, w15, x5	// tmp234, _11, tmp239, tmp232
	str	x8, [x4, 16]	// tmp234, stats_56(D)->pim_clean_cycles
	b	.L127	//
	.p2align 2
.L181:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:323:                     p[d] = 0.0f;
	str	wzr, [x6]	//, MEM[base: _13, offset: 0B]
	b	.L133	//
	.size	pim_clean_points, .-pim_clean_points
	.align	2
	.p2align 3,,7
	.global	pim_count_dirty
	.type	pim_count_dirty, %function
pim_count_dirty:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:346:     if (!bank || !bank->points) {
	cbz	x0, .L187	// bank,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:346:     if (!bank || !bank->points) {
	ldr	x4, [x0, 16]	// _1, bank_15(D)->points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:347:         return 0;
	mov	w6, 0	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:346:     if (!bank || !bank->points) {
	cbz	x4, .L195	// _1,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:350:     for (uint32_t i = 0; i < bank->num_points; ++i) {
	ldr	w9, [x0]	//, bank_15(D)->num_points
	cbz	w9, .L195	// _24,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:343: {
	stp	x29, x30, [sp, -16]!	//,,,
	fmov	w8, s0	// outlier_threshold, outlier_threshold
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:350:     for (uint32_t i = 0; i < bank->num_points; ++i) {
	mov	w5, 0	// i,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:343: {
	add	x29, sp, 0	//,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:351:         const float *p = bank->points + ((size_t)i * bank->dims);
	ldr	w7, [x0, 4]	//, bank_15(D)->dims
	.p2align 3
.L186:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:350:     for (uint32_t i = 0; i < bank->num_points; ++i) {
	add	w5, w5, 1	// i, i,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:352:         if (detect_dirty_type(p, bank->dims, outlier_threshold) != DIRTY_TYPE_NONE) {
	fmov	s0, w8	//, outlier_threshold
	mov	x0, x4	//, ivtmp.99
	mov	w1, w7	//, _3
	bl	detect_dirty_type	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:353:             count++;
	tst	w0, 255	//
	cinc	w6, w6, ne	// <retval>, <retval>,
	add	x4, x4, x7, uxtw 2	// ivtmp.99, ivtmp.99, _3,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:350:     for (uint32_t i = 0; i < bank->num_points; ++i) {
	cmp	w5, w9	// i, _24
	bne	.L186	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:358: }
	mov	w0, w6	//, <retval>
	ldp	x29, x30, [sp], 16	//,,,
	ret
	.p2align 2
.L187:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:347:         return 0;
	mov	w6, 0	// <retval>,
.L195:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:358: }
	mov	w0, w6	//, <retval>
	ret
	.size	pim_count_dirty, .-pim_count_dirty
	.align	2
	.p2align 3,,7
	.global	pim_parse_imputation_policy
	.type	pim_parse_imputation_policy, %function
pim_parse_imputation_policy:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:362:     if (!name || !policy) {
	cmp	x0, 0	// name,
	ccmp	x1, 0, 4, ne	// policy,,,
	beq	.L201	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:361: {
	stp	x29, x30, [sp, -32]!	//,,,
	add	x29, sp, 0	//,,
	stp	x19, x20, [sp, 16]	//,,
	mov	x19, x1	// policy, policy
	mov	x20, x0	// name, name
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:365:     if (strcmp(name, "zero") == 0) {
	adrp	x1, .LC7	// tmp83,
	add	x1, x1, :lo12:.LC7	//, tmp83,
	bl	strcmp	//
	cbz	w0, .L207	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:369:     if (strcmp(name, "mean") == 0) {
	adrp	x1, .LC8	// tmp86,
	mov	x0, x20	//, name
	add	x1, x1, :lo12:.LC8	//, tmp86,
	bl	strcmp	//
	cbnz	w0, .L202	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:370:         *policy = PIM_IMPUTE_MEAN;
	mov	w1, 1	// tmp88,
	str	w1, [x19]	// tmp88, *policy_9(D)
.L198:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:374: }
	ldp	x19, x20, [sp, 16]	//,,
	ldp	x29, x30, [sp], 32	//,,,
	ret
	.p2align 2
.L207:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:366:         *policy = PIM_IMPUTE_ZERO;
	str	wzr, [x19]	//, *policy_9(D)
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:374: }
	ldp	x19, x20, [sp, 16]	//,,
	ldp	x29, x30, [sp], 32	//,,,
	ret
	.p2align 2
.L201:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:363:         return -1;
	mov	w0, -1	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:374: }
	ret
	.p2align 2
.L202:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:363:         return -1;
	mov	w0, -1	// <retval>,
	b	.L198	//
	.size	pim_parse_imputation_policy, .-pim_parse_imputation_policy
	.align	2
	.p2align 3,,7
	.global	pim_imputation_policy_name
	.type	pim_imputation_policy_name, %function
pim_imputation_policy_name:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:378:     return policy == PIM_IMPUTE_MEAN ? "mean" : "zero";
	cmp	w0, 1	// policy,
	adrp	x1, .LC7	// tmp76,
	adrp	x2, .LC8	// tmp75,
	add	x1, x1, :lo12:.LC7	// tmp78, tmp76,
	add	x2, x2, :lo12:.LC8	// tmp79, tmp75,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:379: }
	csel	x0, x2, x1, eq	//, tmp79, tmp78,
	ret
	.size	pim_imputation_policy_name, .-pim_imputation_policy_name
	.align	2
	.p2align 3,,7
	.global	pim_clean_oblivious
	.type	pim_clean_oblivious, %function
pim_clean_oblivious:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:390:     const uint64_t features = bank ? (uint64_t)bank->num_points * bank->dims : 0;
	cbz	x0, .L258	// bank,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:386: {
	stp	x29, x30, [sp, -96]!	//,,,
	add	x29, sp, 0	//,,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:390:     const uint64_t features = bank ? (uint64_t)bank->num_points * bank->dims : 0;
	ldp	w4, w3, [x0]	//,, bank_92(D)->num_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:392:     if (!bank || !bank->points || !stats || bank->num_points == 0 || bank->dims == 0 ||
	ldr	x5, [x0, 16]	// bank_92(D)->points, bank_92(D)->points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:386: {
	str	x25, [sp, 64]	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:392:     if (!bank || !bank->points || !stats || bank->num_points == 0 || bank->dims == 0 ||
	cmp	x5, 0	// bank_92(D)->points,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:390:     const uint64_t features = bank ? (uint64_t)bank->num_points * bank->dims : 0;
	umull	x25, w4, w3	// iftmp.8_94, _1, _3
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:392:     if (!bank || !bank->points || !stats || bank->num_points == 0 || bank->dims == 0 ||
	ccmp	x2, 0, 4, ne	// stats,,,
	beq	.L214	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:392:     if (!bank || !bank->points || !stats || bank->num_points == 0 || bank->dims == 0 ||
	cbz	w4, .L214	// _1,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:392:     if (!bank || !bank->points || !stats || bank->num_points == 0 || bank->dims == 0 ||
	cbz	w3, .L214	// _3,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:392:     if (!bank || !bank->points || !stats || bank->num_points == 0 || bank->dims == 0 ||
	fcmpe	s0, #0.0	// outlier_threshold
	bls	.L214	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:393:         outlier_threshold <= 0.0f || !isfinite(outlier_threshold) ||
	fabs	s2, s0	// tmp319, outlier_threshold
	mov	w3, 2139095039	// tmp422,
	fmov	s1, w3	// tmp320, tmp422
	fcmp	s2, s1	// tmp319, tmp320
	bhi	.L214	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:393:         outlier_threshold <= 0.0f || !isfinite(outlier_threshold) ||
	cmp	w1, 1	// policy,
	bhi	.L214	//,
	stp	x19, x20, [x29, 16]	//,,
	stp	x21, x22, [x29, 32]	//,,
	mov	x21, x2	// stats, stats
	str	x24, [x29, 56]	//,
	mov	w24, w1	// policy, policy
	str	x26, [x29, 72]	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:399:     means = (float *)calloc(bank->dims, sizeof(float));
	mov	x1, 4	//,
	str	d8, [x29, 80]	//,
	fmov	s8, s0	// outlier_threshold, outlier_threshold
// /usr/aarch64-linux-gnu/include/bits/string_fortified.h:71:   return __builtin___memset_chk (__dest, __ch, __len, __bos0 (__dest));
	stp	xzr, xzr, [x2]	// MEM[(void *)stats_95(D)]
	mov	x26, x0	// bank, bank
	stp	xzr, xzr, [x2, 16]	// MEM[(void *)stats_95(D)]
	stp	xzr, xzr, [x2, 32]	// MEM[(void *)stats_95(D)]
	stp	xzr, xzr, [x2, 48]	// MEM[(void *)stats_95(D)]
	stp	xzr, xzr, [x2, 64]	// MEM[(void *)stats_95(D)]
	str	xzr, [x2, 80]	//, MEM[(void *)stats_95(D)]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:399:     means = (float *)calloc(bank->dims, sizeof(float));
	ldr	w19, [x0, 4]	//, bank_92(D)->dims
	uxtw	x22, w19	// _10, _9
	mov	x0, x22	//, _10
	bl	calloc	//
	mov	x20, x0	// means,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:400:     if (!means) {
	cbz	x0, .L256	// means,
	str	x23, [x29, 48]	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:404:     if (policy == PIM_IMPUTE_MEAN) {
	cmp	w24, 1	// policy,
	beq	.L259	//,
	ldr	w9, [x26]	//, bank_92(D)->num_points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:389:     uint64_t *counts = NULL;
	mov	x22, 0	// counts,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:388:     double *sums = NULL;
	mov	x23, 0	// sums,
.L222:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:438:     for (uint32_t i = 0; i < bank->num_points; ++i) {
	cbz	w9, .L230	// pretmp_438,
.L262:
	ldp	x11, x2, [x21, 64]	// stats__records_read_lsm.105, pretmp_442, stats_95(D)->records_read
	sub	w13, w9, #1	// _428, pretmp_438,
	fneg	s0, s8	// _453, outlier_threshold
	ldr	x7, [x26, 16]	// ivtmp.129, bank_92(D)->points
	add	x10, x2, 2	// tmp371, pretmp_442,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mov	w1, 9200	// tmp372,
	sub	w14, w19, #1	// tmp420, _9,
	add	x2, x2, 1	// ivtmp.126, pretmp_442,
	add	x10, x10, x13	// _426, tmp371, _428
	movk	w1, 0xc974, lsl 16	// tmp372,,
	.p2align 3
.L228:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:440:         uint32_t null_mask = ct_mask_float_bits_eq(point[0], KMEANS_NULL_SENTINEL);
	ldr	s1, [x7]	// pretmp_449, MEM[base: point_130, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	fmov	w0, s1	// tmp431, pretmp_449
	eor	w0, w0, w1	// _172, tmp431, tmp372
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:16:     return 0u - ((value | (0u - value)) >> 31);
	neg	w8, w0	// tmp373, _172
	orr	w8, w8, w0	// tmp374, tmp373, _172
	asr	w8, w8, 31	// tmp375, tmp374,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mvn	w8, w8	// _178, tmp375
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:442:         for (uint32_t d = 0; d < bank->dims; ++d) {
	cbz	w19, .L225	// _9,
	mov	x4, 0	// ivtmp.112,
	ldr	x12, [x21, 80]	// stats__features_checked_lsm.107, stats_95(D)->features_checked
	b	.L227	//
	.p2align 2
.L260:
	ldr	s1, [x7, x4, lsl 2]	// pretmp_449, MEM[base: point_130, index: ivtmp.112_434, step: 4, offset: 0B]
.L227:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:30:     bits.f = value;
	fmov	w5, s1	// _180, pretmp_449
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:58:     uint32_t high = 0u - (uint32_t)(value > threshold);
	fcmgt	s2, s1, s8	// high, pretmp_449, outlier_threshold
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:59:     uint32_t low = 0u - (uint32_t)(value < -threshold);
	fcmgt	s1, s0, s1	// low, _453, pretmp_449
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mvn	w3, w5	// tmp376, _180
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:32:     mantissa = bits.u & 0x007fffffu;
	and	w15, w5, 8388607	// mantissa, _180,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	and	w6, w3, 2139095040	// _183, tmp376,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:69:     uint32_t invalid_mask = null_mask | ct_mask_is_nan(value) |
	orr	v1.8b, v2.8b, v1.8b	// tmp392, high, low
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:16:     return 0u - ((value | (0u - value)) >> 31);
	neg	w3, w6	// tmp377, _183
	neg	w0, w15	// tmp381, mantissa
	orr	w3, w3, w6	// tmp378, tmp377, _183
	orr	w0, w0, w15	// tmp382, tmp381, mantissa
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:52:     out.u = (t.u & mask) | (f.u & ~mask);
	ldr	w6, [x20, x4, lsl 2]	//, MEM[base: means_99, index: ivtmp.112_435, step: 4, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:16:     return 0u - ((value | (0u - value)) >> 31);
	asr	w3, w3, 31	// tmp379, tmp378,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:69:     uint32_t invalid_mask = null_mask | ct_mask_is_nan(value) |
	fmov	w15, s1	// tmp392, tmp392
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mvn	w3, w3	// tmp380, tmp379
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:52:     out.u = (t.u & mask) | (f.u & ~mask);
	eor	w6, w5, w6	// tmp394, _180, MEM[base: means_99, index: ivtmp.112_435, step: 4, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:33:     return ct_mask_eq_u32(exponent, 0x7f800000u) & ct_mask_nonzero_u32(mantissa);
	and	w0, w3, w0, asr 31	// tmp384, tmp380, tmp382,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:69:     uint32_t invalid_mask = null_mask | ct_mask_is_nan(value) |
	orr	w0, w0, w8	// tmp385, tmp384, _178
	orr	w0, w0, w15	// invalid_mask, tmp385, tmp392
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:52:     out.u = (t.u & mask) | (f.u & ~mask);
	and	w0, w0, w6	// tmp396, invalid_mask, tmp394
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:443:             point[d] = ct_repair_float(point[d], null_mask, means[d], outlier_threshold);
	eor	w0, w0, w5	// tmp433, tmp396, _180
	str	w0, [x7, x4, lsl 2]	// tmp398, MEM[base: point_130, index: ivtmp.112_435, step: 4, offset: 0B]
	add	x4, x4, 1	// ivtmp.112, ivtmp.112,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:442:         for (uint32_t d = 0; d < bank->dims; ++d) {
	cmp	w19, w4	// _9, ivtmp.112
	bhi	.L260	//,
	add	x0, x12, 1	// tmp401, stats__features_checked_lsm.107,
	add	x0, x14, x0	// tmp402, tmp420, tmp401
	str	x0, [x21, 80]	// tmp402, stats_95(D)->features_checked
	.p2align 3
.L225:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:446:         stats->records_written++;
	str	x2, [x21, 72]	// ivtmp.126, stats_95(D)->records_written
	add	x2, x2, 1	// ivtmp.126, ivtmp.126,
	add	x7, x7, x19, uxtw 2	// ivtmp.129, ivtmp.129, _9,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:438:     for (uint32_t i = 0; i < bank->num_points; ++i) {
	cmp	x2, x10	// ivtmp.126, _426
	bne	.L228	//,
	mov	w3, 12	// tmp406,
	mov	w1, 10	// tmp407,
	uxtw	x0, w9	// _455, pretmp_438
	add	x11, x11, 1	// tmp404, stats__records_read_lsm.105,
	umull	x3, w9, w3	// _457, pretmp_438, tmp406
	add	x13, x11, x13	// tmp405, tmp404, _428
	umull	x9, w9, w1	// _459, pretmp_438, tmp407
	str	x13, [x21, 64]	// tmp405, stats_95(D)->records_read
.L224:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:450:     stats->scan_cycles = features * (policy == PIM_IMPUTE_MEAN ? 18u : 8u) +
	cmp	w24, 1	// policy,
	mov	x2, 18	// tmp417,
	mov	x1, 8	// tmp416,
	csel	x1, x1, x2, ne	// iftmp.9_83, tmp416, tmp417,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:452:     stats->pim_clean_cycles = features * 12u + (uint64_t)bank->num_points * 10u;
	add	x2, x25, x25, lsl 1	// tmp412, iftmp.8_94, iftmp.8_94,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:450:     stats->scan_cycles = features * (policy == PIM_IMPUTE_MEAN ? 18u : 8u) +
	madd	x25, x1, x25, x3	// tmp409, iftmp.9_83, iftmp.8_94, _457
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:452:     stats->pim_clean_cycles = features * 12u + (uint64_t)bank->num_points * 10u;
	add	x9, x9, x2, lsl 2	// tmp414, _459, tmp412,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:450:     stats->scan_cycles = features * (policy == PIM_IMPUTE_MEAN ? 18u : 8u) +
	stp	x0, x25, [x21]	// _455, tmp409, stats_95(D)->chunks
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:454:     free(means);
	mov	x0, x20	//, means
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:452:     stats->pim_clean_cycles = features * 12u + (uint64_t)bank->num_points * 10u;
	str	x9, [x21, 16]	// tmp414, stats_95(D)->pim_clean_cycles
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:454:     free(means);
	bl	free	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:455:     free(sums);
	mov	x0, x23	//, sums
	bl	free	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:456:     free(counts);
	mov	x0, x22	//, counts
	bl	free	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:457:     return 0;
	mov	w0, 0	// <retval>,
.L257:
	ldp	x19, x20, [x29, 16]	//,,
	ldp	x21, x22, [x29, 32]	//,,
	ldp	x23, x24, [x29, 48]	//,,
	ldr	x26, [x29, 72]	//,
	ldr	d8, [x29, 80]	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:458: }
	ldr	x25, [sp, 64]	//,
	ldp	x29, x30, [sp], 96	//,,,
	ret
.L256:
	ldp	x19, x20, [x29, 16]	//,,
	ldp	x21, x22, [x29, 32]	//,,
	ldr	x24, [x29, 56]	//,
	ldr	x26, [x29, 72]	//,
	ldr	d8, [x29, 80]	//,
.L214:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:395:         return -1;
	mov	w0, -1	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:458: }
	ldr	x25, [sp, 64]	//,
	ldp	x29, x30, [sp], 96	//,,,
	ret
.L259:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:405:         sums = (double *)calloc(bank->dims, sizeof(double));
	mov	x1, 8	//,
	mov	x0, x22	//, _10
	bl	calloc	//
	mov	x23, x0	// sums,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:406:         counts = (uint64_t *)calloc(bank->dims, sizeof(uint64_t));
	mov	x1, 8	//,
	mov	x0, x22	//, _10
	bl	calloc	//
	mov	x22, x0	// counts,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:407:         if (!sums || !counts) {
	cmp	x23, 0	// sums,
	ccmp	x0, 0, 4, ne	// counts,,,
	beq	.L216	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:415:         for (uint32_t i = 0; i < bank->num_points; ++i) {
	ldr	w9, [x26]	//, bank_92(D)->num_points
	cbz	w9, .L218	// pretmp_438,
	fneg	s3, s8	// _474, outlier_threshold
	ldr	x6, [x26, 16]	// ivtmp.159, bank_92(D)->points
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mov	w8, 9200	// tmp327,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:415:         for (uint32_t i = 0; i < bank->num_points; ++i) {
	mov	w7, 0	// i,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	movk	w8, 0xc974, lsl 16	// tmp327,,
	.p2align 3
.L221:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:417:             uint32_t null_mask = ct_mask_float_bits_eq(point[0], KMEANS_NULL_SENTINEL);
	ldr	s0, [x6]	// pretmp_468, MEM[base: point_111, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	fmov	w0, s0	// tmp427, pretmp_468
	eor	w0, w0, w8	// _115, tmp427, tmp327
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:16:     return 0u - ((value | (0u - value)) >> 31);
	neg	w5, w0	// tmp328, _115
	orr	w5, w5, w0	// tmp329, tmp328, _115
	asr	w5, w5, 31	// tmp330, tmp329,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mvn	w5, w5	// _141, tmp330
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:418:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cbz	w19, .L219	// _9,
	mov	x2, 0	// ivtmp.140,
	b	.L220	//
	.p2align 2
.L261:
	ldr	s0, [x6, x2, lsl 2]	// pretmp_468, MEM[base: point_111, index: ivtmp.140_421, step: 4, offset: 0B]
.L220:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:30:     bits.f = value;
	fmov	w3, s0	// _152, pretmp_468
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:58:     uint32_t high = 0u - (uint32_t)(value > threshold);
	fcmgt	s1, s0, s8	// high, pretmp_468, outlier_threshold
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:59:     uint32_t low = 0u - (uint32_t)(value < -threshold);
	fcmgt	s0, s3, s0	// low, _474, pretmp_468
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:423:                 sums[d] += (double)contribution;
	ldr	d2, [x23, x2, lsl 3]	// MEM[base: sums_101, index: ivtmp.140_422, step: 8, offset: 0B], MEM[base: sums_101, index: ivtmp.140_422, step: 8, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mvn	w4, w3	// tmp331, _152
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:32:     mantissa = bits.u & 0x007fffffu;
	and	w10, w3, 8388607	// mantissa, _152,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	and	w0, w4, 2139095040	// _155, tmp331,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:419:                 uint32_t invalid_mask = null_mask | ct_mask_is_nan(point[d]) |
	orr	v0.8b, v1.8b, v0.8b	// tmp347, high, low
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:16:     return 0u - ((value | (0u - value)) >> 31);
	neg	w4, w0	// tmp332, _155
	neg	w1, w10	// tmp336, mantissa
	orr	w4, w4, w0	// tmp333, tmp332, _155
	orr	w1, w1, w10	// tmp337, tmp336, mantissa
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:424:                 counts[d] += (uint64_t)(valid_mask & 1u);
	ldr	x0, [x22, x2, lsl 3]	// MEM[base: counts_103, index: ivtmp.140_422, step: 8, offset: 0B], MEM[base: counts_103, index: ivtmp.140_422, step: 8, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:419:                 uint32_t invalid_mask = null_mask | ct_mask_is_nan(point[d]) |
	fmov	w10, s0	// tmp347, tmp347
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:16:     return 0u - ((value | (0u - value)) >> 31);
	asr	w4, w4, 31	// tmp334, tmp333,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:21:     return ~ct_mask_nonzero_u32(lhs ^ rhs);
	mvn	w4, w4	// tmp335, tmp334
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:33:     return ct_mask_eq_u32(exponent, 0x7f800000u) & ct_mask_nonzero_u32(mantissa);
	and	w1, w4, w1, asr 31	// tmp339, tmp335, tmp337,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:419:                 uint32_t invalid_mask = null_mask | ct_mask_is_nan(point[d]) |
	orr	w1, w1, w5	// tmp340, tmp339, _141
	orr	w1, w1, w10	// invalid_mask, tmp340, tmp347
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:421:                 uint32_t valid_mask = ~invalid_mask;
	mvn	w1, w1	// valid_mask, invalid_mask
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:53:     return out.f;
	and	w3, w1, w3	// tmp349, valid_mask, _152
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:423:                 sums[d] += (double)contribution;
	fmov	s0, w3	// tmp429, tmp349
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:424:                 counts[d] += (uint64_t)(valid_mask & 1u);
	and	w1, w1, 1	//, valid_mask,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:423:                 sums[d] += (double)contribution;
	fcvt	d1, s0	// tmp350, tmp429
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:424:                 counts[d] += (uint64_t)(valid_mask & 1u);
	add	x1, x0, x1	// tmp355, MEM[base: counts_103, index: ivtmp.140_422, step: 8, offset: 0B], tmp354
	str	x1, [x22, x2, lsl 3]	// tmp355, MEM[base: counts_103, index: ivtmp.140_422, step: 8, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:423:                 sums[d] += (double)contribution;
	fadd	d1, d2, d1	// tmp351, MEM[base: sums_101, index: ivtmp.140_422, step: 8, offset: 0B], tmp350
	str	d1, [x23, x2, lsl 3]	// tmp351, MEM[base: sums_101, index: ivtmp.140_422, step: 8, offset: 0B]
	add	x2, x2, 1	// ivtmp.140, ivtmp.140,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:418:             for (uint32_t d = 0; d < bank->dims; ++d) {
	cmp	w19, w2	// _9, ivtmp.140
	bhi	.L261	//,
.L219:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:415:         for (uint32_t i = 0; i < bank->num_points; ++i) {
	add	w7, w7, 1	// i, i,
	add	x6, x6, x19, uxtw 2	// ivtmp.159, ivtmp.159, _9,
	cmp	w7, w9	// i, pretmp_438
	bne	.L221	//,
.L218:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:428:         for (uint32_t d = 0; d < bank->dims; ++d) {
	cbz	w19, .L222	// _9,
	mov	x1, 0	// ivtmp.132,
	.p2align 3
.L223:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:429:             uint64_t count = counts[d];
	ldr	x2, [x22, x1, lsl 3]	// count, MEM[base: counts_103, index: ivtmp.132_425, step: 8, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:431:             float candidate = (float)(sums[d] / (double)safe_count);
	ldr	d0, [x23, x1, lsl 3]	// MEM[base: sums_101, index: ivtmp.132_425, step: 8, offset: 0B], MEM[base: sums_101, index: ivtmp.132_425, step: 8, offset: 0B]
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:430:             uint64_t safe_count = count + (uint64_t)(count == 0u);
	cmp	x2, 0	// count,
	cinc	x0, x2, eq	// safe_count, count,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:431:             float candidate = (float)(sums[d] / (double)safe_count);
	ucvtf	d1, x0	// tmp361, safe_count
	fdiv	d0, d0, d1	// tmp362, MEM[base: sums_101, index: ivtmp.132_425, step: 8, offset: 0B], tmp361
	fcvt	s0, d0	// candidate, tmp362
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:433:             means[d] = ct_select_float(has_value, candidate, 0.0f);
	fmov	w0, s0	// tmp430, candidate
	csel	w0, w0, wzr, ne	// tmp369, tmp430,,
	str	w0, [x20, x1, lsl 2]	// tmp369, MEM[base: means_99, index: ivtmp.132_425, step: 4, offset: 0B]
	add	x1, x1, 1	// ivtmp.132, ivtmp.132,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:428:         for (uint32_t d = 0; d < bank->dims; ++d) {
	cmp	w19, w1	// _9, ivtmp.132
	bhi	.L223	//,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:438:     for (uint32_t i = 0; i < bank->num_points; ++i) {
	cbnz	w9, .L262	// pretmp_438,
.L230:
	mov	x9, 0	// _459,
	mov	x3, 0	// _457,
	mov	x0, 0	// _455,
	b	.L224	//
	.p2align 2
.L258:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:395:         return -1;
	mov	w0, -1	// <retval>,
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:458: }
	ret
.L216:
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:408:             free(means);
	mov	x0, x20	//, means
	bl	free	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:409:             free(sums);
	mov	x0, x23	//, sums
	bl	free	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:410:             free(counts);
	mov	x0, x22	//, counts
	bl	free	//
// IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c:411:             return -1;
	mov	w0, -1	// <retval>,
	b	.L257	//
	.size	pim_clean_oblivious, .-pim_clean_oblivious
	.section	.rodata.str1.8,"aMS",@progbits,1
	.align	3
.LC0:
	.string	"rb"
	.zero	5
.LC1:
	.string	"pim_bank_load_dataset: failed to open %s: %s\n"
	.zero	2
.LC2:
	.string	"pim_bank_load_dataset: failed to read header from %s\n"
	.zero	2
.LC3:
	.string	"pim_bank_load_dataset: invalid dataset header (magic=0x%x version=%u points=%u dims=%u)\n"
	.zero	7
.LC4:
	.string	"pim_bank_load_dataset: out of memory\n"
	.zero	2
.LC5:
	.string	"pim_bank_load_dataset: failed to read dataset body\n"
	.zero	4
.LC6:
	.string	"pim_bank_load_dataset: trailing bytes in %s\n"
	.zero	3
.LC7:
	.string	"zero"
	.zero	3
.LC8:
	.string	"mean"
	.ident	"GCC: (Ubuntu/Linaro 7.5.0-3ubuntu1~18.04) 7.5.0"
	.section	.note.GNU-stack,"",@progbits
