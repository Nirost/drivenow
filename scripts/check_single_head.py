"""
Fail if the Alembic migration graph has more than one head.

Two heads happen easily when branches are merged: each adds a revision
pointing at the same parent. Alembic does not error on this until someone
runs `upgrade head`, by which point the divergence is already merged.
Checking at commit time is cheap; untangling it later is not.

Portable across Linux and macOS — no `grep -P`, which is GNU-only.
"""
import pathlib
import re
import sys

VERSIONS = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"

REVISION = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
DOWN = re.compile(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.MULTILINE)


def main() -> int:
    revisions: set[str] = set()
    parents: set[str] = set()

    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text()
        match = REVISION.search(text)
        if not match:
            print(f"{path.name}: no revision identifier found")
            return 1
        revisions.add(match.group(1))

        down = DOWN.search(text)
        if down and down.group(1):
            parents.add(down.group(1))

    heads = revisions - parents

    if len(heads) != 1:
        print(f"Expected exactly 1 migration head, found {len(heads)}: {sorted(heads)}")
        print("Resolve with: alembic merge -m 'merge heads' " + " ".join(sorted(heads)))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
