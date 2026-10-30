import re
from pathlib import PurePosixPath
SEVERITY_ORDER={"Low":1,"Medium":2,"High":3,"Critical":4}
COMMENT_PREFIXES=("//","#","--","/*","*","*/")
def changed_content_lines(patch):
    result=[]
    for line in patch.splitlines():
        if line.startswith(("+++","---","@@")): continue
        if line.startswith(("+","-")) and line[1:].strip(): result.append(line[1:].strip())
    return result
def is_comment_only(path,patch):
    lines=changed_content_lines(patch)
    if not lines:return False
    if PurePosixPath(path).suffix.lower() in {".md",".txt",".rst"}:return True
    return all(line.startswith(COMMENT_PREFIXES) or line in {"{","}"} for line in lines)
def dropped_columns(patch):
    found=[]
    patterns=[r"(?i)\bdrop\s+column\s+[\[\"`]?([a-z_][\w]*)",r"(?i)^-\s*[\[\"`]?([a-z_][\w]*)[\]\"`]?\s+(?:int|bigint|varchar|nvarchar|text|date|datetime|decimal|bit|uuid)\b"]
    for raw in patch.splitlines():
        for pattern in patterns:
            match=re.search(pattern,raw)
            if match:found.append(match.group(1).lower())
    return sorted(set(found))
def is_api_breaking_change(path,patch):
    if PurePosixPath(path).suffix.lower() not in {".cs",".py",".js",".ts",".java",".go",".yaml",".yml",".json"}:return False
    deleted="\n".join(line[1:] for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
    return bool(re.search(r"(?i)(httpget|httppost|route|app\.(get|post|put|delete)|router\.|public\s+.*\(|def\s+\w+\(|interface\s+\w+)",deleted))
def highest_severity(findings):
    return max((item["severity"] for item in findings),key=SEVERITY_ORDER.get,default="Low")
