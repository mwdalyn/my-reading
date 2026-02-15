# generate_requirements.py
import ast, sys, pkg_resources
# Ensure project root is on sys.path (solve proj layout constraint; robust for local + CI + REPL)
from pathlib import Path
# In lieu of packaging and running with python -m  
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import *

# Collect all imported module names in all .py files
def find_imports(path):
    modules = set()
    for py_file in path.rglob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(py_file))
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    modules.add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module.split(".")[0])
    return modules

# Check which modules are installed and get versions
def installed_packages(modules):
    installed = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
    requirements = []
    for mod in modules:
        key = mod.lower()
        if key in installed:
            requirements.append(f"{mod}=={installed[key]}")
    return requirements

if __name__ == "__main__":
    imports = find_imports(PROJECT_ROOT)
    reqs = installed_packages(imports)

    if reqs:
        with open(REQ_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(reqs)))
        print(f"requirements.txt generated at {REQ_FILE}")
    else:
        print("No installed modules found for your imports.")
