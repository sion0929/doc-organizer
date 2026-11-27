# 노션 데이터베이스 만들기

유형마다 데이터베이스(DB)를 하나씩 만든다. 속성 목록의 원본은 각 양식 파일의 **① 노션 DB 속성** 표다.
이 문서에는 속성을 다시 적지 않는다(두 곳에 적으면 어긋나기 때문).

## 만들 DB 목록

| DB 이름 (예시) | 속성 표가 있는 파일 |
|---|---|
| 특허 초안 | `skills/doc-organizer/templates/patent-draft.md` |
| 선행특허 조사 | `skills/doc-organizer/templates/patent-prior-art.md` |
| 논문 작성 | `skills/doc-organizer/templates/paper-writing.md` |
| 논문 리뷰 | `skills/doc-organizer/templates/paper-review.md` |
| 개발 문서 | `skills/doc-organizer/templates/dev-doc.md` |
| 시험일지 | `skills/doc-organizer/templates/test-log.md` |
| 회의록 | `skills/doc-organizer/templates/meeting.md` |
| 구매물품 | `skills/doc-organizer/templates/purchase.md` |
| SUVLab Works | `skills/doc-organizer/templates/todo.md` |

## 만드는 순서

1. 팀 노션에 허브 페이지를 하나 만든다 (예: "SUVLab 문서").
2. 허브 페이지에서 `/데이터베이스 - 전체 페이지` (또는 `/database`)로 DB를 만든다.
3. 양식 파일의 ① 표를 보고 속성을 추가한다.
   - "종류" 칸 → 노션 속성 종류: 제목 / 텍스트 / 숫자 / 선택 / 다중 선택 / 날짜 / 사람 / URL / 수식
   - "선택지" 칸에 적힌 값을 선택 속성의 옵션으로 미리 만들어 둔다(붙여넣을 때 같은 글자로 고르기 쉽게).
4. 9개 DB를 모두 같은 방법으로 만든다.

## 정리한 내용 옮기기

### 페이지 유형 (구매물품 제외 전부)

1. DB에서 `+ 새로 만들기`로 새 페이지를 연다.
2. Claude 출력의 **① 노션 속성 입력값** 표를 보고 속성 칸을 채운다.
3. 페이지 본문을 클릭하고 **② 본문**을 붙여넣는다(`Ctrl+V`).
4. `📷` `📎` `🎞` 자리 표시가 있는 곳에 그림·파일·영상을 직접 첨부하고 자리 표시 줄은 지운다.
5. `⚠️ 확인 필요` 가 남아 있으면 확인해서 채운다.

### 구매물품 (표)

- 엑셀에 붙이기: claude.ai에서는 출력된 표를 드래그해 복사 → 엑셀에 붙여넣기. Claude Code에서는 저장된 `.csv`를 엑셀로 연다.
- 노션 DB에 넣기: 구매물품 DB 오른쪽 위 `•••` → **CSV 병합(Merge with CSV)** → 저장된 `.csv` 선택.
  CSV 열 이름이 DB 속성 이름과 같아야 해당 칸으로 들어간다.

## (선택) DB 템플릿 만들기

Claude 없이 직접 쓰는 사람도 같은 양식을 쓰게 하려면, DB의 `새로 만들기 ▾` → `+ 새 템플릿`에
양식 파일의 **③ 본문 뼈대** 를 붙여넣는다. 붙여넣기 전에 `%% … %%` 줄은 지운다.
