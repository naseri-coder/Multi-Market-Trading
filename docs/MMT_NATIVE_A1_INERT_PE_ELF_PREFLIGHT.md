# NATIVE-A1 — bounded native PE/ELF file preflight (never execute)

**Status: NONPRODUCTION FILE-STRUCTURE INSPECTION ONLY. No native sandbox or safe-execution approval.**

The existing universal artifact intake recognizes DLL, EXE and SO file
extensions and checks a few magic bytes. NATIVE-A1 adds a second and more
constrained acceptance contract without modifying the original intake
or any runtime dispatch. The result is ALWAYS UNTRUSTED.

## Scope

- DLL: Windows PE x86, x86-64 or ARM64, with file-header DLL characteristic.
- EXE: Windows PE x86, x86-64 or ARM64, with executable-image characteristic
  and without the DLL characteristic.
- SO: Linux ELF little-endian ET_DYN for x86, x86-64 or AArch64.
  **ET_DYN may also be a PIE executable**, so this alone cannot prove
  that an artifact is truly a shared library.

The parser uses only Python byte slicing, bounded integer reads and SHA256.
It does NOT invoke ctypes, dlopen, importlib extension loading, subprocess,
Docker, Wine, a Windows executable, a system ELF loader or antivirus engine.
No native instructions are executed or mapped.

### PE static-header checks

Checks DOS and PE signature offset, COFF machine, declared sections,
optional-header magic vs machine bitness, DLL/executable characteristics,
header/image sizes, basic alignments, section table and file-backed section
ranges, and overlapping raw file sections. It does NOT prove PE
completeness, imports, relocations, digital Authenticode signature,
certificate chain, code integrity, ABI, symbol exports or malicious behavior.

### ELF static-header checks

Checks ELF identification, little endian, class vs selected machine,
ET_DYN type, version, ELF header size, bounded program/section header tables
when specified, segment file bounds and presence of at least one PT_LOAD
segment. This is structural plausibility only. It does NOT certify dynamic
loader behavior, needed libraries, symbol versions, RPATH/RUNPATH, RELRO,
PIE-vs-library distinction, signatures, sandbox escape resistance or safety.

### Exact admission boundaries

- Require MMT_NONPRODUCTION=1 and explicit operator_ack=True.
- MMT_PRODUCTION=1 denies admission.
- Require a separately operator-reviewed exact lowercase SHA256 digest.
- For a local artifact, require an absolute path, non-symlink ordinary file,
  single filesystem hard link, maximum size 8MiB, stable inode/size/mtime/
  ctime while reading. The path and source never leave this process.
- For in-memory bytes, require bounded 1..8MiB input and a safe filename
  whose suffix is one of DLL, SO, EXE.
- Fail closed on malformed headers, wrong bitness, invalid offsets, file
  identity drift, disallowed extensions, oversized input and digest mismatch.
- No source byte contents or credentials included in result objects.
- The report includes format, file-type claim, architecture, endianness,
  declared bitness, count of file-backed regions, digest and size.
- Every publisher, code-signature, complete-format-validation, dependency,
  malware-safety, independent-host, PAPER strategy and execution/Telegram/
  broker/Worker authorization field remains FALSE.

A SHA256 match proves only equality to the caller-supplied digest; a
malicious file and malicious digest may both agree. A structurally plausible
binary can still contain malicious code or trigger vulnerabilities in a
real operating-system loader. Do not load it in the bot process or on
any other operational host. A Python header inspector cannot prove
sandbox security or prevent all filesystem races with a privileged attacker.

## Acceptance tests (offline GitHub CI)

Fixtures synthesize minimal PE32/PE32+, x86/x86-64/ARM64 binaries and
ELF32/ELF64 x86/x86-64/AArch64 headers solely as bytes. They test type
and machine disagreement, wrong bitness/endian, section and segment
overflows/overlaps, absent loads, header truncation, bad filename/digest,
symlink/hardlink denial, production/operator restrictions and A6 hard stop.
The original universal artifact recognition tests are retained.

No genuine signed vendor DLL/SO/EXE has been supplied or validated.
No actual Windows guest, Linux disposable host or native execution takes
place in CI. This is deliberately NOT a milestone for execution isolation.

## Remaining real-world blockers (require separate authorization)

1. Independent signed publisher provenance and artifact-custody evidence.
2. Exact expected OS loader version, dependencies, ABI, symbols and code
   signing policy, verified on an expendable and independently controlled host.
3. Adversarial native sandbox containment tests with no sensitive credentials,
   no network and kernel-level isolation, with external observed evidence.
4. Exact Core API adapter and deterministic native results, including
   resource exhaustion, crashes, forbidden syscalls and restart recovery.
5. Separate approved transition to a native worker execution policy.
   RUNTIME-A6 presently and unconditionally denies Worker launch.

**Verdict: NATIVE_A1_STATIC_BINARY_HEADER_REVIEW_ONLY_NATIVE_EXECUTION_BLOCKED.**
