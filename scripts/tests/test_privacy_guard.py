"""Tests for scripts/privacy_check.py and the Claude Code guard (.claude/hooks/guard.py).

Run: python -m unittest discover -s scripts/tests
Fake secrets are assembled at runtime so this file never trips the scanners itself.
"""

from __future__ import annotations

import importlib.util
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import privacy_check  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "guard", REPO_ROOT / ".claude" / "hooks" / "guard.py"
)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
sys.modules["guard"] = guard
spec.loader.exec_module(guard)


def tiff(ifd0: list[tuple[int, int, int, bytes]], gps: bool = False) -> bytes:
    """Little-endian TIFF: IFD0 entries (tag, type, count, 4-byte value), optional GPS IFD."""
    entries = list(ifd0)
    gps_offset = 8 + 2 + 12 * (len(entries) + (1 if gps else 0)) + 4
    if gps:
        entries.append((0x8825, 4, 1, struct.pack("<I", gps_offset)))
    body = struct.pack("<H", len(entries))
    body += b"".join(struct.pack("<HHI", t, k, n) + v for t, k, n, v in entries)
    body += struct.pack("<I", 0)
    if gps:  # GPSVersionID + GPSLatitudeRef
        body += struct.pack("<H", 2)
        body += struct.pack("<HHI", 0x0000, 1, 4) + bytes([2, 3, 0, 0])
        body += struct.pack("<HHI", 0x0001, 2, 2) + b"N\x00\x00\x00"
        body += struct.pack("<I", 0)
    return b"II*\x00" + struct.pack("<I", 8) + body


def jpeg(exif: bytes | None) -> bytes:
    segment = b""
    if exif is not None:
        payload = b"Exif\x00\x00" + exif
        segment = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    return b"\xff\xd8" + segment + b"\xff\xd9"


def png(exif: bytes) -> bytes:
    chunk = struct.pack(">I", len(exif)) + b"eXIf" + exif + b"\x00\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + chunk


SERIAL = (0xA431, 2, 4, b"123\x00")
ORIENTATION = (0x0112, 3, 1, b"\x01\x00\x00\x00")


class ImageFindings(unittest.TestCase):
    def test_clean_jpeg_passes(self) -> None:
        self.assertEqual(privacy_check.image_findings(jpeg(None)), [])
        self.assertEqual(privacy_check.image_findings(jpeg(tiff([ORIENTATION]))), [])

    def test_jpeg_with_gps_fails(self) -> None:
        found = privacy_check.image_findings(jpeg(tiff([ORIENTATION], gps=True)))
        self.assertEqual(found, ["EXIF GPS data"])

    def test_jpeg_with_camera_serial_fails(self) -> None:
        found = privacy_check.image_findings(jpeg(tiff([SERIAL])))
        self.assertEqual(found, ["EXIF BodySerialNumber"])

    def test_png_exif_chunk_is_read(self) -> None:
        found = privacy_check.image_findings(png(tiff([SERIAL], gps=True)))
        self.assertEqual(found, ["EXIF BodySerialNumber", "EXIF GPS data"])

    def test_xmp_gps_fails(self) -> None:
        xmp = b'<x:xmpmeta><rdf:Description exif:GPSLatitude="52,31N"/></x:xmpmeta>'
        self.assertEqual(privacy_check.image_findings(jpeg(None) + xmp), ["XMP GPSLatitude"])

    def test_garbage_does_not_crash(self) -> None:
        self.assertEqual(privacy_check.image_findings(b"Exif\x00\x00II*\x00\xff\xff\xff\xff"), [])


class DeniedPaths(unittest.TestCase):
    def test_deny_list_matches_private_paths_only(self) -> None:
        paths = ["maps/kitchen.yaml", "x/run.mcap", ".env", ".env.example", "src/a.py"]
        denied = privacy_check.denied_paths(paths, REPO_ROOT)
        self.assertEqual(denied, ["maps/kitchen.yaml", "x/run.mcap", ".env"])


def analyze(command: str) -> guard.Plan:
    return guard.analyze(command, str(REPO_ROOT))


class Analyze(unittest.TestCase):
    def setUp(self) -> None:
        self.branch = guard.current_branch

    def tearDown(self) -> None:
        guard.current_branch = self.branch

    def on_branch(self, name: str) -> None:
        guard.current_branch = lambda cwd: name

    def test_unrelated_commands_pass(self) -> None:
        for command in ("ls -la", "git status && git log --oneline | head", "gh issue view 13"):
            plan = analyze(command)
            self.assertEqual((plan.blocks, plan.push_dirs, plan.scan_text), ([], [], False))

    def test_feature_branch_push_is_scanned_not_blocked(self) -> None:
        self.on_branch("13-guard")
        plan = analyze('cd "some dir" && git push -u origin 13-guard 2>&1 | tail -5')
        self.assertEqual(plan.blocks, [])
        self.assertEqual(len(plan.push_dirs), 1)
        self.assertTrue(plan.push_dirs[0].endswith("some dir"))

    def test_push_to_main_is_blocked(self) -> None:
        self.on_branch("13-guard")
        for command in (
            "git push origin main",
            "git push origin HEAD:main",
            "git push origin x:refs/heads/main",
        ):
            self.assertTrue(analyze(command).blocks, command)
        self.on_branch("main")
        for command in ("git push", "git push origin", "git push origin HEAD"):
            self.assertTrue(analyze(command).blocks, command)

    def test_force_and_delete_are_blocked(self) -> None:
        self.on_branch("13-guard")
        for command in (
            "git push --force",
            "git push -uf origin x",
            "git push --force-with-lease origin x",
            "git push origin +x",
            "git push --mirror",
            "git push origin --delete x",
            "git push origin :x",
        ):
            self.assertTrue(analyze(command).blocks, command)

    def test_no_verify_is_blocked(self) -> None:
        for command in (
            'git commit --no-verify -m "x"',
            'git commit -anm "x"',
            "git push --no-verify",
        ):
            self.assertTrue(analyze(command).blocks, command)
        self.assertEqual(analyze('git commit -am "name the -n flag"').blocks, [])

    def test_merge_is_blocked(self) -> None:
        self.assertTrue(analyze("gh pr merge 14 --squash").blocks)
        self.assertTrue(analyze("gh api -X PUT repos/o/r/pulls/14/merge").blocks)

    def test_text_in_quotes_is_not_a_command(self) -> None:
        self.on_branch("13-guard")
        command = (
            "git commit -m \"$(cat <<'EOF'\nblock gh pr merge and git push --force main\nEOF\n)\""
        )
        self.assertEqual(analyze(command).blocks, [])

    def test_nested_shell_is_analyzed(self) -> None:
        self.assertTrue(analyze("bash -c 'gh pr merge 3'").blocks)

    def test_gh_writes_are_scanned(self) -> None:
        for command in (
            'gh issue comment 13 --body "done"',
            "gh pr create --title t --body-file body.md",
            "gh api repos/o/r/issues/1/comments -f body=hi",
            "gh api -X PATCH repos/o/r/issues/1 --input x.json",
        ):
            self.assertTrue(analyze(command).scan_text, command)
        self.assertFalse(analyze("gh api repos/o/r/issues/1").scan_text)
        plan = analyze("gh pr create --title t --body-file body.md")
        self.assertEqual([Path(f).name for f in plan.text_files], ["body.md"])

    def test_unparseable_command_falls_back_conservatively(self) -> None:
        plan = analyze("git push --force origin 'x")
        self.assertTrue(plan.blocks)


def run(cwd: Path, *args: str) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(
    guard.shutil.which("gitleaks") or guard.os.environ.get("LOCALAPPDATA"), "needs gitleaks"
)
class CheckPush(unittest.TestCase):
    """End to end against a throwaway repo with a bare remote."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "work"
        run(root, "git", "init", "-q", "--bare", "remote.git")
        run(root, "git", "init", "-q", "-b", "main", "work")
        run(self.repo, "git", "config", "user.name", "Test")
        run(self.repo, "git", "config", "user.email", "1+test@users.noreply.github.com")
        run(self.repo, "git", "remote", "add", "origin", str(root / "remote.git"))
        self.commit("README.md", "hello\n")
        self.commit(".gitignore", (REPO_ROOT / ".gitignore").read_bytes())
        run(self.repo, "git", "push", "-q", "origin", "main")
        run(self.repo, "git", "switch", "-q", "-c", "feature")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def commit(self, name: str, content: str | bytes, *extra: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        run(self.repo, "git", "add", "-f", name)
        run(self.repo, "git", *extra, "commit", "-q", "-m", f"add {name}")

    def test_clean_push_passes(self) -> None:
        self.commit("docs/notes.md", "nothing private here\n")
        self.assertEqual(guard.check_push(str(self.repo)), [])

    def test_nothing_outgoing_passes(self) -> None:
        self.assertEqual(guard.check_push(str(self.repo)), [])

    def test_secret_is_found(self) -> None:
        self.commit("config.env.md", "wifi_password = " + "Sunny" + "Garden" + "42\n")
        problems = guard.check_push(str(self.repo))
        self.assertTrue(any("wifi-credential" in p for p in problems), problems)

    def test_personal_email_is_found(self) -> None:
        self.commit("a.md", "x\n", "-c", "user.email=someone@" + "gmx.de")
        problems = guard.check_push(str(self.repo))
        self.assertTrue(any("personal email" in p for p in problems), problems)

    def test_force_added_private_path_is_found(self) -> None:
        self.commit("maps/home.yaml", "image: home.pgm\n")
        problems = guard.check_push(str(self.repo))
        self.assertTrue(any("maps/home.yaml" in p for p in problems), problems)

    def test_image_with_gps_is_found(self) -> None:
        self.commit("docs/robot.jpg", jpeg(tiff([ORIENTATION], gps=True)))
        problems = guard.check_push(str(self.repo))
        self.assertTrue(any("GPS" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
