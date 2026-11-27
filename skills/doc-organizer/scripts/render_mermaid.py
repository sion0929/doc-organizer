#!/usr/bin/env python3
"""마크다운 안의 ```mermaid 블록을 렌더링해 오류를 검사하고 PNG로 저장한다.

노션에 붙여넣기 전에 다이어그램이 깨지지 않는지 확인하고, 노션에 직접 첨부할 PNG도 만든다.
헤드리스 Chrome + mermaid(CDN)를 쓴다.

사용법:
    python3 render_mermaid.py 본문.md --out 폴더 [--scale 2]

표준출력: 블록마다 한 줄 JSON {"n", "title", "ok", "error", "png"}
종료 코드: 하나라도 오류면 1
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;padding:16px;background:#fff;font-family:'Noto Sans CJK KR','Noto Sans KR',sans-serif}}</style>
<script src="{url}"></script></head><body>
<pre class="mermaid">{src}</pre>
<script>
mermaid.initialize({{startOnLoad:false, securityLevel:'loose', theme:'default',
  themeVariables:{{fontFamily:"'Noto Sans CJK KR','Noto Sans KR',sans-serif"}}}});
mermaid.run({{querySelector:'.mermaid'}}).then(function(){{
  var s=document.querySelector('svg'); var r=s.getBoundingClientRect();
  document.title='OK '+Math.ceil(r.width+32)+'x'+Math.ceil(r.height+32);
}}).catch(function(e){{ document.title='ERR '+String(e && e.message || e).replace(/\\s+/g,' ').slice(0,300); }});
</script></body></html>"""


def find_chrome():
    for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(c)
        if p:
            return p
    return None


def blocks(md):
    """(제목, 소스) 목록. 제목은 블록 바로 앞의 마크다운 제목."""
    out, title, inside, buf = [], "diagram", False, []
    for line in md.split("\n"):
        if not inside:
            m = re.match(r"^\s{0,3}#{1,6}\s+(.*)", line)
            if m:
                title = m.group(1).strip()
            if re.match(r"^\s*```mermaid\s*$", line):
                inside, buf = True, []
        else:
            if re.match(r"^\s*```\s*$", line):
                out.append((title, "\n".join(buf)))
                inside = False
            else:
                buf.append(line)
    return out


def run_chrome(chrome, args, profile):
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           "--user-data-dir=" + profile, "--virtual-time-budget=10000", "--hide-scrollbars"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=90)


def safe(name):
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "_", name).strip("_")
    return (s or "diagram")[:40]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=2.0)
    args = ap.parse_args()

    chrome = find_chrome()
    if not chrome:
        print(json.dumps({"error": "chrome 없음 — 렌더링 검사를 건너뜀"}, ensure_ascii=False))
        return 3
    with open(args.md, encoding="utf-8") as f:
        items = blocks(f.read())
    if not items:
        print(json.dumps({"info": "mermaid 블록 없음"}, ensure_ascii=False))
        return 0
    os.makedirs(args.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="mmd-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    bad = 0
    try:
        for n, (title, src) in enumerate(items, 1):
            page = os.path.join(tmp, "d%d.html" % n)
            with open(page, "w", encoding="utf-8") as f:
                f.write(PAGE.format(url=MERMAID_URL, src=html.escape(src)))
            dom = run_chrome(chrome, ["--dump-dom", "file://" + page], os.path.join(tmp, "p"))
            m = re.search(r"<title>(.*?)</title>", dom.stdout, re.S)
            status = html.unescape(m.group(1)) if m else "ERR 렌더링 결과 없음 (네트워크로 mermaid를 받지 못했을 수 있음)"
            rec = {"n": n, "title": title, "ok": status.startswith("OK"), "error": None, "png": None}
            if rec["ok"]:
                w, h = (int(x) for x in status.split()[1].split("x"))
                png = os.path.join(args.out, "mermaid_%02d_%s.png" % (n, safe(title)))
                run_chrome(chrome, ["--screenshot=" + png, "--window-size=%d,%d" % (max(w, 200), max(h, 120)),
                                    "--force-device-scale-factor=%g" % args.scale, "file://" + page],
                           os.path.join(tmp, "p"))
                rec["png"] = png if os.path.exists(png) else None
            else:
                rec["error"] = status[4:] if status.startswith("ERR") else status
                bad += 1
            print(json.dumps(rec, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
