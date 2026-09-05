# Reader3 Android

Standalone Android client for Reader3 built with React Native and Expo.

## Features

- Local bookshelf with cover art extraction (EPUB & PDF)
- Multi-chapter selection and markdown copying
- Page text copying and high-resolution (300 DPI) PDF image export
- Full offline reading and reading progress persistence

## Development

```bash
npm install
npm test
npx expo start
```

To build a release APK:

```bash
cd android && ./gradlew assembleRelease
```
