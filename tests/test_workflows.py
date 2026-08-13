"""The one thing every workflow in this repository has to know.

The repository is named `EPUB-F.O.R.G.E.` — with a trailing dot — and Windows
cannot hold a directory whose name ends in one. The runner's own workspace is
`D:\\a\\<repo>\\<repo>`, so on every Windows job that path *cannot exist*:

    ##[error]Directory 'D:\\a\\EPUB-F.O.R.G.E.\\EPUB-F.O.R.G.E.' does not exist

`actions/checkout` raises it while validating `GITHUB_WORKSPACE`, before it
reads its own inputs, so its `path:` option cannot rescue it — and every `run:`
step defaults to that same directory.

`build-windows.yml` has carried the workaround and the explanation since it was
written. The lock workflow was added beside it with a plain
`actions/checkout@v4` and failed on its first run with exactly that error: the
comment was one file away and I copied the shape without reading it.

So it becomes a test. A comment explains a trap to whoever reads that file; a
test explains it to whoever does not.
"""

from __future__ import annotations

import pathlib

import pytest

WORKFLOWS = sorted((pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


def source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def windows_jobs(text: str) -> bool:
    return "windows-latest" in text or "windows-" in text


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
class TestEveryWindowsWorkflow:
    def test_does_not_use_actions_checkout(self, workflow):
        """It cannot work here, and it fails before doing anything — which
        makes it look like a runner problem rather than a naming one."""
        text = source(workflow)
        if not windows_jobs(text):
            pytest.skip("not a Windows job")
        # The `uses:` form, not the word: both files explain the trap in a
        # comment that names the action, and a test that cannot tell an
        # explanation from a use would forbid writing the explanation down.
        used = [
            line for line in text.splitlines()
            if line.strip().startswith(("- uses:", "uses:")) and "actions/checkout" in line
        ]
        assert not used, (
            f"{workflow.name} uses actions/checkout, which cannot run in a "
            f"repository whose name ends in a dot. Clone into D:\\forge "
            f"instead — see build-windows.yml. Found: {used}"
        )

    def test_clones_into_a_path_windows_can_represent(self, workflow):
        text = source(workflow)
        if not windows_jobs(text):
            pytest.skip("not a Windows job")
        assert "D:\\forge" in text, f"{workflow.name} never establishes a usable checkout"

    def test_and_says_why(self, workflow):
        """The next person to add a workflow copies one of these. If the reason
        is not in the file they copy, they copy the workaround without it and
        remove it as noise the first time it is in the way."""
        text = source(workflow)
        if not windows_jobs(text):
            pytest.skip("not a Windows job")
        assert "trailing dot" in text or "ends in one" in text, (
            f"{workflow.name} works around the repository name without saying so"
        )

    def test_artifacts_are_named_by_absolute_path(self, workflow):
        """Artifact globs resolve against the workspace — the directory all of
        this exists to avoid — so a relative path silently uploads nothing."""
        text = source(workflow)
        if not windows_jobs(text) or "upload-artifact" not in text:
            pytest.skip("nothing uploaded")
        uploads = text.split("upload-artifact", 1)[1]
        listed = [
            line.strip()
            for line in uploads.splitlines()
            if line.strip().endswith((".exe", ".zip", ".txt", ".lock"))
        ]
        assert listed, f"{workflow.name} uploads nothing recognisable"
        for entry in listed:
            assert entry.startswith("D:\\"), f"{workflow.name}: {entry} is not absolute"


def test_there_is_at_least_one_workflow():
    """A guard on the guard: an empty glob makes every test above vacuous."""
    assert WORKFLOWS
