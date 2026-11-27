#!/usr/bin/env python3
"""노션 붙여넣기용 마크다운 검사기.

노션은 붙여넣은 마크다운 중 일부 문법만 블록으로 바꾼다. 이 스크립트는
바뀌지 않거나 깨지는 문법을 찾아 줄 번호와 함께 알려준다.

사용법:
    python3 check_notion_md.py 파일.md [파일2.md ...]
    python3 check_notion_md.py --template 양식.md   # 양식의 ````markdown 블록만 검사

위반이 있으면 종료 코드 1, 없으면 0.
표준 라이브러리만 사용한다.
"""
import re
import sys

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s")
TABLE_LINE_RE = re.compile(r"^\s*\|")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
LIST_RE = re.compile(r"^( *)([-*+]|\d+\.)\s")
INLINE_CODE_RE = re.compile(r"`+[^`]*`+")
MARKER_LINE_RE = re.compile(r"^\s*%%.*%%\s*$")

RULES = [
    (re.compile(r"^\s{0,3}#{4,}\s"), "제목4이상", "#### 이하 제목은 노션에서 제목으로 바뀌지 않음 → ### 이하로"),
    (re.compile(r"<!--|<(/?[A-Za-z][A-Za-z0-9-]*)(\s[^<>]*)?/?>"), "HTML", "HTML 태그는 글자 그대로 남음 → 마크다운으로"),
    (re.compile(r"<https?://[^>]+>"), "꺾쇠링크", "<URL> 대신 [글](URL) 또는 URL 그대로"),
    (re.compile(r"^\s*\$\$"), "수식블록", "$$ 수식 블록은 변환 안 됨 → 인라인 코드로"),
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), "이미지문법", "이미지는 붙여넣기로 안 들어감 → 📷 [그림: ... — 노션에서 직접 첨부]"),
    (re.compile(r"\[\^[^\]]+\]"), "각주", "각주는 변환 안 됨"),
    (re.compile(r"^\s*!\S+\.(png|jpe?g|gif|webp|svg|bmp)\s*$", re.I), "노션이미지잔여", "!image.png 같은 줄 → 📷 [그림: ... — 노션에서 직접 첨부]"),
    (re.compile(r"^\s*>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", re.I), "콜아웃", "> [!NOTE] 콜아웃은 변환 안 됨 → 일반 인용 >"),
    (re.compile(r"\t"), "탭문자", "탭 대신 공백 4칸"),
]
PLACEHOLDER_RE = re.compile(r"\{[^{}\n]+\}")
SINGLE_TILDE_RE = re.compile(r"(?<!~)~(?!~)")


def split_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return re.split(r"(?<!\\)\|", s)


def extract_template_blocks(lines):
    """````markdown 블록 안쪽 줄만 (원래 줄 번호, 내용)으로 돌려준다."""
    out, inside, found = [], False, False
    for no, line in enumerate(lines, 1):
        if not inside and re.match(r"^````markdown\s*$", line):
            inside, found = True, True
            out.append((no, ""))  # 블록 시작은 빈 줄처럼 취급
            continue
        if inside and re.match(r"^````\s*$", line):
            inside = False
            out.append((no, ""))
            continue
        if inside:
            out.append((no, line))
    return out, found, inside


def check(numbered, template_mode):
    problems = []

    def add(no, rule, msg):
        problems.append((no, rule, msg))

    if template_mode:
        # %% 안내 %% 줄은 출력 전에 지워지므로 없는 줄로 취급
        numbered = [(n, l) for n, l in numbered if not MARKER_LINE_RE.match(l)]

    fence = None  # (문자, 길이, 시작 줄)
    prev = ""  # 바로 앞 줄 (코드 블록 밖 기준)
    table_rows = []  # 현재 표 [(줄번호, 내용)]

    def close_table(next_line_no=None, next_line=""):
        if not table_rows:
            return
        head_no, head = table_rows[0]
        if len(table_rows) < 2 or not TABLE_SEP_RE.match(table_rows[1][1]):
            add(head_no, "표구분행", "표 둘째 줄에 |---|---| 구분 행이 필요")
        n = len(split_cells(head))
        for no, row in table_rows:
            if "\\|" in row:
                add(no, "표칸파이프", "표 칸 안의 | 는 / 로 바꿔 쓰기")
            if len(split_cells(row)) != n:
                add(no, "표열수", f"열 개수가 헤더({n}개)와 다름")
        if next_line_no is not None and next_line.strip():
            add(next_line_no, "표뒤빈줄", "표 바로 다음 줄은 빈 줄이어야 함 (안 그러면 표에 붙음)")
        table_rows.clear()

    for no, line in numbered:
        m = FENCE_RE.match(line)
        if fence:
            if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= fence[1] and not m.group(3).strip():
                fence = None
                prev = line
            continue
        if m:
            close_table(no, line)
            if prev.strip() and not LIST_RE.match(prev) and not prev.startswith(" "):
                add(no, "코드앞빈줄", "코드 블록 앞에 빈 줄 필요")
            fence = (m.group(2)[0], len(m.group(2)), no)
            prev = line
            continue

        if TABLE_LINE_RE.match(line):
            if not table_rows and prev.strip():
                add(no, "표앞빈줄", "표 앞에 빈 줄 필요")
            table_rows.append((no, line))
            prev = line
            continue
        close_table(no, line)

        scan = INLINE_CODE_RE.sub("", line)
        for rx, rule, msg in RULES:
            if rx.search(scan):
                add(no, rule, msg)
        if not template_mode:
            if "%%" in scan:
                add(no, "양식표시잔여", "%% 안내 %% 표시가 남아 있음")
            if PLACEHOLDER_RE.search(scan):
                add(no, "채울자리잔여", "{채울 내용} 표시가 남아 있음 → 내용 또는 ⚠️ 확인 필요")
        if HEADING_RE.match(line) and prev.strip():
            add(no, "제목앞빈줄", "제목 앞에 빈 줄 필요")
        if HEADING_RE.match(prev) and line.strip():
            add(no, "제목뒤빈줄", "제목 다음 줄은 빈 줄이어야 함")
        if len(SINGLE_TILDE_RE.findall(scan)) >= 2:
            add(no, "물결표", "한 줄에 ~ 가 두 개면 노션이 취소선으로 바꿀 수 있음 → 범위는 – 또는 '부터/까지'로")
        lm = LIST_RE.match(line)
        if lm and len(lm.group(1)) % 4:
            add(no, "들여쓰기", "목록 들여쓰기는 공백 4칸 단위")
        prev = line

    close_table()
    if fence:
        add(fence[2], "코드블록닫힘", "코드 블록이 닫히지 않음")
    return problems


def main(argv):
    template_mode = "--template" in argv
    paths = [a for a in argv if a != "--template"]
    if not paths:
        print(__doc__.strip())
        return 2
    total = 0
    for path in paths:
        with open(path, encoding="utf-8-sig") as f:
            lines = f.read().split("\n")
        if template_mode:
            numbered, found, unclosed = extract_template_blocks(lines)
            if not found:
                print(f"{path}: [본문뼈대없음] ````markdown 블록을 찾지 못함")
                total += 1
                continue
            if unclosed:
                print(f"{path}: [본문뼈대닫힘] ````markdown 블록이 닫히지 않음")
                total += 1
        else:
            numbered = list(enumerate(lines, 1))
        problems = check(numbered, template_mode)
        if not template_mode:
            for no, line in numbered:
                if re.match(r"^`{4,}", line) or re.match(r"^\s*\|\s*속성\s*\|\s*값\s*\|", line):
                    problems.append((no, "본문만저장", "속성 표나 바깥 ```` 코드 블록이 들어 있음 → 파일에는 본문만 저장"))
                    break
        for no, rule, msg in sorted(problems):
            print(f"{path}:{no}: [{rule}] {msg}")
        total += len(problems)
    print(f"검사 완료: 위반 {total}건")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
