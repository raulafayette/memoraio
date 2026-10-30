"""Sandbox-only payment ledger. No production charges or client-side approval."""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid

ALLOWED_PRODUCTS={'owned_media_tools_48h'}

def b64(raw):return base64.urlsafe_b64encode(raw).decode().rstrip('=')

class SandboxProvider:
    """In-memory provider simulator; its QR string is deliberately not payable."""
    name='simulator'
    def __init__(self):self.records={}
    def create(self,reference,amount_cents):
        pid='sandbox_'+uuid.uuid4().hex
        self.records[pid]={'id':pid,'reference':reference,'amount_cents':amount_cents,'currency':'BRL','status':'pending','paid_at':None,'live_mode':False}
        return {**self.records[pid],'copy_paste':'TESTE-SEM-VALOR-FINANCEIRO:'+pid,'qr_code':None}
    def lookup(self,pid):return dict(self.records[pid])
    def simulate(self,pid,status,now):
        if status not in ('approved','refunded','cancelled','pending'):raise ValueError('Estado inválido')
        self.records[pid]['status']=status
        if status=='approved' and self.records[pid]['paid_at'] is None:self.records[pid]['paid_at']=now

class Ledger:
    def __init__(self,path,provider,webhook_secret,signing_key,clock=time.time):
        if provider.name!='simulator':raise ValueError('Cobrança externa desativada nesta versão')
        if len(webhook_secret)<32:raise ValueError('Segredo de webhook insuficiente')
        self.path=path;self.provider=provider;self.secret=webhook_secret;self.signing_key=signing_key;self.clock=clock
        with self.connect() as c:c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,device TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),device TEXT NOT NULL,request_key TEXT NOT NULL,product TEXT NOT NULL,amount_cents INTEGER NOT NULL,currency TEXT NOT NULL,provider_id TEXT UNIQUE,status TEXT NOT NULL,paid_at REAL,expires_at REAL,UNIQUE(user_id,request_key));
        CREATE TABLE IF NOT EXISTS webhook_events(provider TEXT,event_id TEXT,at REAL,PRIMARY KEY(provider,event_id));
        CREATE TABLE IF NOT EXISTS daily_usage(user_id TEXT,day TEXT,item_id TEXT,at REAL,PRIMARY KEY(user_id,day,item_id));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at REAL,kind TEXT,reference TEXT);
        ''')
    def connect(self):
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA synchronous=FULL');return c
    def register(self,device):
        if not isinstance(device,str) or not 16<=len(device)<=200:raise ValueError('Identificador de instalação inválido')
        token=secrets.token_urlsafe(32);uid=uuid.uuid4().hex
        with self.connect() as c:c.execute('INSERT INTO users VALUES(?,?,?)',(uid,hashlib.sha256(token.encode()).hexdigest(),device))
        return {'user_id':uid,'token':token}
    def authenticate(self,token):
        with self.connect() as c:r=c.execute('SELECT * FROM users WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not r:raise PermissionError('Autenticação inválida')
        return dict(r)
    def create(self,token,key,product='owned_media_tools_48h'):
        user=self.authenticate(token)
        if product not in ALLOWED_PRODUCTS:raise ValueError('Produto sem viabilidade comercial aprovada')
        if not isinstance(key,str) or not 16<=len(key)<=128:raise ValueError('Chave de idempotência inválida')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous=c.execute('SELECT * FROM orders WHERE user_id=? AND request_key=?',(user['id'],key)).fetchone()
            if previous:return dict(previous)
            pending=c.execute("SELECT id FROM orders WHERE user_id=? AND status='pending'",(user['id'],)).fetchone()
            if pending:raise ValueError('Já existe cobrança pendente; reutilize ou cancele antes de criar outra')
            oid=uuid.uuid4().hex;amount=1990 # Test-only hypothesis, never a real advertised price.
            # Simulator creation is local and deterministic from server ownership. A live adapter
            # must instead persist a pending order/outbox before its external idempotent request.
            charge=self.provider.create(oid,amount)
            c.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?)',(oid,user['id'],user['device'],key,product,amount,'BRL',charge['id'],'pending',None,None))
            c.execute('INSERT INTO audit(at,kind,reference) VALUES(?,?,?)',(self.clock(),'sandbox_charge_created',oid))
            return dict(c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone())
    def signature(self,raw,timestamp):
        return hmac.new(self.secret,str(timestamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    def webhook(self,raw,timestamp,signature):
        now=self.clock()
        if abs(now-float(timestamp))>300 or not hmac.compare_digest(self.signature(raw,timestamp),signature):raise PermissionError('Webhook não autenticado ou expirado')
        payload=json.loads(raw);event=payload['event_id'];pid=payload['payment_id']
        if not isinstance(event,str) or len(event)>200:raise ValueError('Evento inválido')
        # Payload status, value, user and approval page are deliberately ignored.
        payment=self.provider.lookup(pid)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM webhook_events WHERE provider=? AND event_id=?',(self.provider.name,event)).fetchone():return 'duplicate'
            order=c.execute('SELECT * FROM orders WHERE provider_id=?',(pid,)).fetchone()
            if not order or payment['reference']!=order['id'] or payment['amount_cents']!=order['amount_cents'] or payment['currency']!=order['currency'] or payment['live_mode']:raise ValueError('Pagamento não corresponde ao pedido sandbox')
            status=payment['status']
            if status not in ('pending','approved','refunded','cancelled'):raise ValueError('Estado do provedor não suportado')
            paid=payment['paid_at']
            if status=='approved' and (not isinstance(paid,(int,float)) or paid>now+60):raise ValueError('Data de confirmação inválida')
            if order['status'] in ('refunded','cancelled') and status=='approved':raise ValueError('Reaprovação requer conciliação manual')
            expires=(paid+48*3600) if status=='approved' else None
            c.execute('UPDATE orders SET status=?,paid_at=?,expires_at=? WHERE id=?',(status,paid,expires,order['id']))
            c.execute('INSERT INTO webhook_events VALUES(?,?,?)',(self.provider.name,event,now))
            c.execute('INSERT INTO audit(at,kind,reference) VALUES(?,?,?)',(now,'provider_verified_'+status,order['id']))
        return status
    def entitlement(self,token):
        user=self.authenticate(token);now=self.clock()
        with self.connect() as c:r=c.execute("SELECT * FROM orders WHERE user_id=? AND device=? AND status='approved' AND expires_at>? ORDER BY expires_at DESC LIMIT 1",(user['id'],user['device'],now)).fetchone()
        return {'plan':'temporary' if r else 'free','user_id':user['id'],'device':user['device'],'issued_at':now,'expires_at':r['expires_at'] if r else now,'daily_limit':None if r else 10,'product':r['product'] if r else 'free','order_id':r['id'] if r else None}
    def signed_license(self,token):
        payload=self.entitlement(token);raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
        return {'payload':b64(raw),'signature':b64(self.signing_key.sign(raw)),'algorithm':'Ed25519','warning':'Licença sandbox; a confirmação online é necessária para revogação imediata.'}
    def consume(self,token,item_id):
        from datetime import datetime,timezone
        if not isinstance(item_id,str) or not 1<=len(item_id)<=200:raise ValueError('Conteúdo inválido')
        rights=self.entitlement(token);day=datetime.fromtimestamp(self.clock(),timezone.utc).date().isoformat()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM daily_usage WHERE user_id=? AND day=? AND item_id=?',(rights['user_id'],day,item_id)).fetchone():return True
            used=c.execute('SELECT count(*) FROM daily_usage WHERE user_id=? AND day=?',(rights['user_id'],day)).fetchone()[0]
            if rights['daily_limit'] is not None and used>=rights['daily_limit']:return False
            c.execute('INSERT INTO daily_usage VALUES(?,?,?,?)',(rights['user_id'],day,item_id,self.clock()))
        return True

def verify_license(public_key,license,device,server_now):
    raw=base64.urlsafe_b64decode(license['payload']+'='*(-len(license['payload'])%4));signature=base64.urlsafe_b64decode(license['signature']+'='*(-len(license['signature'])%4))
    public_key.verify(signature,raw);claims=json.loads(raw)
    if claims['device']!=device or claims['expires_at']<=server_now:raise PermissionError('Licença expirada ou de outra instalação')
    return claims
