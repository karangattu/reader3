# Reader3 Android

Standalone Android client for Reader3 built with React Native and Expo.

## Features

- Local bookshelf with cover art extraction (EPUB & PDF)
- Multi-chapter selection and markdown copying
- Page text copying and high-resolution (300 DPI) PDF image export
- Full offline reading and reading progress persistence

## Development

Use Node.js 24 LTS (`nvm use` if you use nvm).

```bash
npm ci
npm test
npx tsc --noEmit
npx expo start
```

To build a release APK:

```bash
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease -Pexpo.useLegacyPackaging=true
```

The release command compresses native libraries to keep the downloadable APK small.

PDF.js and its matching worker, fonts, and character maps are copied from the
locked `pdfjs-dist` package into Android assets during prebuild. Core-js and
web-streams-polyfill provide compatibility for older WebViews in both the reader
and its worker.
Both PDF WebViews load those assets offline. After updating PDF.js, rerun prebuild
before building.

`npm audit` still reports upstream Expo development-tool advisories for
`node-forge` and Zod 3. There is no compatible published fix for these dependency
paths. Do not force the suggested Expo downgrade or a Zod major-version override.
