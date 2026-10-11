import importlib.util
from pathlib import Path
import unittest

class PrivacyTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/"scripts"/"audit_release.py"
        spec=importlib.util.spec_from_file_location("release_audit",path)
        self.audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.audit)
    def test_public_source_has_no_scanned_local_identity_or_paths(self):
        self.assertEqual(self.audit.audit_source(),[])
    def test_account_paths_and_explicit_identifiers_detected(self):
        self.assertTrue(self.audit.sensitive(b"C:"+bytes([92])+b"Users"+bytes([92])+b"sample",[]))
        self.assertTrue(self.audit.sensitive("private-identifier".encode("utf-16le"),["private-identifier"]))
        self.assertFalse(self.audit.sensitive(b"%LOCALAPPDATA%",[]))
    def test_allowlist_excludes_runtime_and_build_files(self):
        files=self.audit.public_files()
        self.assertTrue(files)
        for p in files:
            self.assertFalse({"dist","build",".git",".venv","__pycache__"}.intersection(p.relative_to(self.audit.ROOT).parts))
            self.assertNotIn(p.name,{"settings.json","quickmove.json","inventory-options.json"})
    def test_own_public_metadata_uses_wirru(self):
        root=self.audit.ROOT
        self.assertIn("Copyright (c) 2026 wirru",(root/"LICENSE").read_text(encoding="utf-8"))
        version=(root/"scripts"/"windows-version.txt").read_text(encoding="utf-8")
        self.assertIn("StringStruct('CompanyName','wirru')",version)
        self.assertIn("Copyright (c) 2026 wirru",version)
