#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ci_root=$(cd "$(dirname "$0")" && pwd)
source_root=$(cd "$ci_root/.." && pwd)
output_dir="$source_root/mini-switch-syncd-out"
mkdir -p "$output_dir"
finish() {
    build_exit=$?
    # Preserve actual configure diagnostics even when configure terminates early.
    if [ -f "$source_root/config.log" ]; then
        cp "$source_root/config.log" "$output_dir/configure-detail.log" || build_exit=1
    fi
    if [ -f "$source_root/config.h" ]; then
        cp "$source_root/config.h" "$output_dir/config.h.log" || build_exit=1
    fi
    if ! python3 -B "$ci_root/build_receipt.py" --source "$source_root" --ci "$ci_root" \
        --output "$output_dir" --exit-code "$build_exit"; then
        if [ "$build_exit" -eq 0 ]; then build_exit=1; fi
    fi
    exit "$build_exit"
}
trap finish EXIT
[ "$(uname -s)" = Linux ]
[ "$(uname -m)" = aarch64 ]
[ "$(dpkg --print-architecture)" = arm64 ]
export LC_ALL=C
# Select the ordinary platform-independent vendor target explicitly.
unset ENABLESYNCD CONFIGURED_PLATFORM CROSS_BUILD_ENVIRON CONFIGURED_ARCH
git config --global --add safe.directory "$source_root"
git config --global --add safe.directory "$source_root/SAI"
python3 -B "$ci_root/test_export_objects.py" > "$output_dir/policy-unit.log" 2>&1
python3 -B "$ci_root/export_objects.py" --source "$source_root" --ci "$ci_root" \
    --output "$output_dir" --verify-inputs-only > "$output_dir/source-inputs.log" 2>&1
df -h > "$output_dir/storage-before.log"
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 0755 /usr/sbin/policy-rc.d
export DEBIAN_FRONTEND=noninteractive
dpkg-query -W libboost1.83-dev libboost-serialization1.83-dev > "$output_dir/image-boost-version.txt"
apt-get update > "$output_dir/apt-update.log" 2>&1
apt-get install -y --no-install-recommends \
    libhiredis-dev libzmq3-dev zlib1g-dev nlohmann-json3-dev \
    autoconf automake libtool autoconf-archive python3-dev swig \
    doxygen graphviz libxml-simple-perl libxml2-dev > "$output_dir/apt-tools.log" 2>&1
python3 -B "$ci_root/fetch_dependencies.py" "$ci_root/dependencies.json" "$output_dir" \
    > "$output_dir/dependency-download.log" 2>&1
apt-get install -y --no-install-recommends "$output_dir"/*.deb > "$output_dir/dependency-install.log" 2>&1
dpkg-query -W > "$output_dir/installed-package-versions.txt"
dpkg-query -W '-f=${Package}\t${Version}\t${Architecture}\n' > "$output_dir/installed-package-identities.tsv"
ldconfig
ci_library_dir="$source_root/mini-switch-syncd-libraries"
mkdir -p "$ci_library_dir"
ln -s /usr/lib/aarch64-linux-gnu/libsairedis.so "$ci_library_dir/libsai.so"
export LD_LIBRARY_PATH="$ci_library_dir"
ldd -r /usr/lib/aarch64-linux-gnu/libsairedis.so > "$output_dir/preconfigure-public-loader.log" 2>&1
python3 - "$output_dir/preconfigure-public-loader.log" <<'PY'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text()
if any(term in text for term in ("not found", "undefined symbol:", "libsaivs")):
    raise SystemExit("Actual public configure library has an unresolved loader closure; see preserved preconfigure-public-loader.log")
if "libswsscommon.so" not in text or "ld-linux-aarch64.so.1" not in text:
    raise SystemExit("Actual public configure library lacks its expected native loader dependency")
PY
c++ --version > "$output_dir/compiler-version.txt"
cd "$source_root"
./autogen.sh > "$output_dir/autogen.log" 2>&1
# Only an absent optional target capability is pinned negative.
# All positive probes and the executed version check use the actual public Redis SAI.
ac_cv_func_sai_tam_telemetry_get_data=no LDFLAGS="-L$ci_library_dir" \
    ./configure --disable-python2 > "$output_dir/configure.log" 2>&1
cp config.h "$output_dir/config.h.log"
cp config.log "$output_dir/configure-detail.log"
make -C SAI/meta saimetadata.c > "$output_dir/metadata-generator.log" 2>&1
make -C lib -j2 libSaiRedis.a > "$output_dir/redis-objects.log" 2>&1
make -C syncd -j2 libSyncd.a syncd-main.o > "$output_dir/syncd-objects.log" 2>&1
# Record the normal upstream link expansion before the production target exists.
make -C syncd -n syncd > "$output_dir/upstream-link-dry-run.log" 2>&1
# This validates the full production link against public Redis SAI only.
# Its binary is deliberately excluded from the object artifact.
make -C syncd -j2 syncd > "$output_dir/public-syncd-link.log" 2>&1
python3 -B "$ci_root/export_objects.py" --source "$source_root" --ci "$ci_root" \
    --output "$output_dir" > "$output_dir/object-export-command.log" 2>&1
df -h > "$output_dir/storage-after.log"
find "$output_dir" -maxdepth 1 -type f -name '*.deb' -delete
