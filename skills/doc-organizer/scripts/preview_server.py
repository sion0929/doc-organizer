#!/usr/bin/env python3
"""옆 창 미리보기 · 공동 편집 서버.

작성 중인 md를 브라우저(Orca 옆 탭 또는 Chrome)에서 렌더링해 보여주고,
사용자가 그 창에서 직접 고치거나 메모를 남길 수 있게 한다. Claude가 파일을 고치면 창이 자동으로 새로고침된다.

사용법:
    python3 preview_server.py 문서.md [--port 8790]
    → 첫 줄에 URL 출력. Orca: orca tab create --url <URL> --split right --focus

사용자 편집은 문서.md 에 바로 저장되고 문서.md.edits.log 에 기록된다.
메모는 문서.md.notes.md 에 쌓인다(Claude가 "반영" 때 읽는다).
127.0.0.1 에서만 열린다. 표준 라이브러리만 쓴다(화면 렌더링용 marked·mermaid는 CDN).
"""
import argparse
import datetime
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>
:root{--bg:#fff;--fg:#1f2328;--mut:#656d76;--bd:#d0d7de;--acc:#0969da;--warn:#fff8c5;--note:#f6f8fa}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8d96a0;--bd:#30363d;--acc:#4493f8;--warn:#3b2e00;--note:#161b22}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 'Noto Sans CJK KR','Noto Sans KR',system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 14px;background:var(--bg);border-bottom:1px solid var(--bd)}
header b{font-size:14px;margin-right:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:50vw}
button{font:inherit;font-size:13px;padding:4px 10px;border:1px solid var(--bd);border-radius:6px;background:var(--note);color:var(--fg);cursor:pointer}
button.on{border-color:var(--acc);color:var(--acc)}#st{font-size:12px;color:var(--mut)}
#banner{display:none;padding:8px 14px;background:var(--warn);font-size:13px}
main{max-width:980px;margin:0 auto;padding:16px 18px 80px}
#view h1{font-size:1.6em;border-bottom:1px solid var(--bd);padding-bottom:.2em}#view h2{font-size:1.3em;margin-top:1.6em}#view h3{font-size:1.1em}
#view table{border-collapse:collapse;display:block;overflow-x:auto}#view td,#view th{border:1px solid var(--bd);padding:4px 8px;font-size:14px}
#view pre{background:var(--note);padding:10px;overflow-x:auto;border-radius:6px}#view code{font-size:13px}
#view .mermaid{background:#fff;border:1px solid var(--bd);border-radius:6px;padding:8px;overflow-x:auto;margin:10px 0}
#view img.att{max-width:100%;border:1px solid var(--bd);border-radius:6px;margin:6px 0;display:block}
#view .gap{background:var(--warn);padding:0 3px;border-radius:3px}
textarea{width:100%;font:13px/1.5 ui-monospace,'D2Coding',monospace;background:var(--bg);color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:10px}
#ed{height:calc(100vh - 140px);display:none}
#notes{display:none;position:fixed;right:12px;bottom:12px;width:min(420px,92vw);background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:10px;box-shadow:0 4px 16px rgba(0,0,0,.15)}
#notes textarea{height:90px}#nl{max-height:200px;overflow:auto;font-size:12px;color:var(--mut);white-space:pre-wrap;margin-top:6px}
</style></head><body>
<header><b id="ttl">__TITLE__</b>
<button id="bv" class="on">미리보기</button><button id="be">편집</button><button id="bs" disabled>저장</button><button id="bn">메모</button><span id="st"></span></header>
<div id="banner">Claude가 파일을 고쳤습니다. 편집 중인 내용이 있어 자동으로 바꾸지 않았습니다. <button id="br">Claude 버전 불러오기</button></div>
<main><div id="view"></div><textarea id="ed" spellcheck="false"></textarea></main>
<div id="notes"><div style="font-size:13px;margin-bottom:4px">Claude에게 남길 메모 — 터미널에서 "반영"이라고 말하면 읽습니다</div>
<textarea id="nt" placeholder="예: 2-1-3 처리 단계를 3개로 줄여줘"></textarea>
<div style="display:flex;gap:6px;margin-top:6px"><button id="ns">메모 남기기</button><button id="nc">닫기</button></div><div id="nl"></div></div>
<script>
const $=id=>document.getElementById(id);let doc={text:'',mtime:0},mode='view',dirty=false,images=[];
mermaid.initialize({startOnLoad:false,securityLevel:'loose',theme:'default'});
function st(t){$('st').textContent=t}
async function load(force){const r=await fetch('/api/doc');const d=await r.json();
 if(!force&&d.mtime===doc.mtime)return;const changed=doc.mtime&&d.mtime!==doc.mtime;
 if(mode==='edit'&&dirty&&changed){$('banner').style.display='block';doc.pending=d;return}
 doc=d;$('ed').value=d.text;dirty=false;$('bs').disabled=true;render();
 st((changed?'방금 바뀜 · ':'')+new Date(d.mtime*1000).toLocaleTimeString());}
async function render(){const v=$('view');v.innerHTML=marked.parse(doc.text);
 v.querySelectorAll('code.language-mermaid').forEach(c=>{const d=document.createElement('div');d.className='mermaid';d.textContent=c.textContent;c.parentElement.replaceWith(d)});
 v.querySelectorAll('h1,h2,h3').forEach((h,i)=>h.id='s'+i);
 v.querySelectorAll('li,p,td').forEach(e=>{if(e.querySelector('li'))return;const t=e.textContent;
  images.forEach(n=>{if(t.includes(n)&&!e.querySelector('img')){const im=document.createElement('img');im.className='att';im.src='/img/'+encodeURIComponent(n);e.appendChild(im)}});
  if(/추가 권장|확인 필요/.test(t)&&!e.querySelector('.gap'))e.innerHTML=e.innerHTML.replace(/(➕ 추가 권장|➕ 추가 권장)/g,'<span class="gap">$1</span>')});
 try{await mermaid.run({nodes:v.querySelectorAll('.mermaid')})}catch(e){st('그림 렌더링 오류: '+e.message)}}
function setMode(m){mode=m;$('bv').classList.toggle('on',m==='view');$('be').classList.toggle('on',m==='edit');
 $('view').style.display=m==='view'?'block':'none';$('ed').style.display=m==='edit'?'block':'none';if(m==='view'){doc.text=$('ed').value;render()}}
$('bv').onclick=()=>setMode('view');$('be').onclick=()=>setMode('edit');
$('ed').oninput=()=>{dirty=true;$('bs').disabled=false;st('저장 안 됨')};
$('bs').onclick=async()=>{const r=await fetch('/api/doc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('ed').value,base_mtime:doc.mtime})});
 const d=await r.json();if(r.status===409){$('banner').style.display='block';st('Claude가 먼저 고쳤습니다 — 불러온 뒤 다시 고쳐주세요');return}
 doc.mtime=d.mtime;doc.text=$('ed').value;dirty=false;$('bs').disabled=true;st('저장됨 · 터미널에서 "반영"이라고 말해주세요')};
$('br').onclick=()=>{$('banner').style.display='none';dirty=false;load(true)};
$('bn').onclick=async()=>{const sel=String(getSelection()).trim();$('notes').style.display='block';if(sel&&!$('nt').value)$('nt').value='> '+sel.slice(0,200)+'\n';$('nt').focus();loadNotes()};
$('nc').onclick=()=>$('notes').style.display='none';
$('ns').onclick=async()=>{const t=$('nt').value.trim();if(!t)return;await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note:t})});$('nt').value='';loadNotes();st('메모 저장됨 · 터미널에서 "반영"이라고 말해주세요')};
async function loadNotes(){const r=await fetch('/api/notes');$('nl').textContent=(await r.json()).text||'(메모 없음)'}
(async()=>{images=(await (await fetch('/api/images')).json()).images;await load(true);setInterval(load,1500)})();
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='s'&&mode==='edit'){e.preventDefault();$('bs').click()}});
</script></body></html>"""


def image_dirs(md):
    folder = os.path.dirname(os.path.abspath(md))
    stem = os.path.splitext(os.path.basename(md))[0]
    base = re.sub(r"_노션$", "", stem)
    out = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isdir(p) and name.startswith(base) and name.endswith("_diagrams"):
            out.append(p)
    return out


def list_images(md):
    names = []
    for d in image_dirs(md):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".png", ".jpg", ".jpeg")) and not f.startswith("mermaid_") and f not in names:
                names.append(f)
    return names


def make_handler(md):
    md = os.path.abspath(md)
    notes = md + ".notes.md"
    log = md + ".edits.log"
    title = os.path.basename(md)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def js(self, code, obj):
            self.send(code, json.dumps(obj, ensure_ascii=False))

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(200, PAGE.replace("__TITLE__", title), "text/html; charset=utf-8")
            if self.path == "/api/doc":
                with open(md, encoding="utf-8") as f:
                    return self.js(200, {"text": f.read(), "mtime": os.path.getmtime(md)})
            if self.path == "/api/notes":
                text = open(notes, encoding="utf-8").read() if os.path.exists(notes) else ""
                return self.js(200, {"text": text})
            if self.path == "/api/images":
                return self.js(200, {"images": list_images(md)})
            if self.path.startswith("/img/"):
                from urllib.parse import unquote
                name = os.path.basename(unquote(self.path[5:]))
                for d in image_dirs(md):
                    p = os.path.join(d, name)
                    if os.path.isfile(p):
                        ctype = "image/png" if name.lower().endswith(".png") else "image/jpeg"
                        with open(p, "rb") as f:
                            return self.send(200, f.read(), ctype)
                return self.send(404, "not found", "text/plain; charset=utf-8")
            self.send(404, "not found", "text/plain; charset=utf-8")

        def do_POST(self):
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if self.path == "/api/doc":
                b = self.body()
                if abs(float(b.get("base_mtime", 0)) - os.path.getmtime(md)) > 1e-6:
                    return self.js(409, {"conflict": True, "mtime": os.path.getmtime(md)})
                with open(md, "w", encoding="utf-8") as f:
                    f.write(b.get("text", ""))
                with open(log, "a", encoding="utf-8") as f:
                    f.write("%s 사용자 편집 저장\n" % now)
                return self.js(200, {"mtime": os.path.getmtime(md)})
            if self.path == "/api/notes":
                note = (self.body().get("note") or "").strip()
                if note:
                    with open(notes, "a", encoding="utf-8") as f:
                        f.write("## %s\n\n%s\n\n" % (now, note))
                return self.js(200, {"ok": True})
            self.send(404, "not found", "text/plain; charset=utf-8")

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    if not os.path.isfile(args.md):
        print("파일 없음: " + args.md, file=sys.stderr)
        return 2
    handler = make_handler(args.md)
    for port in range(args.port, args.port + 40):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    else:
        print("빈 포트 없음", file=sys.stderr)
        return 1
    print("http://127.0.0.1:%d/" % port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
