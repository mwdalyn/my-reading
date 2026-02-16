import subprocess, sys
from pathlib import Path

def build_git_tracked_tree():
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True
    )

    files = result.stdout.splitlines()
    tree = {}

    for file in files:
        parts = file.split("/")
        current = tree
        for part in parts:
            current = current.setdefault(part, {})

    def render(node, prefix=""):
        lines = []
        keys = sorted(node.keys())
        for i, key in enumerate(keys):
            connector = "└── " if i == len(keys) - 1 else "├── "
            lines.append(prefix + connector + key)
            if node[key]:
                extension = "    " if i == len(keys) - 1 else "│   "
                lines.extend(render(node[key], prefix + extension))
        return lines

    root_name = Path.cwd().name
    return root_name + "\n" + "\n".join(render(tree))


# Execute
if __name__ == "__main__":
    try:
        # Ensure we're inside a git repo
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        print("Error: Not inside a Git repository.")
        sys.exit(1)
    # Build tree
    tree_text = build_git_tracked_tree()
    # Output path (project root)
    output_path = Path.cwd() / "project_tree.txt"
    # Write file
    output_path.write_text(tree_text, encoding="utf-8")
    print(f"Project tree written to: {output_path}")
