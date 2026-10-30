"""Fail-closed file/credential screen. Run in a fresh public source export."""
import json,re,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
patterns=[re.compile(p) for p in (r'ghp_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{40,}',r'AIza[0-9A-Za-z_-]{30,}',r'sk-[A-Za-z0-9_-]{24,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'/'+'Users'+r'/[^/\s]+/')]
forbidden={'.sqlite','.sqlite3','.db','.mp4','.mkv','.mp3','.m4a','.wav','.safetensors','.gguf','.pem','.p12','.key'}
deny_dirs={'data','originals','transcripts','models','downloads','.venv','.service-venv','licensing-data','node_modules'}
errors=[];scanned=0
paths=(root/p.decode() for p in subprocess.check_output(['git','ls-files','-z'],cwd=root).split(b'\0') if p) if '--tracked' in sys.argv else root.rglob('*')
for path in paths:
 rel=path.relative_to(root)
 if '.git' in rel.parts:continue
 if path.is_symlink():errors.append({'path':str(rel),'reason':'symlink not permitted'});continue
 if not path.is_file():continue
 if any(part in deny_dirs for part in rel.parts) or path.suffix.lower() in forbidden or path.name.endswith('.cookies.txt') or (path.name.startswith('.env') and path.name!='.env.example'):
  errors.append({'path':str(rel),'reason':'private artifact class'});continue
 if path.stat().st_size>5*1024*1024:errors.append({'path':str(rel),'reason':'unexpected large source file'});continue
 raw=path.read_bytes()
 try:text=raw.decode('utf-8')
 except UnicodeDecodeError:errors.append({'path':str(rel),'reason':'binary not allowlisted for source export'});continue
 scanned+=1
 for n,pattern in enumerate(patterns):
  if pattern.search(text):errors.append({'path':str(rel),'reason':'sensitive pattern '+str(n)})
history_commits=0
history_blobs=0
if '--history' in sys.argv:
 commits=subprocess.check_output(['git','rev-list','--all'],cwd=root,text=True).splitlines()
 seen=set()
 for commit in commits:
  history_commits+=1
  emails=subprocess.check_output(['git','show','-s','--format=%ae%x00%ce',commit],cwd=root,text=True).strip().split('\0')
  if any(not re.fullmatch(r'[^@\s]+@users\.noreply\.github\.com|noreply@github\.com',email) for email in emails):
   errors.append({'path':'commit:'+commit,'reason':'commit email is not a GitHub privacy address'})
  raw=subprocess.check_output(['git','ls-tree','-rz','--full-tree',commit],cwd=root)
  for entry in raw.split(b'\0'):
   if not entry:continue
   header,name=entry.split(b'\t',1);mode,kind,oid=header.split();rel=Path(name.decode())
   if mode==b'120000' or mode==b'160000' or any(part in deny_dirs for part in rel.parts) or rel.suffix.lower() in forbidden or rel.name.endswith('.cookies.txt') or (rel.name.startswith('.env') and rel.name!='.env.example'):
    errors.append({'path':str(rel),'reason':'private artifact or link in history'})
   if kind!=b'blob' or oid in seen:continue
   seen.add(oid);history_blobs+=1
   blob=subprocess.check_output(['git','cat-file','blob',oid.decode()],cwd=root)
   try:old_text=blob.decode('utf-8')
   except UnicodeDecodeError:
    errors.append({'path':str(rel),'reason':'unexpected binary in source history'});continue
   for n,pattern in enumerate(patterns):
    if pattern.search(old_text):errors.append({'path':str(rel),'reason':'sensitive pattern in history '+str(n)})
print(json.dumps({'history_commits':history_commits,'history_blobs':history_blobs,'files_scanned' :scanned,'passed':not errors,'findings':errors},ensure_ascii=False,indent=2))
raise SystemExit(1 if errors else 0)
