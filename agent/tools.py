import json, os, re, subprocess
from pathlib import Path, PurePosixPath

# Folder that contains the agent/ package (the UC05 agent repo).
AGENT_ROOT = Path(__file__).resolve().parents[1]
# Folder of the repository being analyzed (config/, docs/, service code, tests).
# In GitHub Actions the reusable workflows set UC_REPO_ROOT to the caller repo checkout.
# When it is not set, the agent folder itself is used (old single-repo behaviour).
ROOT = Path(os.environ.get("UC_REPO_ROOT") or AGENT_ROOT).resolve()
if not ROOT.is_dir():
    raise RuntimeError(f"UC_REPO_ROOT does not point to a folder: {ROOT}")
def load_metadata(name, revision=None):
    if Path(name).name != name:
        raise ValueError("Metadata name must be a file name.")
    selected_revision = revision or os.environ.get("UC_METADATA_BASE_SHA")
    if selected_revision:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", selected_revision):
            raise ValueError("Metadata revision must be a full commit SHA.")
        try:
            return json.loads(run_git("show", f"{selected_revision}:config/{name}"))
        except subprocess.CalledProcessError:
            raise FileNotFoundError(
                f"Metadata {name} is unavailable at revision {selected_revision}."
            ) from None
    with (ROOT / "config" / name).open(encoding="utf-8") as handle:
        return json.load(handle)
def run_git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, errors="replace")
def get_changed_files(base_sha, head_sha):
    changed=[]
    for line in run_git("diff","--name-status","--find-renames",base_sha,head_sha).splitlines():
        fields=line.split("\t"); path=fields[-1]
        normalized_path = PurePosixPath(path.replace("\\", "/"))
        if "__pycache__" in normalized_path.parts or normalized_path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        changed.append({"status":fields[0],"path":path,"patch":run_git("diff","--unified=3",base_sha,head_sha,"--",path)})
    return changed
def write_text(path, content): Path(path).write_text(content,encoding="utf-8")
def write_json(path, content): Path(path).write_text(json.dumps(content,indent=2),encoding="utf-8")
