# Pretendard

마중ON Care 는 Pretendard 를 UI 폰트로 쓴다. (브랜딩 패키지 `theme_tokens.json` 지정)

- 출처: npm `pretendard@1.3.9` / https://github.com/orioncactus/pretendard
- 라이선스: SIL Open Font License 1.1 (`Pretendard-OFL-LICENSE.txt`)
- 포맷: TTF. 안드로이드가 OTF 보다 안정적으로 읽는다.
- 굵기 4종만 넣는다. 4종으로 10MB 가 늘어나므로 더 넣지 않는다.

앱 코드에서 직접 fontFamily 를 적지 말고 `src/ui/Text.js` 를 쓴다.
안드로이드는 굵기별로 패밀리가 따로여서, 그 파일이 fontWeight 를 패밀리로 옮겨준다.
