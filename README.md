# 온먕봇 공지 중계

공개된 메이플스토리 월드·메이플플래닛 점검 공지와 플래닛 패치노트를 온먕봇에 전달합니다. 월드 패치노트는 제외합니다.

- `notice_relay_export.py`: 공식 사이트를 읽어 `feed.json`을 만드는 수집기입니다. Python 3.11 이상과 beautifulsoup4가 필요합니다.
- 실행: `python notice_relay_export.py --output feed.json`
- `feed.json`: 출처별 실제 확인 시각, 성공/오류 상태, 공지 내용을 담습니다. 수집 실패를 새 글 없음으로 처리하지 않습니다.
- 봇은 3시간 넘게 갱신되지 않은 출처와 잘못된 원문 주소를 게시에 사용하지 않습니다.

## DashCloud 설정

GitHub 중계 기능이 포함된 최신 온먕봇 파일을 업로드합니다. 환경 변수 `NOTICE_RELAY_URL`에 다음 주소를 저장하고, 프로젝트 시크릿 주입 허용목록에도 추가한 뒤 재시작하세요.

```
https://raw.githubusercontent.com/ghkscjf7288/onmyang-notice-feed/main/feed.json
```

Discord에서 `/소식 확인`으로 GitHub 중계 모드와 수집 상태를 확인하세요. `/소식 미리보기`는 운영진에게만 표시되고, `/소식 게시`는 설정된 채널에 실제 게시합니다. 점검은 안내 임베드, 플래닛 패치노트는 공개 스레드로 게시합니다.

## 예약과 보안

GPT 예약 작업이 수집기를 실행하여 feed.json을 갱신하도록 설정합니다. 예약 등록 여부와 실행 결과는 ChatGPT에서 확인하세요. 예약이 등록되어도 봇 업로드·환경 변수 설정·Discord 채널 설정은 별도로 필요합니다.

이 저장소에는 공개 공지만 넣습니다. Discord 토큰, API 키, .env, 사용자 DB를 올리지 마세요. 사이트 접근 제한이나 예약 실행 환경의 장애로 수집에 실패할 수 있습니다.
