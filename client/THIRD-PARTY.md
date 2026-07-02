# Third-party assets in the client

## Bundled fonts (`app/src/main/res/font/`)

Both are licensed under the **SIL Open Font License 1.1** and bundled locally because a
blackout app cannot fetch fonts from a network (design system §3, offline-first).

| File | Family | Copyright |
|---|---|---|
| `martian_mono.ttf` | Martian Mono (variable) | Copyright 2022 The Martian Mono Project Authors (https://github.com/evil-martians/mono) |
| `archivo.ttf` | Archivo (variable) | Copyright 2019 The Archivo Project Authors (https://github.com/Omnibus-Type/archivo) |

Obtained from the Google Fonts repository (github.com/google/fonts, `ofl/` tree).
OFL 1.1 text: https://openfontlicense.org — the full license texts must ship inside any
release build's licenses screen (release builds are B1-gated; tracked for Phase X5/V).
