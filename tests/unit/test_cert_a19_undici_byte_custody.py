"""CERT-A19 fail-closed offline fixture tests; no HTTP, Docker or Node."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import ci_cert_a19_undici_byte_custody as a19


class A19ByteCustodyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.payload = self.home / "debian"
        self.worker = self.home / "a18"
        for base in (self.payload, self.worker):
            p = base / "usr/share/nodejs/undici/lib"
            p.mkdir(parents=True)
            (p / "balanced-pool.js").write_bytes(
                b"const pool=this[kFactory](upstreamOrigin, "
                b"Object.assign({}, this[kOptions]))\n")

    def test_only_two_specific_paths_proven(self):
        report = a19.check_mechanisms(self.payload, self.worker)
        self.assertIn("EXACT_TWO_PATHS_MATCH", report["worker_byte_parity"])
        self.assertEqual(report["package_balanced_pool_sha256"],
                         report["worker_balanced_pool_sha256"])

    def test_no_a18_keeps_worker_parity_unknown(self):
        report = a19.check_mechanisms(self.payload, None)
        self.assertIn("UNVERIFIED", report["worker_byte_parity"])
        self.assertIsNone(report["worker_balanced_pool_sha256"])

    def test_worker_byte_mismatch_denied(self):
        target = self.worker / "usr/share/nodejs/undici/lib/balanced-pool.js"
        target.write_bytes(target.read_bytes() + b"// tampered\n")
        with self.assertRaisesRegex(a19.A19Refused, "BYTES_DIFFER"):
            a19.check_mechanisms(self.payload, self.worker)

    def test_json_clone_denied(self):
        p = self.payload / "usr/share/nodejs/undici/lib/balanced-pool.js"
        p.write_bytes(b"JSON.parse(JSON.stringify(opts))\n")
        with self.assertRaisesRegex(a19.A19Refused, "UNEXPECTED_MECHANISM"):
            a19.check_mechanisms(self.payload, None)

    def test_cache_interceptor_path_present_denied(self):
        p = self.payload / "usr/share/nodejs/undici/lib/interceptor/cache.js"
        p.parent.mkdir(exist_ok=True)
        p.write_text("present")
        with self.assertRaisesRegex(a19.A19Refused, "CACHE_INTERCEPTOR_PATH_PRESENT"):
            a19.check_mechanisms(self.payload, None)

    def test_symlink_member_denied(self):
        p = self.payload / "usr/share/nodejs/undici/lib/balanced-pool.js"
        p.unlink()
        p.symlink_to(self.worker / "usr/share/nodejs/undici/lib/balanced-pool.js")
        with self.assertRaisesRegex(a19.A19Refused, "SYMLINK_MEMBER_REFUSED"):
            a19.check_mechanisms(self.payload, None)

    def test_untrusted_archive_sha_denied(self):
        p = self.home / "debian.deb"
        p.write_bytes(b"invalid archive")
        with self.assertRaisesRegex(a19.A19Refused, "ARCHIVE_HASH_MISMATCH"):
            a19.verify_hash(p, a19._DEB_SHA, 2_000_000)

    def test_fake_duplicate_lock_key_denied(self):
        with self.assertRaisesRegex(a19.A19Refused, "DUPLICATE_LOCK_KEY"):
            a19._reject_duplicate([("a", 1), ("a", 2)])

    def test_worker_cache_path_present_denied(self):
        p = self.worker / "usr/share/nodejs/undici/lib/interceptor/cache.js"
        p.parent.mkdir(exist_ok=True)
        p.write_text("present")
        with self.assertRaisesRegex(a19.A19Refused, "WORKER_CACHE_INTERCEPTOR_PRESENT"):
            a19.check_mechanisms(self.payload, self.worker)


if __name__ == "__main__":
    unittest.main()
