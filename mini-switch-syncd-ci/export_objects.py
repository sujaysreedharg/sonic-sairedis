#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Export real public production relocatables; private vendor linking stays local."""
import argparse
import ctypes
import gzip
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import shutil
import struct
import subprocess
import tarfile

MAX_EXPORT = 64 * 1024**2
MAX_ARCHIVE = 32 * 1024**2


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command, log=None, binary=False):
    result = subprocess.run(command, capture_output=True, text=not binary, check=False)
    if log:
        log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Command failed: " + shlex.join(map(str, command)))
    return result.stdout


def source_list(text, variable):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^" + re.escape(variable) + r"\s*=\s*(.*)", line)
        if match:
            value = match.group(1)
            while value.rstrip().endswith("\\"):
                index += 1
                if index >= len(lines):
                    raise RuntimeError("Truncated source-list continuation")
                value = value.rstrip()[:-1] + " " + lines[index]
            return list(dict.fromkeys(value.split()))
    raise RuntimeError("Missing normal upstream source list: " + variable)


def elf_header(data, relocatable=False):
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise RuntimeError("Not an ELF64 little-endian version-one object")
    kind, machine = struct.unpack_from("<HH", data, 16)
    if machine != 183 or kind not in ((1,) if relocatable else (2, 3)):
        raise RuntimeError("Unexpected ELF kind or machine")
    return {"elf_type": kind, "elf_machine": machine}


def link_content(data):
    """Measure allocated sections and named relocations outside debug targets."""
    elf_header(data, relocatable=True)
    offset = struct.unpack_from("<Q", data, 40)[0]
    width, count, string_index = struct.unpack_from("<HHH", data, 58)
    if width != 64 or not count or string_index >= count or offset + width * count > len(data):
        raise RuntimeError("Invalid relocatable section table")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, offset + index * width) for index in range(count)]
    strings = sections[string_index]
    names = data[strings[4]:strings[4] + strings[5]]

    def string(table, position):
        end = table.find(b"\0", position)
        if position >= len(table) or end < 0:
            raise RuntimeError("Invalid ELF string reference")
        return table[position:end].decode("utf-8")

    section_names = [string(names, section[0]) for section in sections]
    allocated = []
    relocations = []
    for index, section in enumerate(sections):
        name, kind, flags, address, start, size, link, target, alignment, entry_size = section
        if kind != 8 and start + size > len(data):
            raise RuntimeError("Invalid ELF section bounds")
        if flags & 2:
            payload = b"" if kind == 8 else data[start:start + size]
            allocated.append((section_names[index], kind, flags, size, alignment, hashlib.sha256(payload).hexdigest()))
        if kind not in (4, 9):
            continue
        if target >= count or link >= count:
            raise RuntimeError("Invalid relocation section links")
        if section_names[target].startswith((".debug", ".zdebug")):
            continue
        symbols = sections[link]
        if symbols[1] != 2 or symbols[9] != 24 or symbols[6] >= count:
            raise RuntimeError("Invalid relocation symbol table")
        table = sections[symbols[6]]
        symbol_names = data[table[4]:table[4] + table[5]]
        expected_size = 24 if kind == 4 else 16
        if entry_size != expected_size or size % entry_size:
            raise RuntimeError("Invalid relocation entry size")
        for at in range(start, start + size, entry_size):
            location, info = struct.unpack_from("<QQ", data, at)
            symbol_index = info >> 32
            if symbol_index * 24 >= symbols[5]:
                raise RuntimeError("Invalid relocation symbol reference")
            sname, sinfo, sother, ssection, svalue, ssize = struct.unpack_from("<IBBHQQ", data, symbols[4] + symbol_index * 24)
            symbol = string(symbol_names, sname)
            if not symbol and sinfo & 15 == 3:
                if ssection >= count:
                    raise RuntimeError("Invalid section symbol")
                symbol = "section:" + section_names[ssection]
            addend = struct.unpack_from("<q", data, at + 16)[0] if kind == 4 else None
            relocations.append((section_names[index], section_names[target], location, info & 0xffffffff,
                                symbol, svalue, ssize, sinfo, sother, addend))
    encoded = json.dumps({"allocated": allocated, "relocations": relocations}, separators=(",", ":")).encode()
    return {"allocated_section_count": len(allocated), "nondebug_relocation_count": len(relocations),
            "allocated_sections_and_nondebug_relocations_sha256": hashlib.sha256(encoded).hexdigest()}


def config_profile(text, profile):
    for symbol, enabled in profile["optional_exports"].items():
        macro = "HAVE_" + symbol.upper()
        defined = re.search(r"^#define " + macro + r" 1$", text, re.MULTILINE) is not None
        undefined = re.search(r"^/\* #undef " + macro + r" \*/$", text, re.MULTILINE) is not None
        if defined != enabled or undefined != (not enabled):
            raise RuntimeError("Generated feature macro differs from measured target: " + macro)
    if not re.search(r"^#define HAVE_SAI_QUERY_API_VERSION 1$", text, re.MULTILINE):
        raise RuntimeError("Required SAI version export was not configured")


def verify_inputs(source, ci):
    identity = json.loads((ci / "source.json").read_text())
    run(["git", "-C", str(source), "merge-base", "--is-ancestor", identity["source_commit"], "HEAD"])
    changed = run(["git", "-C", str(source), "diff", "--name-only", identity["source_commit"], "HEAD"]).splitlines()
    for path in changed:
        if not (path.startswith("mini-switch-syncd-ci/") or path == ".github/workflows/mini-switch-syncd-objects.yml"):
            raise RuntimeError("Non-CI upstream source was changed: " + path)
    if run(["git", "-C", str(source), "diff", "--name-only"]).strip():
        raise RuntimeError("Tracked source workspace is dirty")
    for path, expected in identity["source_hashes"].items():
        if sha(source / path) != expected:
            raise RuntimeError("Pinned upstream source differs: " + path)
    sai_commit = run(["git", "-C", str(source / "SAI"), "rev-parse", "HEAD"]).strip()
    if sai_commit != identity["sai_commit"]:
        raise RuntimeError("SAI submodule commit differs")
    headers = json.loads((ci / "sai-headers.json").read_text())
    if headers["commit"] != sai_commit:
        raise RuntimeError("SAI source and header pins disagree")
    for name, expected in headers["headers"].items():
        found = [source / "SAI" / subdir / name for subdir in ("inc", "experimental")
                 if (source / "SAI" / subdir / name).is_file()]
        if len(found) != 1 or sha(found[0]) != expected:
            raise RuntimeError("Actual pinned SAI header differs: " + name)
    profile = json.loads((ci / "vendor-interface-profile.json").read_text())
    if profile["configure_negative_cache"] != {"ac_cv_func_sai_tam_telemetry_get_data": "no"}:
        raise RuntimeError("Unreviewed configure cache selection")
    return identity, profile


def archive_members(path, expected_sources, logs):
    with path.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise RuntimeError("Only self-contained standard archives may be exported")
    listing = run(["ar", "t", str(path)], logs / (path.name + "-members.log")).splitlines()
    expected = [path.stem + "_a-" + Path(item).stem + ".o" for item in expected_sources]
    if len(listing) != len(expected) or set(listing) != set(expected) or len(set(listing)) != len(listing):
        raise RuntimeError("Archive does not contain exactly the normal production units: " + path.name)
    members = []
    for name in listing:
        if Path(name).name != name:
            raise RuntimeError("Unsafe archive member")
        data = run(["ar", "p", str(path), name], binary=True)
        members.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        **elf_header(data, relocatable=True), **link_content(data)})
    return members


def normalized_symbols(path, defined):
    text = run(["nm", "-A", "-P", "--defined-only" if defined else "--undefined-only", str(path)])
    return text.replace(str(path), path.name)


def direct_undefined(text):
    found = set()
    for line in text.splitlines():
        match = re.search(r":\s+(\S+)\s+U(?:\s|$)", line)
        if match:
            found.add(match.group(1))
    return found


def portable_link(log, source):
    candidates = []
    for line in log.splitlines():
        if "libtool: link: " in line:
            line = line.split("libtool: link: ", 1)[1]
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if tokens and Path(tokens[0]).name in {"g++", "c++"} and "-o" in tokens and "libSyncd.a" in tokens:
            if Path(tokens[tokens.index("-o") + 1]).name == "syncd":
                candidates.append(tokens)
    if len(candidates) != 1:
        raise RuntimeError("Cannot identify one actual normal production link command")
    tokens = candidates[0]
    if "-lsai" not in tokens or any("saivs" in token for token in tokens):
        raise RuntimeError("Actual production link is not the vendor SAI target")
    mapping = {"syncd-main.o": "objects/syncd-main.o", "libSyncd.a": "archives/libSyncd.a",
               "../lib/libSaiRedis.a": "archives/libSaiRedis.a",
               str(source / "lib/libSaiRedis.a"): "archives/libSaiRedis.a"}
    portable = ["c++"]
    changed = set()
    for index, token in enumerate(tokens[1:], 1):
        if tokens[index - 1] == "-o":
            portable.append("{output}")
        elif token == "-L" + str(source / "mini-switch-syncd-libraries"):
            portable.append("-L{vendor_library_dir}")
            changed.add("vendor_library_dir")
        elif token in {"-L../meta/.libs", "-L" + str(source / "meta/.libs")}:
            portable.append("-L{metadata_library_dir}")
        elif token in mapping:
            portable.append(mapping[token])
            changed.add(mapping[token])
        else:
            if "/work" in token or "mini-switch-syncd-libraries" in token or token in {";", "&&", "||"}:
                raise RuntimeError("Untranslated build-tree or shell argument in link command")
            portable.append(token)
    if changed != {"vendor_library_dir", "objects/syncd-main.o", "archives/libSyncd.a", "archives/libSaiRedis.a"}:
        raise RuntimeError("Actual link command does not have the expected portable inputs")
    return {"actual_public_link_tokens": tokens, "private_native_link_template": portable,
            "template_requires_local_vendor_library_and_loader_acceptance": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--ci", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-inputs-only", action="store_true")
    args = parser.parse_args()
    source, ci, output = args.source.resolve(), args.ci.resolve(), args.output.resolve()
    if not args.verify_inputs_only and (platform.system() != "Linux" or platform.machine() != "aarch64"):
        raise RuntimeError("Object acceptance requires actual Linux AArch64")
    identity, profile = verify_inputs(source, ci)
    if args.verify_inputs_only:
        print("Pinned upstream source, submodule, SAI headers and measured interface selection verified")
        return
    config = (source / "config.h").read_text()
    config_profile(config, profile)
    export = output / "object-export"
    export.mkdir()
    logs = export / "logs"
    logs.mkdir()
    redis_sources = source_list((source / "lib/Makefile.am").read_text(), "libSaiRedis_a_SOURCES")
    syncd_sources = source_list((source / "syncd/Makefile.am").read_text(), "libSyncd_a_SOURCES")
    if len(redis_sources) != 22 or len(syncd_sources) != 44:
        raise RuntimeError("Pinned production source-count drift")
    members = []
    for relative, sources in (("lib/libSaiRedis.a", redis_sources), ("syncd/libSyncd.a", syncd_sources), ("syncd/syncd-main.o", None)):
        original = source / relative
        destination = export / ("archives" if sources else "objects") / original.name
        destination.parent.mkdir(exist_ok=True)
        before = {"bytes": original.stat().st_size, "sha256": sha(original)}
        original_symbols = [normalized_symbols(original, defined) for defined in (False, True)]
        original_members = archive_members(original, sources, logs) if sources else [link_content(original.read_bytes())]
        shutil.copyfile(original, destination)
        run(["strip", "--strip-debug", str(destination)])
        symbols = [normalized_symbols(destination, defined) for defined in (False, True)]
        if symbols != original_symbols or sha(original) != before["sha256"]:
            raise RuntimeError("Debug-only strip changed link symbols or the original artifact")
        for defined, symbol_text in zip((False, True), symbols):
            (logs / (original.name + ("-defined.log" if defined else "-undefined.log"))).write_text(symbol_text)
        after_members = archive_members(destination, sources, logs) if sources else [link_content(destination.read_bytes())]
        field = "allocated_sections_and_nondebug_relocations_sha256"
        if [item[field] for item in original_members] != [item[field] for item in after_members]:
            raise RuntimeError("Debug-only stripping changed code/data or nondebug relocations")
        sections = run(["readelf", "-W", "-S", str(destination)], logs / (original.name + "-sections.log"))
        run(["readelf", "-W", "-r", str(destination)], logs / (original.name + "-relocations.log"))
        if re.search(r"\]\s+\.debug", sections) or ".symtab" not in sections:
            raise RuntimeError("Export must remove debug sections and retain symbol tables")
        members.append({"path": destination.relative_to(export).as_posix(), "source_path": relative,
                        "original": before, "stripped": {"bytes": destination.stat().st_size, "sha256": sha(destination)},
                        "original_unchanged": True, "defined_and_undefined_symbols_preserved": True,
                        "allocated_sections_and_nondebug_relocations_preserved": True,
                        "original_members": original_members, "stripped_members": after_members})
    undefined = direct_undefined((logs / "libSyncd.a-undefined.log").read_text())
    for symbol, enabled in {profile["required_export"]: True, **profile["optional_exports"]}.items():
        if (symbol in undefined) != enabled:
            raise RuntimeError("Actual VendorSai references differ from the target feature selection: " + symbol)
    public = source / "syncd/syncd"
    with public.open("rb") as stream:
        public_header = elf_header(stream.read(64))
    loader = run(["ldd", "-r", str(public)], logs / "public-syncd-loader.log")
    dynamic = run(["readelf", "-W", "-d", str(public)], logs / "public-syncd-dynamic.log")
    run(["readelf", "-W", "-h", "-l", "-n", "-V", str(public)], logs / "public-syncd-elf.log")
    if any(term in loader for term in ("not found", "undefined symbol:", "libsaivs")) or "libsairedis.so" not in loader:
        raise RuntimeError("Actual public validation link has invalid loader closure")
    if re.search(r"\((?:RPATH|RUNPATH)\)", dynamic):
        raise RuntimeError("Public validation ELF contains embedded search paths")
    public_library = Path("/usr/lib/aarch64-linux-gnu/libsairedis.so").resolve()
    library = ctypes.CDLL(str(public_library))
    query = library.sai_query_api_version
    query.argtypes, query.restype = [ctypes.POINTER(ctypes.c_uint64)], ctypes.c_int32
    version = ctypes.c_uint64()
    if query(ctypes.byref(version)) != 0 or version.value != profile["sai_api_version"]:
        raise RuntimeError("Actual public SAI API version differs")
    public_exports = {name: hasattr(library, name) for name in profile["optional_exports"]}
    if not all(public_exports.values()):
        raise RuntimeError("Public configure library does not expose the expected genuine APIs")
    portable = portable_link((output / "public-syncd-link.log").read_text(), source)
    (export / "link-command.json").write_text(json.dumps(portable, indent=2) + "\n")
    (export / "config.h").write_text(config)
    for name in ("source.json", "dependencies.json", "sai-headers.json", "vendor-interface-profile.json"):
        shutil.copyfile(ci / name, export / name)
    for name in ("LICENSE", "NOTICE"):
        if (source / name).is_file():
            shutil.copyfile(source / name, export / name)
    for name in ("Apache-2.0.txt", "PUBLIC-NOTICE.txt"):
        shutil.copyfile(ci / name, export / name)
    # Include source licenses for metadata/header inputs as well.
    for path in sorted((source / "SAI").glob("LICENSE*")):
        if path.is_file():
            shutil.copyfile(path, export / ("SAI-" + path.name))
    copied_bytes = sum(item["stripped"]["bytes"] for item in members)
    if copied_bytes > MAX_EXPORT:
        raise RuntimeError("Stripped relocatables exceed 64 MiB")
    report = {"schema_version": 1, "status": "PASS", "source_commit": identity["source_commit"],
              "sai_commit": identity["sai_commit"], "executed_checkout_commit": run(["git", "-C", str(source), "rev-parse", "HEAD"]).strip(),
              "artifacts": members, "target_interface_profile": profile,
              "public_configure_library": {"path": str(public_library), "bytes": public_library.stat().st_size,
                                            "sha256": sha(public_library), "api_version": version.value, "optional_exports": public_exports},
              "public_syncd_validation_elf": {"bytes": public.stat().st_size, "sha256": sha(public), **public_header},
              "public_validation_link_executed": True, "private_vendor_link_executed": False,
              "sonic_startup_executed": False, "physical_or_rtl_traffic_executed": False,
              "strip_operation": "GNU strip --strip-debug on copies; actual defined/undefined symbol equality checked",
              "production_translation_units": {"libSyncd": len(syncd_sources), "libSaiRedis": len(redis_sources), "main": 1},
              "production_source_hashes": [{"path": directory + "/" + name, "sha256": sha(source / directory / name)}
                                           for directory, names in (("syncd", syncd_sources + ["main.cpp"]), ("lib", redis_sources))
                                           for name in names],
              "exported_relocatable_bytes": copied_bytes, "link_command": portable,
              "file_hashes": [{"path": path.relative_to(export).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
                              for path in sorted(export.rglob("*")) if path.is_file()]}
    (export / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    archive = output / "mini-switch-arm64-syncd-objects.tar.gz"
    with archive.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as tar:
                for path in sorted(export.rglob("*")):
                    if path.is_file():
                        entry = tar.gettarinfo(str(path), arcname=path.relative_to(export).as_posix())
                        entry.uid = entry.gid = entry.mtime = 0
                        entry.uname = entry.gname = ""
                        entry.mode = 0o644
                        with path.open("rb") as stream:
                            tar.addfile(entry, stream)
    if archive.stat().st_size > MAX_ARCHIVE:
        raise RuntimeError("Compressed production object artifact exceeds 32 MiB")
    report["archive"] = {"filename": archive.name, "bytes": archive.stat().st_size, "sha256": sha(archive)}
    report["manifest_sha256"] = sha(export / "manifest.json")
    (output / "object-export.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: authentic public production relocatables and Redis-SAI validation link; private link/startup pending")


if __name__ == "__main__":
    main()
