"""Build the AppKit/WKWebView shell using Apple's SDK. No private data bundled."""
from pathlib import Path
import plistlib
import json
import subprocess
root=Path(__file__).resolve().parent.parent
brand=json.loads((root/'branding.json').read_text())
bundle=root/(brand['name']+'.app');contents=bundle/'Contents';binary=contents/'MacOS'/'MemoriaDesktop';binary.parent.mkdir(parents=True,exist_ok=True);(contents/'Resources').mkdir(exist_ok=True)
subprocess.run(['xcrun','swiftc','-swift-version','5','-target','arm64-apple-macosx14.0','-module-cache-path','/private/tmp/memoria-swift-modules','-O','-framework','AppKit','-framework','WebKit','-framework','UserNotifications',str(root/'macos'/'Memoria.swift'),'-o',str(binary)],check=True)
settings={'CFBundleName':brand['name'],'CFBundleDisplayName':brand['name'],'CFBundleExecutable':'MemoriaDesktop','CFBundleIdentifier':'local.memoria.desktop','CFBundleVersion':'3','CFBundleShortVersionString':'0.3.0','CFBundlePackageType':'APPL','NSHighResolutionCapable':True,'LSMinimumSystemVersion':'14.0','NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},'CFBundleIconFile':'AppIcon'}
(contents/'Info.plist').write_bytes(plistlib.dumps(settings))
iconset=Path('/private/tmp/memoria-app.iconset')
subprocess.run(['xcrun','swift','-module-cache-path','/private/tmp/memoria-swift-modules',str(root/'macos'/'Icon.swift'),str(iconset)],check=True)
subprocess.run(['/usr/bin/iconutil','-c','icns',str(iconset),'-o',str(contents/'Resources'/'AppIcon.icns')],check=True)
subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(bundle)],check=True)
print(bundle)
