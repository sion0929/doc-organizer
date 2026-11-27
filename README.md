# 문서정리 — doc-organizer Skill

연구실 자료를 **노션에 복붙할 수 있게** 정리해 주는 Claude Skill.
팀 노션은 Claude와 연결되어 있지 않으므로, Claude가 만든 마크다운을 복사해서 노션에 붙여넣는다.

## 정리할 수 있는 자료

| 번호 | 유형 | 출력 |
|---|---|---|
| 1-1 / 1-2 | 특허 초안 / 선행특허 조사 | 페이지 |
| 2-1 / 2-2 | 논문 작성 / 논문 리뷰 | 페이지 |
| 3 | 개발 문서 | 페이지 |
| 4 | 시험일지 | 페이지 |
| 5 | 회의록 | 페이지 |
| 6 | 구매물품 | 표 (엑셀·노션 DB) |
| 7 | 할 일 (실험 내용 정리 / 하드웨어 제작 / 시스템 설계 / 계획 구체화 / 시스템 구조도 / 점검 문서) | 페이지 |

## 사용법 (Claude Code)

Claude Code에서 `/doc-organizer` 를 입력하거나 "문서 정리해줘", "회의록 정리해줘"처럼 말한다.

1. 유형을 고른다 (번호).
2. 자료가 있으면 붙여넣거나 파일 경로를 알려준다. 없으면 "없음" → 질문에 답하며 채운다.
3. 결과:
   - **① 노션 속성 입력값** 표 → 노션 DB의 속성 칸에 직접 입력
   - **② 본문** → `~/notion-output/날짜_유형_제목.md` 에 저장되고 클립보드에도 복사됨 → 노션 페이지 본문에 `Ctrl+V`
   - **③ 확인할 것** → `⚠️ 확인 필요` 항목과 Claude가 추정한 값. 노션에 넣기 전에 확인
   - **④ 따로 할 일** → 노션에서 직접 첨부할 그림·파일 등
   - 구매물품: 표가 탭 구분으로 클립보드에 복사됨 → 엑셀에 `Ctrl+V` 하면 칸별로 들어감. `~/notion-output/날짜_구매물품_품목.csv` 도 저장(노션 DB `•••` → CSV 병합)
4. 고칠 곳을 말하면 전체를 다시 만들어 준다.

> 터미널 화면을 드래그해서 복사하면 줄바꿈·마크다운 기호가 깨질 수 있다. 저장된 파일이나 클립보드를 쓴다.

## 처음 한 번: 노션 붙여넣기 확인

[tests/notion-paste-test.md](tests/notion-paste-test.md) 내용을 노션 빈 페이지에 붙여넣어서,
제목·목록·체크박스·표·인용·코드 블록·구분선이 제대로 바뀌는지 확인한다.

```bash
xclip -selection clipboard < tests/notion-paste-test.md   # 클립보드에 복사 후 노션에 Ctrl+V
```

깨지는 요소가 있으면 `skills/doc-organizer/SKILL.md` 의 "노션 복붙 규칙"에서 그 요소를 "쓰지 않는다"로 옮긴다.
2026-11-27 확인 결과 모든 요소(Mermaid 포함)가 깨짐 없이 변환됨.

## 설치

```bash
ln -s /home/sion/문서정리/skills/doc-organizer ~/.claude/skills/doc-organizer
```

claude.ai에서 쓰려면 `skills/doc-organizer` 폴더를 zip으로 묶어 설정 → 기능 → Skills 에 올린다.

```bash
cd skills && zip -r ../doc-organizer.zip doc-organizer
```

## 노션 데이터베이스 만들기

[notion-setup.md](notion-setup.md) 참고. 유형마다 DB를 하나씩 만들고, 속성은 각 양식 파일의 "① 노션 DB 속성" 표대로 만든다.

## 구조

```
skills/doc-organizer/
├── SKILL.md                    진행 순서 · 출력 형식 · 노션 복붙 규칙
├── scripts/check_notion_md.py  노션에서 깨지는 문법 검사
└── templates/                  유형별 양식 (① DB 속성 / ② 질문 / ③ 본문 뼈대 / ④ 작성 메모)
    └── todo/                   할 일 분류별 양식 6개
tests/notion-paste-test.md      붙여넣기 확인용
notion-setup.md                 노션 DB 만드는 법
docs/superpowers/specs/         설계서
```

## 양식 고치기

- 양식 파일 하나만 고치면 된다. 섹션을 바꿀 때는 ② 질문 목록과 ③ 본문 뼈대를 같이 고친다.
- 고친 뒤 검사:

```bash
python3 skills/doc-organizer/scripts/check_notion_md.py --template skills/doc-organizer/templates/*.md skills/doc-organizer/templates/todo/*.md
```

- 양식 파일에는 실제 내용(과제명·금액·수치 등)을 넣지 않는다. 구조와 채울 자리 `{ }` 만 둔다.
- 결과물은 `~/notion-output/` 에 저장된다(저장소 밖). 실제 내용이 담기므로 저장소에 넣지 않는다.
