# 수업 전용 디지털교재 제작 MVP

Windows에서 DOCX 원고를 자동으로 준비하고 사람이 승인한 교정 제안만 반영해 HTML, PDF, EPUB을 만드는 데스크톱 시험판입니다. GUI와 제작 엔진은 분리되어 있습니다.

## 새 PC에서 시작하기

Windows에서 Git과 Python 3.12를 설치한 후 PowerShell에서 실행하세요.

```powershell
git clone https://github.com/hckim-prog/digital-textbook-production-mvp.git
cd digital-textbook-production-mvp
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

`.env`의 `OPENAI_API_KEY=` 뒤에 본인의 API 키를 넣고 저장한 뒤 실행합니다. 이미 `.env`가 있다면 예제 파일을 다시 복사하지 마세요. 키를 채팅이나 GitHub에 올리지 마세요.

```powershell
.venv\Scripts\python.exe main.py
```

원고 분석·출력과 고정 응답 시험은 API 키 없이 사용할 수 있습니다. 실제 AI 교정·연결 테스트·모델 비교에는 인터넷과 사용 가능한 API 키가 필요하며 사용료가 발생할 수 있습니다. 설정의 모델 ID·지원 옵션·단가는 계정 접근 권한과 현재 제공 정보에 맞춰 확인하세요.

**[다음 작업과 인수인계](docs/NEXT_SESSION.md)**: 장·절·소단원 기본 분석, AI 제안, 편집·승인과 출력 연계를 추가했습니다. 실제 AI 분류 정확도 평가는 후속 작업입니다.

공개 저장소에는 소스와 테스트·설정 예제만 포함합니다. 실제 원고, 참고 PDF, `.env`, 작업 기록, 생성 결과물, 백업, EXE는 포함하지 않습니다. 이전 승인·보류를 이어가려면 원고와 `working/` 폴더를 개인적으로 별도 이동하세요. EXE는 아래 빌드 명령으로 새 PC에서 만들 수 있습니다.

## 현재 상태

- 원고 선택 → AI 교정 설정 → AI 교정 → 교정 결과 검토 → 결과물 제작의 5단계 화면입니다.
- Chapter 1 원고의 코드 블록 6개를 원본 DOCX·중간 원고·HTML·PDF·EPUB에서 대조했습니다. PDF는 실제 출력 글자와 줄 위치까지 검사합니다.
- EPUBCheck와 실제 원고의 복잡한 수식·각주 검증은 아직 진행되지 않았습니다. 원본에 이런 요소가 있으면 QA 결과와 출력물을 직접 확인해야 합니다.
- 빌드한 실행파일 위치는 `dist-publisher/DigitalTextbookMaker/DigitalTextbookMaker.exe`입니다. 공개 저장소에 EXE는 포함하지 않습니다. 폴더 전체를 함께 보관하세요. 다른 PC에서의 실행과 인쇄 품질은 추가 검증이 필요합니다.
- 시험 원고는 사용자가 지정한 Google Drive의 Google 문서를 DOCX로 내보낸 파일입니다. Drive 원본은 변경하지 않았습니다.
- Chapter 1·2의 대표 문단 각 1개로 교정 제안과 토큰 기록을 시험했고, Chapter 2의 대표 문단 1개를 2개 모델로 비교해 HTML·CSV·Markdown 보고서를 생성했습니다.

## 설치 및 실행

Python 3.12와 pip가 필요합니다. 이 PC에서는 프로젝트의 `.venv`에 필요한 패키지가 설치되어 있습니다.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

또는 `run_mvp.bat`을 실행합니다. 이 배치 파일은 기존 `.venv`를 사용합니다.

## 화면 사용법

화면은 Windows 테마와 관계없이 밝은 회색·흰색으로 표시합니다. 교정 표는 행을 번갈아 구분하고, 상태는 글자와 옅은 색으로 함께 표시합니다. 원문에서 삭제·변경된 부분과 수정 제안에서 추가·변경된 부분에는 색과 밑줄을 적용합니다. 이 강조는 화면 표시용이며 원고 내용을 바꾸지 않습니다. 행을 두 번 클릭하면 원문과 수정 제안을 나란히 보는 비교 창이 열립니다.

1. **① 원고 선택**에서 DOCX를 지정하면 자동으로 준비하고 본문·이미지·코드·표·링크 개수를 보여줍니다. **이전 작업 불러오기**로 검토 상태와 지난 결과물을 복원합니다.
2. **② AI 교정 설정**에서 역할별 모델을 선택합니다. **고급 설정**에서 추론 강도를 바꿀 수 있습니다.
3. **③ AI 교정**에서 이번 검토 단계와 범위를 선택하고 **AI 교정 시작**을 누릅니다. 기본 범위는 전체 원고이며, 코드·표 등 보호 영역을 제외한 실제 대상 수가 표시됩니다. 일부 문단 시험을 선택하면 문단 수를 지정할 수 있습니다. 같은 단계·모델·추론 설정·입력 문장으로 성공한 문단은 다음 실행에서 건너뛰므로 남은 문단부터 이어집니다. 의도적으로 다시 실행하려면 재검토 선택란을 켜세요. 중단 버튼은 현재 요청이 끝난 뒤 멈추고 완료된 제안을 저장합니다.
4. **④ 교정 결과 검토**에서 항목을 승인·거절·보류합니다. **교정/교열 실행 → 제안 검토 → 기술 검토 실행 → 제안 검토 → 최종 검토 실행 → 제안 검토** 순서로 진행하면 앞 단계의 승인 내용이 다음 단계로 전달됩니다. 필요한 단계만 실행할 수도 있습니다. 기본 목록은 현재 단계이며 필터로 다른 단계나 전체 기록을 볼 수 있습니다. 여러 행을 선택할 수 있고, 긴 제안은 두 번 클릭하면 전체와 상태 변경 이유를 볼 수 있습니다.
5. **⑤ 결과물 제작**에서 저장 폴더와 HTML/PDF/EPUB을 선택하고 제작합니다. 승인한 수정만 적용됩니다. 결과물 품질 확인과 결과 폴더 열기는 제작 후 활성화됩니다.

### 장·절·소단원 구성

1. DOCX 준비 후 **① 원고 선택 → 장·절·소단원 구성**을 엽니다.
2. **기본 분석 (무료)**은 Word 개요 수준·제목 스타일·번호를 읽어 초안을 만듭니다. 스타일이 잘못 쓰인 원고에서는 결과를 직접 확인해야 합니다.
3. **AI 구조 분석**은 ②에서 선택한 기술 검토 모델과 추론 강도를 사용합니다. **기존 제목 분류** 또는 **제목 없는 본문에 새 제목도 제안**을 선택할 수 있습니다. 비용 안내 후 호출하며 코드·표·그림·수식 등 보호된 내용은 전송하지 않습니다.
4. 왼쪽 목차에서 항목을 선택하면 오른쪽에 해당 범위의 원문과 근거가 표시됩니다. 수준·시작 문단·제목을 바꾸고 **선택 항목 수정**을 누릅니다. 항목 추가·삭제도 가능합니다. 종료 문단은 다음 동급/상위 제목 직전으로 자동 계산합니다. 상위 항목을 삭제하려면 하위 항목부터 정리하세요.
5. 원문 제목 사용을 해제하면 새 제목을 본문 앞에 추가합니다. 원문 문단은 삭제하거나 재작성하지 않습니다. 첫 장은 원고 첫 문단에서 시작해야 하며 도입 부분도 포함합니다.
6. **초안 저장**은 승인과 다릅니다. 저장된 초안이 있으면 결과물 제작이 중단됩니다. **구조 승인 및 저장** 후 제작하면 HTML의 h1/h2/h3·목차, PDF 제목·책갈피, EPUB 탐색 목차에 반영됩니다. 구조를 전혀 설정하지 않은 기존 작업은 이전 방식으로 제작할 수 있습니다.

구조는 `working/<원본 해시>/structure.json`에 원고 지문·상태·분류 근거와 함께 저장되며, 승인된 중간 원고의 `outline`에 연결됩니다. 원래 블록 ID·내용·순서는 유지됩니다. AI 분석은 현재 전체 입력 JSON 60,000자 이내로 제한하며 초과 시 임의로 자르지 않고 안내합니다. PDF 직접 입력, 긴 원고의 분할 분석, 이미지 자체 미리보기는 아직 지원하지 않습니다.

**고급 도구**에 API 연결 확인, 모델 사용 가능 여부, 모델 비교를 모았습니다. API 확인과 교정·비교에는 토큰 비용이 발생합니다. 비교 보고서의 승인률은 승인 / (승인 + 거절)이며, 보류와 미검토를 제외합니다. 검토 전에는 0% 대신 미검토로 표시합니다.

### 단계·분류·상태의 의미

- 교정/교열은 문장 표현, 기술 검토는 기술 설명, 최종 검토는 앞 단계 승인문을 포함한 의미·용어 일관성을 검토합니다. 최종 검토도 수정 제안만 만들며 자동 승인하지 않습니다. 제외된 코드의 실행 검증이나 문서 전체에 대한 정확성 보증은 아닙니다.
- 분류는 **A 단순 교정 / B 편집 검토 / C 기술 확인 / D 원본 보호**입니다. 승인 여부를 뜻하지 않습니다.
- **보류**는 사용자가 직접 선택한 상태입니다. 같은 단계·같은 문단의 다른 제안을 승인하면 기존 승인 제안은 **대체됨**으로 표시합니다.
- 앞 단계의 승인 내용을 바꿔 기준 문장이 달라지면 후속 제안은 **다시 검토 필요**로 표시하고 출력에서 제외합니다. 해당 단계를 다시 실행해야 합니다.
- 완료 안내는 성공·실패·미처리 문단 수를 구분합니다. 일부 실패나 중단 후에는 남은 대상을 다시 실행할 수 있습니다. 문단별 결과는 실행 종료 또는 정상 중단 때 저장되며, 강제 종료 시 진행 중 실행의 제안은 보존되지 않을 수 있습니다.

### 이전 버전에서 작업을 이어갈 때

이전 검토 기록은 읽기 전용으로 보존합니다. 새 검토를 처음 실행할 때 **기존 승인문을 기준 원고로 복사**하고 별도의 순차 검토 기록을 만듭니다. 이전 보류·미검토 제안은 새 원고에 적용하지 않습니다. 예전 보류에는 변경 사유가 없으므로 사용자의 선택인지 과거 자동 변경인지 소급해서 판정하지 않습니다.

## 파일 위치

| 파일 | 위치 |
|---|---|
| 작업 복사본·중간 원고·교정 제안 | `working/<원본 해시>/` |
| 새 순차 검토·기준 원고·단계별 입력 | `working/<원본 해시>/review-v2/` |
| 장·절·소단원 초안·승인 구조 | `working/<원본 해시>/structure.json` |
| HTML·PDF·EPUB | `<선택한 폴더>/<원고명>_<날짜시간>/HTML·PDF·EPUB/` |
| 품질 검사 | `<작업 폴더>/reports/QA-report.html`, `qa.json` |
| 코드 원문 대조 | `<작업 폴더>/reports/code-fidelity.json` |
| PDF·EPUB 포함 코드 검사 | `<작업 폴더>/reports/code-output-fidelity.json` |
| 출력에 반영한 원고·검토 기록 | `<작업 폴더>/reports/approved-master.json`, `review-decisions.json` |
| 새 검토의 출발 원고·이전 승인 근거 | `<작업 폴더>/reports/review-baseline.json`, `legacy-review-decisions.json` |
| 모델 비교 HTML·CSV·Markdown | `reports/model-comparison/<날짜시간>/` |
| API 호출 기록 | `reports/api-usage.jsonl` |

원본 DOCX와 `.env`는 수정하지 않습니다. `input/`, `working/`, `output/`, `reports/`, `logs/`, `.env`는 Git 추적에서 제외합니다.

## 설계

`app/gui`는 화면, `app/controllers`는 작업 순서, `core`는 DOCX·AI·출력·QA를 맡습니다. Core는 GUI 없이 Python 코드와 테스트에서 호출할 수 있습니다.

중간 원고로 **JSON + 별도 이미지 파일**을 선택했습니다. Pandoc Markdown 단독보다 블록 ID, 원본 순서, 이미지 관계, 표, 승인 상태를 연결하기 쉽고, 구조화 HTML 단독보다 교정 제안과 원문을 안전하게 대조하기 쉽습니다. JSON은 사람이 직접 편집하기보다는 GUI에서 승인하고 필요하면 파생 HTML·Markdown을 검토하는 방식입니다.

DOCX는 `python-docx`와 OOXML 본문 순회로 문단·표 순서를 읽고, 이미지 관계 ID로 자산을 추출합니다. 코드·실행 결과·표·이미지와 URL·수식·이진수는 AI 자동 적용 대상에서 제외합니다. 숫자와 수학 기호가 달라진 수정 제안도 거릅니다. 현재 스타일 추론은 휴리스틱이므로 실제 두 원고에 맞춘 조정이 필요합니다.

코드 영역은 Word의 줄바꿈·탭·공백·빈 줄을 그대로 Structured Master의 `code-block`으로 보관하고 HTML/EPUB에서 `<pre class="code-block"><code>…</code></pre>`로 출력합니다. HTML 생성 직후 원본 DOCX, Master, HTML의 코드 블록 개수·순서·각 줄·들여쓰기·빈 줄을 정확히 비교합니다. 하나라도 다르면 제작을 중단하며 PDF/EPUB으로 진행하지 않습니다. PDF는 고정된 줄 간격과 고정폭 글꼴로 코드를 출력하고, 탭은 4칸 탭 정렬로 표시합니다. 원래 탭/공백 문자열은 PDF 내부 검사 자료에도 보관합니다. 실제 PDF의 글자·행 위치와 EPUB의 내용을 다시 읽어 대조합니다.

품질 검사는 본문·숫자·표 내용·그림 개수와 순서·링크·수식을 실제 출력에서 확인합니다. 이미지가 포함된 문단은 문장 사이의 원래 이미지 순서를 유지합니다. 수식은 선형 표기로 변환하고 원본 수식 XML을 보관하며, 품질 보고서에 육안 검토 안내를 표시합니다. PDF를 Word와 같은 페이지 배치로 복제하는 기능은 아닙니다. 복잡한 수식·병합 표·각주·내부 링크와 특수 목록 형식은 추가 검증이 필요합니다. 이미지·수식·링크가 섞인 문단과 표는 보존을 우선해 AI 교정에서 제외합니다.

AI 응답은 JSON으로 받고 블록 원문 일치 여부를 확인합니다. 실패 시 무한 재시도하지 않으며 호출별 성공 여부와 토큰을 기록합니다. 역할별 모델, 표시 이름, 추론 옵션, 표준 텍스트 단가는 `config/models.yaml`에서 관리합니다. 현재 [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), [Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)와 기존 Mini·5.1을 등록했습니다. 캐시 입력 할인과 대용량 할증은 추정치에 반영하지 않으며 가격 변동 시 설정을 갱신해야 합니다.

## 설정과 오류 해결

- `.env`에 `OPENAI_API_KEY`가 필요합니다. 키는 화면과 보고서에 기록하지 않습니다.
- 모델 ID, 표시 이름, 설명, 추론 강도, 가격, 문단 제한은 `config/models.yaml`에서 수정합니다. **사용 가능한 AI 모델 확인**은 API 목록과 설정 후보를 비교하며, **API 연결 상태 확인**은 실제 선택 모델로 짧은 Responses 요청을 보냅니다. 모델을 자동 변경하지 않습니다.
- PDF는 Windows의 맑은 고딕, Consolas, Segoe UI Symbol 글꼴을 사용합니다. 글꼴이 없으면 PDF를 생성할 수 없습니다.
- 원본 DOCX가 분석 후 변경되면 다시 분석해야 합니다.
- 이미지·표·수식이 많은 원고는 생성 파일과 QA를 함께 검토하세요. EPUBCheck는 아직 통합되지 않았습니다.
- API 연결 실패 시 키, 네트워크, 모델 접근 권한과 사용 한도를 확인하세요.

## 테스트와 EXE

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp reports/test-new-run
```

`dist-publisher/DigitalTextbookMaker/DigitalTextbookMaker.exe`를 실행합니다. 폴더 전체가 함께 있어야 합니다. 이 프로젝트 안에서 실행할 때는 프로젝트 루트의 설정·작업·기존 `.env`를 공유합니다. 다른 위치로 배포할 때는 `.env`를 EXE와 같은 폴더에 별도로 배치하세요. 빌드에 API 키를 포함하지 않았습니다. 기존 `dist`, `dist-fixed`, `dist-workflow`는 이전 버전입니다.

소스에서 다시 빌드할 때는 다음 명령을 실행합니다.

```powershell
.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist-publisher --workpath build-publisher DigitalTextbookMaker.spec
```

이 PC의 번들 Python 런타임에 포함된 `icuuc.dll`은 Qt와 호환되지 않아, 빌드 설정에서 이 DLL을 제외하고 Windows 시스템 DLL을 사용합니다.

배포본 검증은 개발용 `--verify-local` 옵션으로 실행할 수 있습니다. 실제 API 연결 검사까지 하려면 `--verify-api`를 함께 지정합니다(짧은 유료 요청 1회). 일반 실행에는 검증 옵션이 필요 없습니다. 결과는 `reports/publisher-audit/exe-acceptance.json`에 기록됩니다.

`--verify-review-flow`는 별도 시험 원고와 고정 응답으로 GUI의 세 단계 승인·결과물 제작을 확인합니다. 유료 API를 호출하지 않으며 결과는 `reports/review-upgrade/exe-flow.json`에 기록됩니다.

`--verify-structure`는 고정 응답으로 구조 분석의 성공·실패, GUI 승인과 세 형식의 목차·원문 보존을 확인합니다. 유료 API를 호출하지 않으며 `reports/structure-verification/acceptance.json`과 화면 캡처를 남깁니다.
