# 다음 PC에서 작업 이어가기

## 2026-09-23 작업 종료 및 GitHub 반영

- 오늘 완료한 빠른 제작, 사전 진단, 디자인 테마, 중단·재개, 한 줄 코드 보존 검사 수정, AI 뎁스 자동 보완을 함께 커밋·푸시합니다. 아래 각 날짜별 기록은 당시 검증과 배포 이력입니다.
- **다음 작업: 목록 연속성 복구(아직 미구현).** Chapter 8의 `템플릿 매개변수 / 템플릿 인수 / 인스턴스화`는 같은 목록인데 마지막 항목만 별도 박스로 출력됩니다. 사용자 요청 후 읽기 전용 코드 조사까지만 진행했고, 작업 종료 요청에 따라 구현은 시작하지 않았습니다.
- 우선 확인할 원인: `core/manuscript/docx_reader.py`가 번호 문단 본문의 클릭·선택·입력·설치·실행 등의 단어만으로 `procedure-step`으로 분류하며, 테마는 이 타입을 박스로 렌더링합니다. 실제 Word 목록 정보와 세 항목의 분류 결과를 먼저 대조하세요.
- 후속 수정 범위: 문맥과 목록 패턴에 기반한 list continuity repair, 의미 구조와 디자인 분리, 동일 목록의 HTML/PDF/EPUB 일관된 출력. 명확한 주의/참고/TIP 등의 의미가 없는 단순 불릿을 박스로 만들지 않습니다. 디자인 자체를 변경하지 않습니다.
- 기존 작업의 저장된 master/교정 기준본에도 예전 분류가 남아 있을 수 있습니다. 원고 재파싱뿐 아니라 재출력 경로를 점검하고, 기존 블록 ID·원문·코드·검토 기록·구조 지문을 보존하세요. Chapter 8 전체 목록과 세 출력 형식을 검증해야 합니다.
- API 키·원고·working·reports·결과물·EXE는 GitHub 반영 대상이 아닙니다. 다른 PC에서는 별도의 로컬 환경 설정과 실행 파일 빌드가 필요합니다.

## 2026-09-23 AI 뎁스 자동 보완

- 이번 범위는 기존 Chapter/Section 아래 필요한 Subsection/Topic 자동 생성만입니다. GUI 원고 구조에 기존 구조 사용 / AI 뎁스 자동 보완, 최대 3depth/4depth만 추가했습니다. 기본값은 AI 보완·4depth이며 설정을 저장합니다. 기술 검토 모델과 해당 추론 강도를 그대로 사용합니다.
- core/manuscript/depth.py는 Section별 본문·표·코드를 읽기 전용 자료로 보내 의미상 필요한 새 3/4depth만 받습니다. 빈 nodes도 정상입니다. 길이/그림/코드/페이지 단독 이유의 분할을 금지하는 프롬프트를 사용하며 의미적 품질은 AI 판단입니다.
- 원문 블록과 기존 목차는 바꾸지 않고 새 제목을 지정 블록 앞에 삽입합니다. 새 제목은 임의 번호를 붙이지 않습니다. 원문 위치·Section 범위·최대 뎁스·계층·순서를 검증하고 사용자 승인/수정 절차 없이 결과물 최종 구조로 적용합니다. 기존 수동 구조/교정 기록은 그대로 둡니다.
- Section별 요청 결과를 원고 지문·기존 구조·모델·추론·최대 뎁스·정책 버전별로 working/<hash>/ai-depth에 캐시합니다. 중단 후 완료 Section을 재호출하지 않습니다. Section 하나가 JSON 60,000자보다 크면 잘라 보내지 않고 오류를 안내합니다.
- HTML h4/계층 목차, PDF Heading4/4단계 책갈피, EPUB 본문/탐색 목차를 지원합니다. 자동 구조 모드에서는 기존 구조가 draft여도 형식검사 후 사용하며 수동 승인 절차를 요구하지 않습니다.
- 실제 원고 2.Chapter 1-초안의 사본.docx: 기존 7개 항목(Chapter 1, Section 4, 기존 Subsection 2). gpt-5.6-sol / none 실제 Section 4회 분석 결과 3depth 13개, 4depth 4개 추가. 자동 교정 API는 실행하지 않았습니다. 최종 HTML/PDF/EPUB QA 모두 통과, 원본 및 기존 사용자 JSON 해시 불변 확인. PDF 27~28페이지 시각 확인.
- 실제 결과: reports/actual-ai-depth/result.json, outline.json, output/. 실제 AI 사용 내역은 격리 시험의 reports/api-usage.jsonl에 있습니다. 원고/캐시/결과는 Git 제외 대상입니다.
- 자동 테스트 89개 통과. --verify-publication에 고정 응답으로 3/4depth 직접 적용/세 형식 검증을 추가했습니다. 기존 UI 검증은 기존 구조 사용을 명시해 유료 API가 발생하지 않습니다.
- dist-depth-staging의 실제 EXE에서 출판/중단 검증 통과 후 dist-publisher 전체 교체, 설치된 EXE 출판 검증 통과 및 재실행. 이전 실행 파일은 backups/publisher-before-ai-depth-20260923에 보관합니다. 실제 Chapter 1 분석의 검증된 ai-depth 캐시와 최종 구조를 원래 working/<hash>에 추가해 재호출을 방지했습니다(기존 구조/교정 JSON은 수정하지 않음).

## 2026-09-23 Chapter 8 코드 보존 검사 오탐 수정

- 원인: 1줄 코드 `cout << getLarger(10.0, 20.5) << endl;`가 표 안에 있었고 reader는 코드로 분류했지만 scanner는 2줄 이상만 인식했습니다. 기존 17개 코드는 모두 정확히 같았으나 준비/HTML 18개와 개수 불일치로 차단됐습니다.
- scanner가 명확한 1줄 코드도 인식하도록 수정했습니다. 1줄 단일 셀 표는 기존 저장 ID(b00179-r0c0)와 표 구조를 유지합니다. reader의 독립적인 cout/std:: 키워드 판정을 없애고 scanner 결과를 사용하므로 설명 문장을 코드로 오인하지 않습니다.
- 개수/순서 불일치와 실제 문자/들여쓰기 불일치 오류 안내를 구분하고, 검사 보고서 전체 경로를 안내합니다. 검사를 생략하거나 공백 정규화로 우회하지 않습니다.
- 후속 PDF 오류: 그림 여러 개가 든 표의 한 행이 페이지 높이를 초과했습니다. ReportLab Table splitInRow를 활성화해 행 내부 콘텐츠를 여러 페이지에 배치합니다.
- 자동 테스트 81개 통과. 기존 Chapter 8 작업 폴더를 reports/chapter8-singleline-validation로 복사하여 기존 교정 결과를 재사용했고, 유료 API 없이 HTML/PDF/EPUB 전체 보존 QA 통과(코드 18개). 원본 DOCX 및 사용자 작업 JSON 해시 불변 확인. PDF 23~25페이지 시각 확인.
- 결과/검사: reports/chapter8-singleline-validation/result.json. frozen 출판 검증용 원고에도 한 줄 코드 표를 추가했습니다.
- 배포: dist-code-staging 실제 EXE 출판/중단·재개 검증 통과 후 dist-publisher 전체 교체, 설치된 EXE 출판 검증 통과 및 재실행. 이전 버전은 backups/publisher-before-singleline-code-20260923에 보관합니다.

## 2026-09-23 중단 버튼 연결 오류 수정

- 실제 원인: 빠른 제작 GUI가 `cancelled=self.cancel_review.is_set()`로 시작 순간의 bool을 넘겼습니다. publish가 False를 항상 False인 함수로 대체하여 버튼 이벤트를 보지 못했습니다. 이제 bound method를 전달하고 bool 전달은 오류로 거부합니다.
- `core/cancellation.py`의 OperationCancelled와 TaskThread의 별도 cancelled 신호로 정상 중단을 작업 실패와 구분합니다. 상태를 지연된 진행 알림이 덮지 않으며 두 중단 버튼이 함께 비활성화됩니다.
- 빠른 제작 버튼은 중단 후 `이어서 제작`으로 표시합니다. 완료된 문단은 기존 모델·추론·문장 지문 기준으로 재사용하고, 미처리 문단만 다시 요청합니다. 강제 종료가 아닌 정상 중단에서는 현재 API 응답을 저장한 뒤 멈춥니다. 이미 서버에 보낸 요청을 즉시 취소하지는 않습니다.
- HTML 블록/표 행, PDF 블록/표 행/배치 흐름, EPUB 본문/자산, 출력 형식 사이와 QA 전후에 협력적 중단을 확인합니다. AI 교정을 끈 제작에서도 중단 버튼이 활성화됩니다. 단일 이미지 처리/파일 쓰기/QA 검사 중에는 다음 확인 지점까지 기다릴 수 있습니다.
- 중단된 출력은 reports/production-state.json에 cancelled로 남기며 최근 성공 결과로 등록하지 않습니다. 재시작 시 파일은 새 폴더에 다시 생성합니다. 구조 AI가 완료된 경우 검증 결과를 캐시에 저장한 다음 중단합니다.
- 자동 테스트 76개 통과: 실제 GUI 버튼 → 지연 응답 저장 → 중단 완료 → 완료 문단 재호출 없이 재개, 출력 각 단계 중단/새 폴더 재제작, PDF 레이아웃 내부 중단, bool 회귀 방지.
- `--verify-cancellation`은 유료 API 없는 별도 GUI 통합 시험입니다. reports/cancellation-verification/acceptance.json 및 stopped.png를 생성합니다.
- 배포: dist-cancellation-staging에서 실제 EXE 중단·재개/전체 출판 검증 통과 후 canonical dist-publisher/DigitalTextbookMaker 전체 폴더를 교체했습니다. 설치 후 중단·재개 검증도 통과했습니다. 기존 버전은 backups/publisher-before-cancellation-20260923에 보관합니다. 사용자 앱은 정상 종료 후 새 버전으로 재실행했습니다.

## 2026-09-23 교재 디자인 자동 적용

- 자체 제작한 오프라인 테마 3종: 기본 교재형(파랑), 코딩·실습형(청록), 본문 중심형(갈색). GitHub 프로젝트는 방향 참고용이며 외부 테마/폰트/CDN을 가져오지 않았습니다.
- 제작 영역의 `교재 디자인` 기본값은 자동 추천입니다. 코드 블록/실행 결과/코드 표 셀이 있으면 실습형, 표 없이 일반 본문이 8,000자를 넘으면 본문형, 그 외는 기본형입니다. 선택은 QSettings에 보존합니다.
- `디자인 미리보기`는 내장 예시 교재 HTML을 브라우저로 엽니다. 원고를 준비한 상태의 자동 추천은 해당 원고로 테마만 결정합니다. 실제 원고 미리보기나 AI 호출이 아닙니다.
- HTML: 접이식 고정 목차, 현재 절 표시, 모바일 배치, 원문 코드 복사, 표 가로 스크롤, 제목/캡션/실습 영역 스타일. 외부 네트워크 없이 동작합니다.
- PDF: 제목 표지, 장 단위 새 페이지, 제목 계층, 표 배경, 코드 강조선, 페이지 번호와 책갈피. 코드가 6pt 미만으로 축소돼야 하면 실패로 안내하며 줄바꿈을 변경하지 않습니다. PDF는 Windows 맑은 고딕/Consolas 기반이며 웹 본문형의 바탕체와 글꼴이 동일하지는 않습니다.
- EPUB: 같은 테마 색상/계층의 전용 CSS, 탐색 목차. JS/웹 사이드바는 넣지 않습니다. 실제 전자책 기기의 글꼴·표·긴 코드 표시와 EPUBCheck 검증은 별도 후속 항목입니다.
- 출력마다 reports/design.json에 테마 ID/버전/설정을 저장합니다. 원본 DOCX, .env, 기존 working JSON이 그대로임을 실제 원고 시험 전후 해시로 확인했습니다.
- 검증: 자동 테스트 69개 통과. 실제 Chapter 1 HTML/PDF/EPUB 내용·이미지·코드 보존 QA 통과. Chapter 2는 기존 PDF b00095 제로폭 문자 누락 검사만 실패하며 이를 숨기거나 통과로 처리하지 않습니다.
- 브라우저 데스크톱/390px 모바일 화면과 목차 접기/이동, 코드 복사 성공 표시, PDF 표지/내지 PNG를 확인했습니다. IAB 클립보드 읽기 API는 빈 값을 반환하여 실제 붙여넣기까지 검증한 것으로 주장하지 않습니다.
- 검증 파일: reports/design-actual-summary.json, reports/design-validation/, reports/publication-verification/acceptance.json, reports/review-upgrade/exe-flow.json. 모두 로컬 전용입니다.
- dist-design-staging에서 빌드 후 실제 EXE의 --verify-publication(자동/3개 테마 전 형식), --verify-review-flow 통과. dist-publisher/DigitalTextbookMaker 전체 교체 후 설치된 EXE의 --verify-publication도 통과했습니다. 유료 API 호출 없음.
- 실행 경로와 C:/Project/디지털교재 제작.lnk는 동일합니다. 이전 버전 백업: backups/publisher-before-design-20260923. 이번 변경은 아직 Git 커밋/푸시하지 않았습니다.

## 2026-09-23 자동 출판 사전 진단

- 검증: 자동 테스트 63개 통과, 별도 빌드와 설치 후 EXE의 `--verify-publication` 통과. 기존 `--verify-review-flow`도 새 EXE에서 통과. 유료 API 호출 없음.
- 설치: dist-publisher/DigitalTextbookMaker 전체를 검증된 새 폴더로 교체했고 바로가기는 기존 경로를 유지합니다. 이전 정상 빌드는 backups/publisher-before-preflight-20260923에 보관합니다.

- 빠른 제작은 `publishing.publish`를 통해 원고/이미지 보존 및 목차 단서·번호·범위를 교정 API 전에 검사합니다. 통과하면 목차를 출력에 직접 반영합니다. 기존 승인 구조가 우선입니다.
- 제목 스타일 없는 번호형 제목도 인식합니다. 제목 후보 없음, 누락된 상위 수준, 번호 충돌, 제목으로 지정된 서술문, 40문단 초과 미구분 구간은 보완 대상으로 표시합니다. 이 기준은 휴리스틱이며 의미 정확도 보장이 아닙니다.
- 사용자가 'AI 새 제목·목차 재구성 허용'을 선택하면 구조 부족 시에만 기술 검토 모델로 새 제목을 제안합니다. 기본값은 꺼짐. 입력 60,000자 제한을 넘으면 요청 전에 중단합니다. 구조 재검사 통과 후만 교정/출력을 진행합니다.
- 본문은 재작성하지 않습니다. 기존 구조 초안과 승인·거절·보류 기록을 변경하지 않고, 출력물 reports/publication-preflight.json에 사용한 구조를 기록합니다. AI 구조는 원고 지문·모델·추론·정책이 같은 경우 재사용합니다.
- 출력 QA 실패는 완료가 아닌 오류로 보고하고 실패 보고서 경로를 안내합니다. 실패 결과를 최근 성공 출력으로 등록하지 않습니다.
- `python main.py --verify-publication`은 새 구조 자동 출력·무구조 차단·고정 AI 재구성 출력을 검증합니다. 유료 API 호출 없음.


## 집 PC 빠른 제작 개선

- 빠른 제작을 기본으로 하고 단계별 실행·승인 표는 상세 검토로 접었습니다.
- 선택한 교정/교열 모델로 전체 원고의 미처리 문단만 한 번 검토한 뒤 제작합니다. AI 실행 옵션을 끄면 추가 API 호출 없이 제작합니다.
- `core/ai/quick.py`의 작은 허용 목록과 정확히 일치하는 미검토 A 제안만 출력에 적용합니다. 일반적인 띄어쓰기 정규화나 모든 A 항목 자동 승인은 하지 않습니다.
- 자동 적용은 승인 기록을 변경하지 않습니다. 거절·보류·승인 기록이 있는 블록과 코드·표·이미지·링크는 자동 변경하지 않습니다.
- 결과물 reports/quick-changes.html 및 JSON에 변경 내역을 보관합니다. 빠른 제작 옵션을 끄고 재제작하면 기존 승인본으로 돌아갑니다. 이전 출력은 보존합니다.
- 2026-09-23: 불완전했던 dist-publisher를 검증된 빠른 제작 빌드 전체로 복구했습니다. 기본 실행 경로는 dist-publisher/DigitalTextbookMaker/DigitalTextbookMaker.exe이며 C:/Project/디지털교재 제작.lnk도 이 경로를 가리킵니다. 복구 후 EXE 검토 흐름 검증 통과(유료 API 호출 없음). 이전 불완전 폴더는 backups/dist-publisher-broken-20260923에 보관했습니다. 배포 업데이트는 새 폴더에서 검증 후 교체하고 실행 중인 폴더에 직접 빌드하지 마세요.
- Chapter 2 PDF의 제로폭 문자 비교 실패는 이 변경으로 해결하지 않았습니다. QA 실패를 통과로 처리하지 않습니다.


## 2026-09-22 작업 내용

사용자 요청: 장 → 절 → 소단원 제작 기능을 추가하고, 16:50(한국 시간)까지 GitHub에 올린 뒤 남은 작업을 기록합니다.

### 구현한 기능

- 원고 선택 영역에 **장·절·소단원 구성** 창을 추가했습니다.
- Word 제목 스타일·개요 수준·번호에 의한 기본 분석과 AI 분석을 제공합니다. AI는 기술 검토 모델을 사용하며 기존 제목 분류/새 제목 제안을 구분합니다.
- 목차 트리, 범위의 원문·분류 근거, 수준·제목·시작 문단 편집, 추가·삭제, 초안 저장·승인을 지원합니다. 끝 문단과 부모 관계는 자동 계산합니다.
- `core/manuscript/structure.py`: 검증·기본 규칙·AI 입력 보호·승인 저장. 원본과 별도로 `structure.json`에 저장합니다. 초안은 제작을 차단하고 승인한 구조만 적용합니다.
- `core/master.py`: `Block.outline_level`, `Master.outline`을 기본값과 함께 추가해 기존 JSON을 계속 읽습니다. 원문 블록 내용·순서는 수정하지 않습니다.
- `core/export/outputs.py`: HTML h1/h2/h3와 연결 목차, PDF 제목·책갈피, EPUB 계층 탐색 목차를 반영합니다.
- QA는 목차 순서·제목·연결과 PDF 책갈피를 검사하며 기존 코드·본문·이미지 보존 검사를 계속 수행합니다. HTML 코드 검사가 통과해야 PDF/EPUB으로 진행합니다.
- 기존 순차 교정, 밝은 화면, 승인 기록 보존과 코드 공백 보존 기능은 유지합니다.

### 검증

- 자동 테스트 **41개 통과**: 새 구조 검사 9개와 기존 32개. 원본 원고가 없는 새 PC에서는 기존 실제 원고 시험 하나가 생략될 수 있습니다.
- `--verify-structure`: 고정 AI 응답의 성공과 실패, 창 수명, 구조 승인, HTML/PDF/EPUB QA 통과. 유료 API 호출 없음.
- `--verify-review-flow`: 기존 3단계 교정 흐름 통과. 유료 API 호출 없음.
- `dist-publisher/DigitalTextbookMaker/DigitalTextbookMaker.exe`를 다시 빌드한 뒤 위 두 검증을 실제 EXE에서도 통과했습니다. 기존 `dist/DigitalTextbookMaker`는 예전 버전이므로 실행 위치를 구분하세요.
- 실제 Chapter 1을 `reports/structure-actual/`의 격리된 시험 작업으로 제작했습니다. 기본 규칙으로 장 1개·절 4개·소단원 2개를 제안했으며 모든 출력 QA가 통과했습니다. **이 수치는 분류 정답률을 뜻하지 않습니다. 편집자 검토 전 초안입니다.**
- 실제 원본 파일과 기존 작업 JSON 21개가 바뀌지 않았음을 해시로 확인했습니다. 실제 작업의 구조를 대신 승인하지 않았습니다.
- 로컬 검증 보고서와 원고·결과물은 공개 저장소에 올리지 않습니다.

### 다음에 할 작업 (우선순위)

1. **실제 AI 분류 품질 확인**: 실제 원고에 유료 AI 분석은 아직 실행하지 않았습니다. 사용자가 고른 모델로 작은 범위부터 실행하고 편집자가 만든 정답 목차와 비교하세요. 번호 목록·팁·학습목표·요약·연습문제·목차 페이지의 오분류를 중점 확인합니다.
2. **긴 원고 분석**: 현재 AI 입력 JSON은 60,000자 이내입니다. 초과 시 거부하며 자동 잘라내지 않습니다. 장별 분할과 전체 구조 재조정, 중단·재개를 구현해야 합니다.
3. **화면 보완**: 오른쪽은 원문 텍스트와 이미지 개수 표시입니다. 이미지 실제 미리보기·단위별 일괄 이동·구조 변경 이력·승인 취소 전용 버튼을 추가할 수 있습니다. 현재 상위 항목 삭제는 하위 항목부터 정리해야 합니다.
4. **제목 탐지 확대**: 현재 글자 크기·굵기·여백을 종합하는 시각적 분류는 없습니다. Word 스타일/개요/번호 + AI 문맥을 사용합니다. 제목 없는 원고의 새 제목 제안은 검토가 필수입니다.
5. **출력 품질**: PDF 본문에 별도의 페이지 번호 목차는 아직 없습니다(책갈피 지원). EPUBCheck와 실제 기기에서 확인하고, 복잡한 수식·각주·병합 표도 별도 검증하세요.
6. **PDF 직접 입력**: 참고 PDF는 예시 분석용이며 앱 입력은 DOCX입니다. PDF 레이아웃 기반 구조 분석은 후속 범위입니다.
7. **다른 PC 검증**: API 모델 접근·옵션 확인, Windows 글꼴과 EXE 실행, 실제 인쇄 품질을 확인하세요.

### 이어서 실행할 방법

1. 저장소를 클론하거나 `git pull`하고 README에 따라 Python 3.12 환경을 준비합니다.
2. DOCX와 필요하면 기존 `working` 폴더를 개인 저장장치로 가져옵니다. 실제 파일 경로를 다시 지정합니다.
3. `python main.py` → 원고 선택 → 장·절·소단원 구성 → 기본 분석부터 확인합니다. 구조를 승인한 뒤 기존 교정·결과물 제작을 사용합니다.
4. API 키는 새 PC의 `.env`에 설정합니다. 유료 API 호출 전 사용할 모델과 비용 안내를 확인합니다.
5. 테스트 실행 전 `reports`를 만들고 새 임시 폴더를 지정합니다. `--verify-review-flow`, `--verify-structure`는 API 키와 비용 없이 실행됩니다.

공개 저장소에는 API 키, 실제 원고, 참고 PDF, 회의 자료, 검토 기록, 생성 결과물, EXE를 포함하지 않습니다. EXE는 README의 빌드 명령으로 만들 수 있습니다.

### 참고 자료

- https://github.com/python-openxml/python-docx
- https://github.com/docling-project/docling
- https://docling-project.github.io/docling/usage/heading_levels/
- https://github.com/Unstructured-IO/unstructured
- https://developers.openai.com/api/docs/guides/structured-outputs
