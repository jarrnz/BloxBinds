"""Inspect only trusted local builds. No identifiers are printed in audit reports."""
import argparse
import getpass
import io
import marshal
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import types
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={"README.md","LICENSE","TEST_RESULTS.md","PRIVACY_AUDIT.md","RELEASE_NOTES.md","requirements.txt",
            "requirements-build.txt",".gitignore","main.py"}
PUBLIC_DIRS={"bloxbinds","tests","scripts",".github","third_party"}
SUFFIXES={".py",".txt",".md",".yml",".yaml",".terms"}


def public_files():
    files=[ROOT/name for name in ROOT_FILES if (ROOT/name).is_file()]
    for directory in PUBLIC_DIRS:
        files.extend(p for p in (ROOT/directory).rglob("*") if p.is_file() and p.suffix in SUFFIXES
                     and "__pycache__" not in p.parts)
    return sorted(files)


def identifiers():
    values={getpass.getuser(),os.environ.get("COMPUTERNAME","")}
    for key in ("user.name","user.email"):
        result=subprocess.run(["git","config","--global","--get",key],cwd=ROOT,capture_output=True,text=True)
        if result.returncode==0:values.add(result.stdout.strip())
    return [v for v in values if len(v)>3 and v.lower() not in {"wirru","github-actions[bot]","runneradmin"}]


def sensitive(data, values, *, paths=True):
    folded=data.lower()
    for value in values:
        if any(value.lower().encode(encoding) in folded for encoding in ("utf-8","utf-16le")):
            return True
    if not paths:
        return False
    # Account directories in project files are blocked; upstream runtime paths are separately reported.
    return bool(re.search(rb"[a-z]:[\\/]users[\\/]",folded) or
                re.search(rb"[a-z]\x00:\x00[\\/]\x00u\x00s\x00e\x00r\x00s\x00[\\/]\x00",folded))


def code_objects(code):
    yield code
    for item in code.co_consts:
        if isinstance(item,types.CodeType):yield from code_objects(item)


def audit_code(code, label, values, problems):
    for obj in code_objects(code):
        filename=obj.co_filename
        if PureWindowsPath(filename).is_absolute() or filename.startswith("/"):
            problems.append(label+": absolute Python code filename")
            break
    if sensitive(marshal.dumps(code),values,paths=False):problems.append(label+": local identity in code")


def audit_source(values=None):
    values=identifiers() if values is None else values
    return [str(p.relative_to(ROOT))+": local identity/path" for p in public_files() if sensitive(p.read_bytes(),values)]


def audit_exe(path, values=None):
    from PyInstaller.archive.readers import CArchiveReader
    values=identifiers() if values is None else values
    problems=[]
    if sensitive(path.read_bytes(),values,paths=False):problems.append("executable: local identity/path in raw bytes")
    archive=CArchiveReader(str(path))
    module_count=0
    runtime_path_matches=0
    import pefile
    pe=pefile.PE(str(path))
    version={}
    for block in getattr(pe,"FileInfo",[]):
        for item in block:
            for table in getattr(item,"StringTable",[]):version.update(table.entries)
    pe.close()
    if version.get(b"CompanyName") != b"wirru" or version.get(b"ProductName") != b"BloxBinds":
        problems.append("executable: unexpected developer/product version metadata")
    for name,entry in archive.toc.items():
        data=archive.extract(name)
        kind=entry[-1]
        if sensitive(data,values,paths=False):problems.append("bundle member "+name+": local identity/path")
        if kind=="b":
            runtime_path_matches += len(re.findall(rb"[a-z]:[\\/]users[\\/]",data.lower()))
        elif kind not in ("z",) and not name.endswith("base_library.zip") and sensitive(data,[],paths=True):
            problems.append("bundle member "+name+": unexpected account path in application/data")
        if kind in ("s","m","M"):
            audit_code(marshal.loads(data),name,values,problems);module_count+=1
        elif kind=="z":
            pyz=archive.open_embedded_archive(name)
            for module in pyz.toc:
                code=pyz.extract(module)
                if isinstance(code,types.CodeType):
                    audit_code(code,module,values,problems);module_count+=1
        elif name.endswith("base_library.zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as library:
                for member in library.namelist():
                    if member.endswith(".pyc"):
                        audit_code(marshal.loads(library.read(member)[16:]),member,values,problems);module_count+=1
    return problems,module_count,runtime_path_matches


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe",type=Path)
    args=parser.parse_args()
    problems=audit_source()
    count=0
    upstream=0
    if args.exe:
        extra,count,upstream=audit_exe(args.exe);problems.extend(extra)
    if problems:
        for problem in sorted(set(problems)):print(problem)
        return 1
    print(f"Privacy scan passed: {len(public_files())} public files; {count} bundled code modules; no scanned local developer identifiers; relative bundled Python code filenames.")
    if upstream:
        print(f"Audit limitation: {upstream} account-directory references remain in upstream runtime binaries, not the local developer identity. See PRIVACY_AUDIT.md.")
    print("Static audit does not guarantee anonymity. Configure an actual GitHub noreply address before public commits.")
    return 0

if __name__=="__main__":raise SystemExit(main())
