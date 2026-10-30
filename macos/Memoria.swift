import AppKit
import WebKit
import UserNotifications

final class App: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    let productName = Bundle.main.object(forInfoDictionaryKey:"CFBundleDisplayName") as? String ?? "Memoraio"
    var web: WKWebView!
    var endpoint: URL?
    var poll: Timer?
    let http = URLSession(configuration:.ephemeral)
    var lastCount: Int?
    var instagramLogin: InstagramLogin?
    let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/MemoriaAudiovisual")
    func applicationDidFinishLaunching(_ notification: Notification) {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .nonPersistent()
        cfg.userContentController.add(self,name:"appearance")
        cfg.userContentController.add(self,name:"instagramConnect")
        cfg.userContentController.add(self,name:"openDirectory")
        cfg.userContentController.add(self,name:"chooseDirectory")
        web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = self; web.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x:0,y:0,width:1180,height:800), styleMask:[.titled,.closable,.miniaturizable,.resizable], backing:.buffered,defer:false)
        window.title = "Biblioteca"; window.minSize = NSSize(width:650,height:450)
        window.contentView = web; window.delegate = self; window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("BibliotecaPrincipal"); window.center()
        menus(); show(); connect()
        poll = Timer.scheduledTimer(withTimeInterval:10,repeats:true) { [weak self] _ in self?.status() }
    }
    func userContentController(_ userContentController:WKUserContentController,didReceive message:WKScriptMessage) {
        let origin=message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame,origin.protocol=="http",origin.host=="127.0.0.1",origin.port==endpoint?.port else{return}
        if ["openDirectory","chooseDirectory"].contains(message.name),let body=message.body as? [String:Any],let id=body["id"] as? String,id.count<=80,id.allSatisfy({$0.isLetter || $0.isNumber || $0=="_" || $0=="-"}) {
            if message.name=="openDirectory" {
                request("/api/directory?id="+id) { [weak self] data in
                    guard let data=data,let json=try? JSONSerialization.jsonObject(with:data) as? [String:Any],let path=json["path"] as? String else {self?.web.evaluateJavaScript("notice('A pasta não está disponível. Confira o destino nos Ajustes.')");return}
                    NSWorkspace.shared.open(URL(fileURLWithPath:path,isDirectory:true))
                }
            } else {
                let panel=NSOpenPanel();panel.canChooseDirectories=true;panel.canChooseFiles=false;panel.allowsMultipleSelection=false;panel.canCreateDirectories=true;panel.prompt="Usar esta pasta";panel.message=id.isEmpty ? "Pasta padrão das transcrições" : "Pasta de transcrições deste canal"
                panel.beginSheetModal(for:window) { [weak self] result in
                    guard result == .OK,let path=panel.url?.path else{return}
                    let payload:[String:Any]=id.isEmpty ? ["transcript_directory":path] : ["id":id,"directory":path]
                    self?.request(id.isEmpty ? "/api/preferences" : "/api/channel-directory",payload) {data in
                        self?.web.evaluateJavaScript(data == nil ? "notice('Não foi possível usar esta pasta. Escolha uma pasta pessoal ou de um disco externo disponível.')" : "directoriesChanged()")
                    }
                }
            }
            return
        }
        if message.name=="instagramConnect" {
            if instagramLogin==nil {instagramLogin=InstagramLogin(owner:self)}
            instagramLogin?.show();return
        }
        guard message.name=="appearance",let choice=message.body as? String else{return}
        if choice=="dark" {window.appearance=NSAppearance(named:.darkAqua)}
        else if choice=="light" {window.appearance=NSAppearance(named:.aqua)}
        else if choice=="system" {window.appearance=nil}
        instagramLogin?.window.appearance=window.appearance
    }
    func item(_ menu:NSMenu,_ title:String,_ action:Selector,_ key:String="") {
        let i=NSMenuItem(title:title,action:action,keyEquivalent:key);i.target=self;menu.addItem(i)
    }
    func menus() {
        let root=NSMenu();NSApp.mainMenu=root
        func menu(_ name:String)->NSMenu { let i=NSMenuItem();let m=NSMenu(title:name);i.submenu=m;root.addItem(i);return m }
        let app=menu(productName)
        item(app,"Sobre \(productName)",#selector(about));app.addItem(.separator())
        item(app,"Ajustes…",#selector(settings),",")
        item(app,"Ativar notificações…",#selector(notifications));app.addItem(.separator())
        item(app,"Ocultar \(productName)",#selector(hide),"h")
        item(app,"Mostrar biblioteca",#selector(show),"0");app.addItem(.separator())
        item(app,"Sair da interface (manter tarefas)",#selector(quit),"q")
        item(app,"Sair completamente",#selector(quitAll))
        let file=menu("Arquivo");item(file,"Fechar janela",#selector(close),"w")
        let edit=menu("Editar")
        for (t,a,k) in [("Desfazer","undo:","z"),("Recortar","cut:","x"),("Copiar","copy:","c"),("Colar","paste:","v"),("Selecionar tudo","selectAll:","a")] { edit.addItem(withTitle:t,action:Selector(a),keyEquivalent:k) }
        let view=menu("Visualizar");item(view,"Atualizar",#selector(connect),"r");item(view,"Aumentar texto",#selector(zoomIn),"+");item(view,"Diminuir texto",#selector(zoomOut),"-")
        let full=NSMenuItem(title:"Entrar em tela cheia",action:#selector(NSWindow.toggleFullScreen(_:)),keyEquivalent:"f");full.keyEquivalentModifierMask=[.control,.command];view.addItem(full)
        let process=menu("Tarefas");item(process,"Pausar processamento",#selector(pause));item(process,"Retomar processamento",#selector(resume))
        let win=menu("Janela");NSApp.windowsMenu=win
        win.addItem(withTitle:"Minimizar",action:#selector(NSWindow.performMiniaturize(_:)),keyEquivalent:"m")
        win.addItem(withTitle:"Zoom",action:#selector(NSWindow.performZoom(_:)),keyEquivalent:"")
        item(win,"Mostrar biblioteca",#selector(show))
        let help=menu("Ajuda");item(help,"Execução em segundo plano",#selector(helpInfo))
    }
    @objc func show() { window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true) }
    @objc func close() { window.performClose(nil) }
    @objc func hide() { NSApp.hide(nil) }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func about() { NSApp.orderFrontStandardAboutPanel(options:[.applicationName:productName,.applicationVersion:"0.3",.credits:NSAttributedString(string:"Biblioteca audiovisual local. Nome de trabalho.")]) }
    @objc func settings() { web.evaluateJavaScript("go('settings')") }
    @objc func zoomIn() { web.pageZoom=min(2.5,web.pageZoom+0.1) }
    @objc func zoomOut() { web.pageZoom=max(0.8,web.pageZoom-0.1) }
    @objc func helpInfo() { message("Tarefas em segundo plano","Fechar a janela, ocultar ou sair da interface mantém as tarefas do serviço instalado. Pausar interrompe tarefas em execução e preserva retomadas. Sair completamente encerra o serviço até a próxima abertura ou login. Suspender ou desligar o Mac interrompe a execução.") }
    func message(_ title:String,_ text:String) { let a=NSAlert();a.messageText=title;a.informativeText=text;a.runModal() }
    func runAgent(_ action:String) {
        let agent=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/local.memoria.audiovisual.plist")
        guard FileManager.default.fileExists(atPath:agent.path) else {return}
        let p=Process();p.executableURL=URL(fileURLWithPath:"/bin/launchctl");p.arguments=[action,"gui/\(getuid())",agent.path];p.standardOutput=FileHandle.nullDevice;p.standardError=FileHandle.nullDevice
        try? p.run();p.waitUntilExit()
    }
    @objc func connect() {
        web.loadHTMLString("<html><body style='font:17px system-ui;padding:40px'><h1>Preparando a biblioteca</h1><p>Conectando ao serviço local…</p></body></html>",baseURL:nil)
        connectAttempt(0)
    }
    func connectAttempt(_ attempt:Int) {
        if attempt==0 { runAgent("bootstrap") }
        guard attempt<20 else { message("Serviço local indisponível","Instale o serviço pela pasta do projeto e use Visualizar → Atualizar. O catálogo e as tarefas permanecem no disco.");return }
        guard let data=try? Data(contentsOf:support.appendingPathComponent("ui-session.json")),let json=try? JSONSerialization.jsonObject(with:data) as? [String:Any],let raw=json["url"] as? String,let url=URL(string:raw),url.scheme=="http",url.host=="127.0.0.1",url.port != nil else {
            DispatchQueue.main.asyncAfter(deadline:.now()+1){self.connectAttempt(attempt+1)};return
        }
        // Probe without following the bootstrap redirect or sharing cookies externally.
        var request=URLRequest(url:url);request.timeoutInterval=2
        http.dataTask(with:request){data,response,error in
            DispatchQueue.main.async {
                if error==nil,let response=response as? HTTPURLResponse,response.statusCode==200 {
                    self.endpoint=url;self.web.load(URLRequest(url:url))
                } else { DispatchQueue.main.asyncAfter(deadline:.now()+1){self.connectAttempt(attempt+1)} }
            }
        }.resume()
    }
    func request(_ path:String,_ body:[String:Any]?=nil,_ completion:((Data?)->Void)?=nil) {
        guard let ep=endpoint,let parts=URLComponents(url:ep,resolvingAgainstBaseURL:false),let token=parts.queryItems?.first(where:{$0.name=="token"})?.value,let url=URL(string:path,relativeTo:ep)?.absoluteURL else{return}
        var req=URLRequest(url:url);req.timeoutInterval=8;req.setValue("memoria=\(token)",forHTTPHeaderField:"Cookie")
        if let body=body {req.httpMethod="POST";req.setValue("application/json",forHTTPHeaderField:"Content-Type");req.setValue("http://127.0.0.1:\(ep.port!)",forHTTPHeaderField:"Origin");req.httpBody=try? JSONSerialization.data(withJSONObject:body)}
        http.dataTask(with:req) {data,response,error in
            let ok=(response as? HTTPURLResponse)?.statusCode==200 && error==nil
            DispatchQueue.main.async {completion?(ok ? data : nil)}
        }.resume()
    }
    @objc func pause() {request("/api/service",["paused":true,"interrupt_running":true]) { [weak self] _ in self?.web.evaluateJavaScript("notice('Processamento pausado; arquivos de retomada preservados.')") }}
    @objc func resume() {request("/api/service",["paused":false]) { [weak self] _ in self?.web.evaluateJavaScript("notice('Processamento retomado.')") }}
    @objc func quitAll() { runAgent("bootout"); NSApp.terminate(nil) }
    @objc func notifications() {
        UNUserNotificationCenter.current().requestAuthorization(options:[.alert,.sound]) { granted,_ in UserDefaults.standard.set(granted,forKey:"notifications") }
    }
    func status() {
        request("/api/state") {[weak self] data in
            guard let self=self,let data=data,let json=try? JSONSerialization.jsonObject(with:data) as? [String:Any],let stats=json["stats"] as? [String:Any],let count=stats["transcripts"] as? Int else{return}
            if let last=self.lastCount,count>last,UserDefaults.standard.bool(forKey:"notifications") {
                let content=UNMutableNotificationContent();content.title="Transcrições disponíveis";content.body="\(count-last) novo(s) conteúdo(s) na biblioteca."
                UNUserNotificationCenter.current().add(UNNotificationRequest(identifier:"transcripts",content:content,trigger:nil))
            }
            self.lastCount=count
            // No token, source title or private path is written in this health receipt.
            let health:[String:Any]=["native":true,"at":Date().timeIntervalSince1970,"web_loaded":self.web.url?.host=="127.0.0.1","transcripts":count]
            if let out=try? JSONSerialization.data(withJSONObject:health) {try? out.write(to:self.support.appendingPathComponent("native-health.json"),options:.atomic)}
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {false}
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows:Bool)->Bool {show();connect();return true}
    func webView(_ webView:WKWebView,decidePolicyFor action:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void) {
        guard let url=action.request.url else{decisionHandler(.cancel);return}
        if url.scheme=="about",url.absoluteString=="about:blank" {decisionHandler(.allow);return}
        if let ep=endpoint,url.scheme=="http",url.host=="127.0.0.1",url.port==ep.port {decisionHandler(action.shouldPerformDownload ? .download : .allow);return}
        if action.navigationType == .linkActivated,url.scheme=="https" {NSWorkspace.shared.open(url)}
        decisionHandler(.cancel)
    }
    func webView(_ webView:WKWebView,decidePolicyFor response:WKNavigationResponse,decisionHandler:@escaping(WKNavigationResponsePolicy)->Void) {
        if let r=response.response as? HTTPURLResponse,r.value(forHTTPHeaderField:"Content-Disposition")?.contains("attachment") == true {decisionHandler(.download)} else{decisionHandler(.allow)}
    }
    func webView(_ webView:WKWebView,navigationAction:WKNavigationAction,didBecome download:WKDownload) {download.delegate=self}
    func webView(_ webView:WKWebView,navigationResponse:WKNavigationResponse,didBecome download:WKDownload) {download.delegate=self}
    func download(_ download:WKDownload,decideDestinationUsing response:URLResponse,suggestedFilename:String,completionHandler:@escaping(URL?)->Void) {
        let panel=NSSavePanel();panel.nameFieldStringValue=URL(fileURLWithPath:suggestedFilename).lastPathComponent
        panel.beginSheetModal(for:window) { result in completionHandler(result == .OK ? panel.url : nil) }
    }
    func webView(_ webView:WKWebView,createWebViewWith configuration:WKWebViewConfiguration,for action:WKNavigationAction,windowFeatures:WKWindowFeatures)->WKWebView? {
        if let url=action.request.url,url.scheme=="https" {NSWorkspace.shared.open(url)};return nil
    }
    func webView(_ webView:WKWebView,didFailProvisionalNavigation navigation:WKNavigation!,withError error:Error) {
        if (error as NSError).code != NSURLErrorCancelled {connectAttempt(0)}
    }
}
final class InstagramLogin: NSObject, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    weak var owner:App?
    let window:NSWindow
    let browser:WKWebView
    let info=NSTextField(wrappingLabelWithString:"Entre na sua conta na página oficial. Ao clicar em Usar sessão, os dados de acesso da sessão serão guardados somente neste Mac para os downloads que você solicitar. Conectar não inicia downloads.")
    let useButton=NSButton(title:"Usar sessão desta conta",target:nil,action:nil)
    init(owner:App) {
        self.owner=owner
        window=NSWindow(contentRect:NSRect(x:0,y:0,width:780,height:800),styleMask:[.titled,.closable,.resizable],backing:.buffered,defer:false)
        let config=WKWebViewConfiguration();config.websiteDataStore = .nonPersistent()
        browser=WKWebView(frame:.zero,configuration:config)
        super.init()
        window.title="Conectar Instagram";window.minSize=NSSize(width:600,height:560);window.isReleasedWhenClosed=false;window.delegate=self;window.appearance=owner.window.appearance
        let content=NSView();window.contentView=content
        browser.navigationDelegate=self;browser.uiDelegate=self
        browser.translatesAutoresizingMaskIntoConstraints=false;info.translatesAutoresizingMaskIntoConstraints=false;useButton.translatesAutoresizingMaskIntoConstraints=false
        info.font=NSFont.systemFont(ofSize:12);useButton.target=self;useButton.action=#selector(useSession);useButton.bezelStyle = .rounded
        content.addSubview(browser);content.addSubview(info);content.addSubview(useButton)
        NSLayoutConstraint.activate([browser.topAnchor.constraint(equalTo:content.topAnchor),browser.leadingAnchor.constraint(equalTo:content.leadingAnchor),browser.trailingAnchor.constraint(equalTo:content.trailingAnchor),browser.bottomAnchor.constraint(equalTo:info.topAnchor,constant:-14),info.leadingAnchor.constraint(equalTo:content.leadingAnchor,constant:20),info.trailingAnchor.constraint(equalTo:content.trailingAnchor,constant:-20),info.bottomAnchor.constraint(equalTo:useButton.topAnchor,constant:-10),useButton.trailingAnchor.constraint(equalTo:content.trailingAnchor,constant:-20),useButton.bottomAnchor.constraint(equalTo:content.bottomAnchor,constant:-16)])
        browser.load(URLRequest(url:URL(string:"https://www.instagram.com/accounts/login/")!));window.center()
    }
    func show(){window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)}
    func windowWillClose(_ notification:Notification){owner?.instagramLogin=nil}
    @objc func useSession(){
        useButton.isEnabled=false
        browser.configuration.websiteDataStore.httpCookieStore.getAllCookies {[weak self] cookies in
            guard let self=self else{return}
            var approved:[String:String]=[:]
            for cookie in cookies {
                let domain=cookie.domain.trimmingCharacters(in:CharacterSet(charactersIn:".")).lowercased()
                if (domain=="instagram.com" || domain.hasSuffix(".instagram.com")),["sessionid","csrftoken","ds_user_id"].contains(cookie.name){approved[cookie.name]=cookie.value}
            }
            guard approved["sessionid"] != nil,approved["csrftoken"] != nil else {self.info.stringValue="O login ainda não foi concluído. Entre na conta acima e depois clique em Usar sessão.";self.useButton.isEnabled=true;return}
            self.owner?.request("/api/instagram/session",["cookies":approved]) {[weak self] data in
                guard let self=self else{return}
                self.useButton.isEnabled=true
                if data != nil {self.owner?.web.evaluateJavaScript("notice('Sessão do Instagram salva neste Mac. Você pode escolher stories e destaques.'); refresh()");self.window.close()}
                else {self.info.stringValue="Não foi possível salvar a sessão no serviço local. Tente novamente; sua senha não é enviada ao serviço local."}
            }
        }
    }
    func webView(_ webView:WKWebView,decidePolicyFor action:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void){
        guard let url=action.request.url else{decisionHandler(.cancel);return}
        if url.absoluteString=="about:blank" {decisionHandler(.allow);return}
        guard url.scheme=="https",let host=url.host?.lowercased() else{decisionHandler(.cancel);return}
        if action.targetFrame?.isMainFrame == false {decisionHandler(.allow);return}
        guard host=="instagram.com" || host.hasSuffix(".instagram.com") || host=="facebook.com" || host.hasSuffix(".facebook.com") else{decisionHandler(.cancel);return}
        decisionHandler(.allow)
    }
    func webView(_ webView:WKWebView,createWebViewWith configuration:WKWebViewConfiguration,for action:WKNavigationAction,windowFeatures:WKWindowFeatures)->WKWebView?{browser.load(action.request);return nil}
}
let app=NSApplication.shared
let delegate=App();app.delegate=delegate;app.setActivationPolicy(.regular);app.run()
