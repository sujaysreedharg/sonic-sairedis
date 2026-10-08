# Public syncd objects for a private native vendor link

The first actual public build failed during dependency installation; no production object or private syncd link was accepted.
Its authenticated evidence is retained at `reports/sonic-syncd-cloud/run-37708720935` in the private project.
The second actual seven-package run `37709724075` failed at configure's required SAI API probe and is also preserved separately.
The public library's actual dynamic symbol table contains that defined global, while its swsscommon dependency names three SONiC libnl libraries absent from the seven-package inputs.
The corrected ten-package candidate remains unexecuted until a new public run completes.
It avoids uploading the private ASIC RTL, vendor SAI or MRC software.
The final private link and SONiC startup must run separately in the Linux guest.

## Exact target and measured interface

The source is [sonic-sairedis commit 3ee202d5](https://github.com/sonic-net/sonic-sairedis/tree/3ee202d5191838f9da4bef25ce0088d36c323fe2), with its exact SAI 1.18.1 submodule.
The [production Makefile](https://github.com/sonic-net/sonic-sairedis/blob/3ee202d5191838f9da4bef25ce0088d36c323fe2/syncd/Makefile.am) defines the vendor target and archives used here.
Normal make rules compile 44 distinct libSyncd units, 22 libSaiRedis units and main.
The upstream duplicated VidManager source-list entry is preserved; archive membership must contain each distinct unit exactly once.
The workflow does not build the top-level virtual-switch, Python binding, test or auxiliary-program targets.
It uses the normal warning flags, including upstream `-Werror`, with no added suppressions.

The actual local Linux vendor ELF was inspected for its exported global APIs and queried for SAI version 1.18.1.
It exports the required version function and the optional bulk-clear, bulk-get and statistics-capability globals.
It lacks the optional TAM telemetry global.
`vendor-interface-profile.json` records the measured ELF hash, byte count, API result and exact selection.
No private implementation bytes or private source paths are included.
The private final link must recheck this profile against its actual library; a changed profile requires a new object build.

Upstream [configure](https://github.com/sonic-net/sonic-sairedis/blob/3ee202d5191838f9da4bef25ce0088d36c323fe2/configure.ac) normally probes the SAI globals.
The public job uses the authenticated real Redis SAI as its configure library and executes its genuine version check.
Only `ac_cv_func_sai_tam_telemetry_get_data=no` is deliberately selected from the measured target's absent optional capability.
The three positive optional checks remain actual compile/link probes.
This visible negative cache selection is not evidence that the public library is the private vendor.
The generated config must agree exactly with the target profile, and the compiled VendorSai references must contain the selected globals and exclude TAM.
VendorSai's existing unsupported-feature path is used; no implementation stub is added.

## Cloud commands and public inputs

The workflow uses the same digest-pinned official Linux ARM64 Bookworm image as the validated SWSS build.
It authenticates ten official SONiC runtime/development archives to their recorded Azure source, artifact and package identities.
Their selected payloads total 3,160,972 compressed bytes.
The retained actual failure identified `libswsscommon`'s missing `libyang3 >= 3.12.2` runtime dependency.
The corrected manifest adds the exact `libyang3_3.12.2-1_arm64.deb` from the previously authenticated official common-libs build, rather than substituting Debian Trixie libraries.
It also adds the exact SONiC base, netfilter and route libnl runtime packages used by the accepted swsscommon ELF.
Before configure, actual `ldd -r` on the public Redis SAI must show no missing libraries or undefined symbols, and its log is retained on failure.
The EXIT handler preserves `config.log` even when configure fails; the original required API and executed-version probes remain unchanged.
Individual bounded file requests avoid downloading the full upstream artifacts.
Signed Debian APT supplies ordinary development tools; their executed installed identities are recorded.
These package totals exclude the build image, system packages and expanded build workspace.

After source/submodule/header verification and genuine configure, the actual commands are:

```sh
make -C SAI/meta saimetadata.c
make -C lib -j2 libSaiRedis.a
make -C syncd -j2 libSyncd.a syncd-main.o
make -C syncd -n syncd
make -C syncd -j2 syncd
```

The exact SAI metadata generator runs through its normal [target](https://github.com/opencomputeproject/SAI/blob/c67f1152309ca08a94de0be8634a733c5cb25c35/meta/Makefile).
Installed matching metadata libraries supply the actual public link dependencies.
The complete production syncd target is genuinely linked to public Redis SAI and checked by Linux `ldd -r` and `readelf`.
The public validation ELF must have no unresolved symbols, virtual-switch mapping or embedded search path.
It is not exported as a usable MiniSwitch syncd.

The isolated local worktree is `/Users/sujay/Projects/mini_switch_sonic/sonic-sairedis-object-validation` on branch `mini-switch/syncd-public-objects-20261007`.
Its base is the pinned upstream commit and its only candidate changes are this directory under `mini-switch-syncd-ci/` plus `.github/workflows/mini-switch-syncd-objects.yml`.
The parent task reviews the concrete candidate before publication or dispatch.

## Export and local-link gate

Only copies of `libSyncd.a`, `libSaiRedis.a` and `syncd-main.o` are exported.
GNU [`strip --strip-debug`](https://sourceware.org/binutils/docs/binutils/strip.html) removes debug material while retaining link symbols.
The exporter independently compares all defined/undefined symbols, allocated-section content and normalized nondebug relocations before and after stripping.
Every archive member must be a genuine AArch64 relocatable, with exact normal production membership.
Original artifacts remain unchanged and their actual hashes are checked again.
The bundle includes source/header/package pins, generated config, source licenses, actual diagnostics and hashes.
The selected relocatables are bounded at 64 MiB and the compressed artifact at 32 MiB; actual sizes remain to be measured.

`link-command.json` preserves the actual emitted normal upstream link tokens and a structured portable template.
Its only path substitutions select the exported artifacts, local output, local private vendor-library directory and matching installed metadata directory.
The template retains the real `-rdynamic`, metadata, swsscommon, hiredis, ZeroMQ, zlib and vendor `-lsai` arguments.
Do not execute it through an interpolated shell string.
Resolve its placeholders and run its argument array with the native Linux C++ linker.

Before local linking, authenticate the exact successful GitHub run/checkout/artifact, verify every bundle hash/member and recheck the private library's profile.
Install the actual matching runtime/development closure and preserve its package identities.
Require the private native link to succeed normally, then inspect its actual AArch64 ELF and invoke `ldd -r`.
The syncd process must load the private `libsai.so`, while orchagent must load public `libsairedis.so` in a separately scoped environment.
Neither link success nor these object receipts establish SONiC startup, SAI backend traffic, physical Ethernet operation or fabrication fit.

## Executed preparation checks

Nine native parser/rejection tests passed on the Mac, together with Bash syntax and Python/JSON parsing.
The actual pinned upstream source lists resolve to the required 44/22 units.
The recorded private ELF hash and optional export profile were independently checked again from its actual dynamic symbol table without loading or uploading it.
A tiny actual Mac clang cross-compiled AArch64 relocatable retained identical code/data and normalized nondebug-relocation fingerprints across actual LLVM debug-only stripping.
Changing a real code byte changed the fingerprint.
That is parser preparation evidence, not Linux execution or a GNU-strip production result.
The preparation checks did not execute a private native link, SONiC service or guest mutation.
The parent subsequently published the isolated public branch and executed run `37708720935`; its dependency failure is preserved separately from these preparation results.

The next parent-owned action is to review and publish the ten-package closure and diagnostic correction, then execute a new real workflow.
