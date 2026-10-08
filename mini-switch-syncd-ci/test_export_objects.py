#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rejection/parser policy tests; these never claim positive Linux acceptance."""
import json
from pathlib import Path
import struct
import unittest

import export_objects as policy


class PolicyTests(unittest.TestCase):
    def test_continued_source_list_and_duplicate(self):
        text = "SOURCES = \\\n first.cpp \\\n second.cpp \\\n first.cpp\nOTHER = third.cpp\n"
        self.assertEqual(policy.source_list(text, "SOURCES"), ["first.cpp", "second.cpp"])

    def test_missing_source_list(self):
        with self.assertRaises(RuntimeError):
            policy.source_list("OTHER = x.cpp\n", "SOURCES")

    def test_truncated_source_list(self):
        with self.assertRaises(RuntimeError):
            policy.source_list("SOURCES = \\" , "SOURCES")

    def test_reject_non_elf(self):
        with self.assertRaises(RuntimeError):
            policy.elf_header(b"not an object")

    def test_reject_wrong_machine_and_type(self):
        # Explicit malformed-header fixtures test rejection, never acceptance.
        for kind, machine in ((1, 62), (2, 183), (3, 183)):
            header = bytearray(64)
            header[:7] = b"\x7fELF\x02\x01\x01"
            struct.pack_into("<HH", header, 16, kind, machine)
            with self.assertRaises(RuntimeError):
                policy.elf_header(header, relocatable=True)

    def test_measured_feature_profile(self):
        profile = json.loads((Path(__file__).parent / "vendor-interface-profile.json").read_text())
        text = "#define HAVE_SAI_QUERY_API_VERSION 1\n" + "\n".join(
            "#define HAVE_" + symbol.upper() + " 1" if enabled else "/* #undef HAVE_" + symbol.upper() + " */"
            for symbol, enabled in profile["optional_exports"].items())
        policy.config_profile(text, profile)
        with self.assertRaises(RuntimeError):
            policy.config_profile(text.replace("/* #undef HAVE_SAI_TAM_TELEMETRY_GET_DATA */", "#define HAVE_SAI_TAM_TELEMETRY_GET_DATA 1"), profile)

    def test_missing_required_query(self):
        profile = {"optional_exports": {}}
        with self.assertRaises(RuntimeError):
            policy.config_profile("", profile)

    def test_exact_global_symbol_names(self):
        text = "libSyncd.a[VendorSai.o]: sai_query_api_version U\nlibSyncd.a[X.o]: _Z20sai_query_api_version U\n"
        self.assertEqual(policy.direct_undefined(text), {"sai_query_api_version", "_Z20sai_query_api_version"})

    def test_portable_actual_link_parser(self):
        line = "libtool: link: g++ -g -O2 -rdynamic -L/work/mini-switch-syncd-libraries -o syncd syncd-main.o libSyncd.a ../lib/libSaiRedis.a -L../meta/.libs -lsaimetadata -lsaimeta -ldl -lhiredis -lswsscommon -lsai -lpthread -lzmq -lz"
        value = policy.portable_link(line, Path("/work"))
        self.assertIn("-L{vendor_library_dir}", value["private_native_link_template"])
        self.assertIn("-lsai", value["private_native_link_template"])
        self.assertNotIn("/work", " ".join(value["private_native_link_template"]))
        for bad in (line.replace("-lsai ", "-lsaivs "), line.replace("../lib/libSaiRedis.a", "/unknown/lib.a"), line + "\n" + line):
            with self.assertRaises(RuntimeError):
                policy.portable_link(bad, Path("/work"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
