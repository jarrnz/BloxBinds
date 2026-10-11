"""Allowlisted release ZIPs, audited first; never publishes or includes .git."""
import hashlib
import argparse
from pathlib import Path
import sys
import zipfile
from audit_release import ROOT, public_files, audit_source, audit_exe
sys.path.insert(0,str(ROOT))
from bloxbinds import __version__
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--exe",type=Path,default=ROOT/"dist"/"BloxBinds.exe")
parser.add_argument("--output-dir",type=Path)
args=parser.parse_args()
exe=args.exe.resolve()
destination=(args.output_dir or exe.parent).resolve()
destination.mkdir(parents=True,exist_ok=True)
issues=audit_source()+audit_exe(exe)[0]
if issues:raise SystemExit("Privacy audit failed; packaging stopped.")
artifacts=[]
for suffix in ("Windows-x64","source"):
    path=destination/(f"BloxBinds-Release-{__version__}-Windows-x64.zip" if suffix=="Windows-x64" else f"BloxBinds-{__version__}-source.zip")
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
        if suffix=="source":
            members=public_files()
        else:
            members=[exe]+[ROOT/name for name in ("README.md","LICENSE","PRIVACY_AUDIT.md")]
            members += [p for p in public_files() if p.relative_to(ROOT).parts[0]=="third_party"]
        for member in members:
            name=member.name if member==exe else str(member.relative_to(ROOT)).replace("\\","/")
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=0
            info.external_attr=0
            archive.writestr(info,member.read_bytes())
    artifacts.append(path)
artifacts.append(exe)
(destination/"SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in artifacts),encoding="ascii")
for p in artifacts:print(p.name,p.stat().st_size,"bytes")
