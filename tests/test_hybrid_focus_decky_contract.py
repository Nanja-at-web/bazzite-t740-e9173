import ast
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "prototype/hybrid-focus/decky/BazziteHybridFocus"


class DeckyContractTests(unittest.TestCase):
    def test_plugin_is_unprivileged(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text())
        self.assertNotIn("_root", manifest.get("flags", []))
        self.assertEqual(manifest["api_version"], 1)

    def test_backend_exposes_only_status_and_target_operations(self):
        source = (PLUGIN / "main.py").read_text()
        tree = ast.parse(source)
        plugin = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Plugin"
        )
        public_methods = {
            node.name
            for node in plugin.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        }
        self.assertEqual(public_methods, {"get_status", "set_target"})
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("subprocess", source)

    def test_backend_uses_private_user_socket_and_strict_protocol(self):
        source = (PLUGIN / "main.py").read_text()
        self.assertIn("DECKY_USER_HOME", source)
        self.assertIn("XDG_RUNTIME_DIR", source)
        self.assertIn("bazzite-hybrid-focus/control.sock", source)
        self.assertIn('"version": 1', source)
        self.assertRegex(source, r"target\s+not\s+in\s+\{[^}]*desktop[^}]*game")
        self.assertIn("socket.AF_UNIX", source)

    def test_qam_has_expected_control_and_neutral_fallback(self):
        source = (PLUGIN / "src/index.tsx").read_text()
        self.assertIn("Hybrid Display Control", source)
        self.assertIn("Controller to Desktop 2", source)
        self.assertIn("Return Controller to Game", source)
        self.assertIn("ButtonItem", source)
        self.assertIn("toaster.toast", source)
        self.assertIn("Navigation.CloseSideMenus", source)
        self.assertRegex(source, r"glyph_family\s*\?\?\s*[\"']neutral[\"']")
        self.assertIn("Neutral", source)

    def test_frontend_calls_only_two_backend_methods(self):
        source = (PLUGIN / "src/index.tsx").read_text()
        calls = set(re.findall(r'callable<[^;]+?>\(["\']([^"\']+)["\']\)', source))
        self.assertEqual(calls, {"get_status", "set_target"})

    def test_build_contract_is_pinned_and_has_entrypoint(self):
        package = json.loads((PLUGIN / "package.json").read_text())
        self.assertEqual(package["packageManager"].split("+")[0], "pnpm@9.15.9")
        self.assertIn("build", package["scripts"])
        self.assertTrue((PLUGIN / "pnpm-lock.yaml").is_file())
        self.assertTrue((PLUGIN / "tsconfig.json").is_file())


if __name__ == "__main__":
    unittest.main()
