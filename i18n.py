"""Local native-UI catalogs. Stored and structure-authored content is never translated.

Template literals are marked at compilation; business values are not passed through
a blanket response/DOM replacement. Keys, statuses, data and personal names stay
independent of the current request language.
"""
import html,json,re,time
from html.parser import HTMLParser
from pathlib import Path
from flask import Blueprint,abort,current_app,g,has_request_context,redirect,request,session,url_for
from flask.json.provider import DefaultJSONProvider
from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.visitor import NodeTransformer
from markupsafe import Markup,escape

ROOT=Path(__file__).resolve().parent
LANGUAGES={'fr':('Français','🇫🇷'),'en':('English','🇬🇧'),'de':('Deutsch','🇩🇪'),'es':('Español','🇪🇸'),'fi':('Suomi','🇫🇮')}
CATALOGS={code:{} for code in LANGUAGES}
PATTERNS_BY_LANGUAGE={code:[] for code in LANGUAGES}
for code,catalog in CATALOGS.items():
    if code=='fr':continue
    for path in sorted((ROOT/('translations/'+code)).glob('*.json')):
        catalog.update(json.loads(path.read_text()))
    for source,translated in catalog.items():
        fields=re.findall(r'\{(\d+)\}',source)
        if not fields:continue
        pieces=re.split(r'\{\d+\}',source)
        PATTERNS_BY_LANGUAGE[code].append((re.compile('([\\s\\S]*?)'.join(re.escape(p) for p in pieces)),fields,translated))
# Backward-compatible names for existing catalog tooling/tests.
CATALOG=CATALOGS['en'];PATTERNS=PATTERNS_BY_LANGUAGE['en']

def language():return getattr(g,'ui_language','fr') if has_request_context() else 'fr'
def t(message,*args,**kwargs):
    code=language()
    text=CATALOGS.get(code,{}).get(str(message),str(message))
    if code!='fr' and text==str(message):
        for pattern,fields,translated in PATTERNS_BY_LANGUAGE.get(code,[]):
            matched=pattern.fullmatch(str(message))
            if matched:
                values={index:value for index,value in zip(fields,matched.groups())}
                text=re.sub(r'\{(\d+)\}',lambda m:values.get(m[1],m.group()),translated);break
    return text.format(*args,**kwargs) if args or kwargs else text

def flash(message,*args,**kwargs):
    from flask import flash as original_flash
    return original_flash(t(message),*args,**kwargs)

class NativeText(str):
    def __html__(self):return escape(t(str.__str__(self)))

class NativeJSONProvider(DefaultJSONProvider):
    def dumps(self,obj,**kwargs):
        def convert(value):
            if isinstance(value,NativeText):return t(str(value))
            if isinstance(value,dict):return {key:convert(item) for key,item in value.items()}
            if isinstance(value,(list,tuple)):return [convert(item) for item in value]
            return value
        return super().dumps(convert(obj),**kwargs)

def native(value):return NativeText(value)
def natural(value):
    return isinstance(value,str) and bool(re.search(r'[A-Za-zÀ-ÿ]',value)) and (bool(re.search(r'[\sÀ-ÿ]',value)) or value[:1].isupper())

def static_html(value):
    def translate_text(match):
        text=match.group(0);plain=re.sub(r'\s+',' ',text).strip()
        if not plain:return text
        translated=t(plain)
        return text[:len(text)-len(text.lstrip())]+translated+text[len(text.rstrip()):]
    def attribute(match):
        prefix,quote,text=match.group(1,2,3)
        return prefix+quote+str(escape(t(text)))+quote
    parts=re.split(r'(<[^>]*>)',value)
    for i,part in enumerate(parts):
        if part.startswith('<'):
            parts[i]=re.sub(r'((?:title|placeholder|alt|aria-label)\s*=\s*)(["\'])(.*?)\2',attribute,part,flags=re.S)
        else:parts[i]=translate_text(re.match(r'[\s\S]*',part))
    return Markup(''.join(parts))

class MarkLiterals(NodeTransformer):
    def visit_Output(self,node,*args,**kwargs):
        node=self.generic_visit(node,*args,**kwargs)
        node.nodes=[nodes.Call(nodes.Name('_','load'),[child],[],None,None) if isinstance(child,nodes.Name) and child.name in ('error','login_error','message') else child for child in node.nodes]
        return node
    def visit_TemplateData(self,node,*args,**kwargs):
        return node
    def visit_Const(self,node,*args,**kwargs):
        if natural(node.value):
            return nodes.Call(nodes.Name('__ui_native__','load'),[nodes.Const(node.value)],[],None,None).set_lineno(node.lineno)
        return node

class NativeExtension(Extension):
    pass

def preprocess_html(source,messages=None):
    """Mark native HTML text/accessible attributes before Jinja compilation.

    Jinja expressions are masked with equal-length whitespace for HTML parsing;
    edits use source offsets. No rendered content or database value is inspected.
    Script/style/code and functional input values remain byte-for-byte untouched.
    """
    pattern=re.compile(r'{{[\s\S]*?}}|{%[\s\S]*?%}|{#[\s\S]*?#}')
    masked=pattern.sub(lambda m:re.sub(r'[^\n]',' ',m.group()),source)
    offsets=[0]
    for match in re.finditer('\n',source):offsets.append(match.end())
    edits=[]
    def mark(start,end):
        original=source[start:end];position=0
        for match in list(pattern.finditer(original))+[None]:
            stop=match.start() if match else len(original)
            part=original[position:stop];plain=' '.join(html.unescape(part).split())
            # Attribute fragments in Jinja macros are not HTML text nodes.
            structural=bool(re.search(r'\b[\w-]+\s*=\s*["\']|[<>{}]',plain))
            if re.search(r'[A-Za-zÀ-ÿ]',plain) and not structural and not re.fullmatch(r'[\W\d_]+',plain):
                lo=len(part)-len(part.lstrip());hi=len(part.rstrip())
                if hi>lo:
                    key=html.unescape(part[lo:hi]);normalized=' '.join(key.split())
                    if messages is not None:messages.add(normalized)
                    edits.append((start+position+lo,start+position+hi,'{{ _('+json.dumps(normalized,ensure_ascii=False)+') }}'))
            position=match.end() if match else len(original)
    class Parser(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=False);self.skip=[]
        def absolute(self):line,col=self.getpos();return offsets[line-1]+col
        def handle_starttag(self,tag,attrs):
            if tag in ('script','style','code','pre'):self.skip.append(tag)
            start=self.absolute();raw=self.get_starttag_text()
            for m in re.finditer(r'(?:title|placeholder|alt|aria-label|data-label|data-confirm)\s*=\s*(["\'])(.*?)\1',raw,re.S):mark(start+m.start(2),start+m.end(2))
            # Native label objects must never translate a functional HTML value,
            # URL, selector or business key. Only visible/accessible attributes
            # are localised. Preserve any already-authored filters and escaping.
            for attr in re.finditer(r'([\w:-]+)\s*=\s*(["\'])([\s\S]*?)\2',raw):
                if attr[1] in ('title','placeholder','alt','aria-label','data-title','data-details','data-action-label','data-label','data-confirm'):continue
                original=source[start+attr.start(3):start+attr.end(3)]
                for expression in re.finditer(r'{{([\s\S]*?)}}',original):
                    a=start+attr.start(3)+expression.start();b=start+attr.start(3)+expression.end()
                    edits.append((a,b,'{{ ('+expression[1]+') | untranslated }}'))
        def handle_endtag(self,tag):
            if self.skip and tag==self.skip[-1]:self.skip.pop()
        def handle_data(self,data):
            if not self.skip:mark(self.absolute(),self.absolute()+len(data))
    parser=Parser();parser.feed(masked);parser.close()
    for start,end,replacement in sorted(edits,reverse=True):source=source[:start]+replacement+source[end:]
    return source

def register(application,a):
    # Transform only source AST literals, never DB values or rendered HTML.
    environment=application.jinja_env
    original_parse=environment._parse
    def parse(source,name,filename):return MarkLiterals().visit(original_parse(preprocess_html(source),name,filename))
    environment._parse=parse
    environment.globals.update(_=t,__ui_html__=static_html,__ui_native__=native)
    environment.filters['native']=lambda value:t(value)
    environment.filters['untranslated']=lambda value:str(value) if isinstance(value,NativeText) else value
    application.json=NativeJSONProvider(application)
    environment.policies['json.dumps_function']=application.json.dumps
    bp=Blueprint('language',__name__)
    @application.before_request
    def choose_language():
        db=a['get_database']()
        read=lambda k,d='':a['read_setting'](db,k,d)
        is_admin=request.path.startswith('/admin')
        key='admin_language' if is_admin else 'kiosk_language_selected'
        primary=read('kiosk_language','fr');primary=primary if primary in LANGUAGES else 'fr'
        available=read('kiosk_languages','fr,en').split(',')
        if primary not in available:available.append(primary)
        switch=read('kiosk_language_switch_enabled','1')=='1' and len(set(available)&set(LANGUAGES))>1
        if not is_admin and not switch:
            session.pop('kiosk_language_selected',None);available=[primary]
        selected=session.get(key,'fr' if is_admin else primary)
        if selected not in LANGUAGES or (not is_admin and selected not in available):selected=primary
        g.ui_language=selected;g.ui_admin=is_admin
        g.ui_available=tuple(LANGUAGES) if is_admin else tuple(x for x in LANGUAGES if x in available)
        g.ui_language_switch=is_admin or switch
    @bp.post('/langue')
    def select():
        from evolution_routes import require_csrf
        require_csrf();value=request.form.get('language')
        admin=request.form.get('scope')=='admin'
        if admin:
            from evolution_routes import require_team
            require_team()
        if value not in LANGUAGES or (not admin and (not g.ui_language_switch or value not in g.ui_available)):abort(400)
        session['admin_language' if admin else 'kiosk_language_selected']=value
        target=request.form.get('next','/')
        if not target.startswith('/') or target.startswith('//') or '\\' in target:target=url_for('index')
        return redirect(target)
    @bp.post('/langue/repos')
    def idle():
        from evolution_routes import require_csrf
        require_csrf()
        # Revoke the existing form-scoped registry BEFORE discarding its device
        # key. Removing cookie buffers alone would leave an old signed cookie
        # able to revive the abandoned enrollment until its normal expiry.
        import enrollment_privacy
        enrollment_privacy.abandon(a['get_database']())
        session.pop('kiosk_language_selected',None)
        # Clear only public enrollment/booking buffers, never admin preferences.
        for key in list(session):
            if key.startswith(('enrollment_','_enrollment_','family_enrollment_','family_identity','tablet_identity')) or key in ('family_booking','family_receipt'):session.pop(key,None)
        return redirect(url_for('index'))
    @application.context_processor
    def context():
        db=a['get_database']();read=a['read_setting']
        try:idle=max(1,min(120,int(read(db,'kiosk_language_idle_minutes','10'))))
        except (ValueError,TypeError):idle=10
        endpoint=request.endpoint or ''
        kiosk_idle=not g.ui_admin and (endpoint in ('index','users','identification','visitors') or endpoint.startswith(('evolution.enroll','tablet.','family_gateway.receipt')) or request.path.startswith('/animations/') and not request.path.startswith('/animations/demande/'))
        return dict(ui_language=language(),ui_language_choices=g.ui_available,ui_admin=g.ui_admin,ui_language_switch=g.ui_language_switch,
            ui_language_registry=LANGUAGES,ui_language_names=[(k,v[0]) for k,v in LANGUAGES.items()],
            ui_primary_language=read(db,'kiosk_language','fr'),ui_idle_minutes=idle,ui_idle_enabled=kiosk_idle,
            ui_catalog=CATALOGS.get(language(),{}))
    application.register_blueprint(bp)
