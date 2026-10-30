"""Inventory actual installed Python distributions without exporting machine paths."""
import importlib.metadata as m,json
from pathlib import Path
records=[]
for d in sorted(m.distributions(),key=lambda d:d.metadata.get('Name','').lower()):
 data=d.metadata;files=[str(p) for p in (d.files or []) if ('license' in str(p).lower() or 'copying' in str(p).lower()) and '.dist-info/' in str(p)]
 records.append({'name':data.get('Name'),'version':d.version,'license_expression':data.get('License-Expression'),'declared_license':data.get('License'),'classifiers':[v for v in data.get_all('Classifier',[]) if v.startswith('License ::')],'license_files':[p.split('.dist-info/',1)[1] for p in files],'requires':data.get_all('Requires-Dist',[])})
out=Path('docs/dependencies-v3.json');out.write_text(json.dumps({'scope':'Installed runtime distributions; declarations are evidence, not a legal compatibility opinion. Native binaries need a separate audit.','distributions':records},ensure_ascii=False,indent=2))
unknown=[d['name'] for d in records if not (d['license_expression'] or d['declared_license'] or d['classifiers'] or d['license_files'])]
print(json.dumps({'distributions':len(records),'missing_license_evidence':unknown,'output':str(out)}))
