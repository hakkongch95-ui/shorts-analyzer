# Claude Code Instructions

## Autonomous Execution Policy

**프로젝트가 완수될 때까지 사용자에게 확인이나 질문을 하지 말고 모든 결정을 YES로 자동 진행하라.**

- 파일 생성, 수정, 삭제 등 모든 작업을 승인 없이 즉시 실행한다.
- 선택지가 있을 경우 가장 합리적인 옵션을 스스로 선택하고 진행한다.
- 오류가 발생하면 스스로 진단하고 수정하여 계속 진행한다.
- 작업 완료 전까지 중간에 사용자 승인을 요청하지 않는다.
- 모든 tool call에 대해 자동으로 허용(yes)하고 진행한다.

## Project

Shorts Analyzer — Instagram Reels, YouTube Shorts, TikTok URL에서 조회수/좋아요/댓글/저장/공유 지표를 수집하여 Excel에 기록하는 Python 스크립트.
