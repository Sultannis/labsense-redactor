# labsense-redactor

The service that removes personal details from digital lab report PDFs before an AI model reads them. It's part of [LabSense](https://labsenseapp.com), an app for tracking lab results. Users upload their lab reports, and LabSense digitizes them with an AI model. For a digital PDF, this service finds the patient's name, date of birth, ID numbers, contacts and address. The user checks the result, hides or shows more, and only the redacted copy goes to the AI.

It is a small internal HTTP service. Only the LabSense backend calls it, inside a private network, with a service token. It keeps no state: each call reads a PDF from object storage by key and writes its outputs to the keys it's given. It never logs document text or the details it finds.

It's published under the AGPL because it uses [PyMuPDF](https://github.com/pymupdf/PyMuPDF).

## What it does

| Endpoint | Does |
|---|---|
| `POST /detect` | Finds personal details. Returns regions (boxes with a type) and a summary of distinct details per type, never the matched text. Also says whether the pages are scans whose text can't be trusted. |
| `POST /words` | Every word with its box, so the review screen can offer `Hide` on any word. |
| `POST /apply` | Truly redacts the regions and strips what else could carry a detail, writes the copy, then checks it. |
| `POST /rasterize` | Page images (JPEG) with the regions painted black. The backend uses them when the user has to paint over the details by hand. |
| `GET /health` | `{"status": "ok"}`, without the token. |

Boxes are fractions of the page as displayed (with its rotation applied), measured from the top-left corner: `{page, x0, y0, x1, y1}` with `0 ≤ x0 < x1 ≤ 1` and pages counted from 1. Field names are camelCase. Every `POST` needs `Authorization: Bearer $REDACTOR_TOKEN`.

```jsonc
// POST /detect
{"key": "acc/…/…", "pageCount": 2, "known": {"names": ["Anna Example"], "emails": ["anna@example.com"], "birthYears": [1988]}}
// → 200
{"regions": [{"page": 1, "x0": 0.12, "y0": 0.08, "x1": 0.31, "y1": 0.1, "type": "name"}],
 "summary": {"name": 1, "date_of_birth": 1}, "scanned": false}

// POST /words
{"key": "acc/…/…", "pageCount": 2}
// → {"pages": [{"page": 1, "words": [{"text": "Ferritin", "x0": 0.1, "y0": 0.4, "x1": 0.18, "y1": 0.42}]}]}

// POST /apply: regions include the user's own blocks, of type "manual"
{"key": "acc/…/…", "regions": [], "outputKey": "acc/…/…"}
// → {"verified": true, "byteSize": 48211, "sha256": "…"}

// POST /rasterize
{"key": "acc/…/…", "regions": [], "outputs": [{"page": 1, "key": "acc/…/…"}]}
// → {"pages": [{"page": 1, "byteSize": 201113, "sha256": "…"}]}
```

Region types: `name`, `date_of_birth`, `address`, `phone`, `email`, `id_number`, `policy_number`, and `manual` for the user's blocks.

Errors:
- `401`: `{"error": "unauthorized"}`.
- `400`: `{"error": "invalid_request"}`. The default validation answer would echo the input, so this one doesn't.
- `422`: `{"error": "<code>"}`. The codes are `page_count_mismatch`, `encrypted`, `unreadable`, `not_found`, `too_large`, `too_many_pages`, `region_outside_document`, `page_outside_document` and `output_key_elsewhere` (an output must stay beside its input: the same first two key segments).

### Detection

Reports in English and Russian, including Kazakh labs' Russian reports. Each word takes the type of the first finder that claims it:

1. **Known details** from the account: the profile names, matched in either alphabet (`Anna` / `Анна`), in Russian case forms (`Ивановой`) and with one typo in longer names. Also the sign-in email, and full dates in a profile's birth year (`14.03.1988`, unlabeled).
2. **Labeled fields** such as `Patient`, `DOB`, `Address`, `Phone`, `MRN`, `Order #`, `Policy`, `ФИО`, `Пациент`, `Дата рождения`, `Адрес`, `Телефон`, `Полис`, `СНИЛС`, `ИИН`, `ИНЗ` and `№ медкарты`. A value can follow the label, sit in the next cell, or sit under a column heading. Each type checks that its value has the right shape, so a heading such as `Name  Result  Units` hides nothing. Doctors' and lab staff's names are hidden too.
3. **Shapes:** emails; phone numbers; SNILS; SSNs; 16-digit OMS policies; runs of 9 or more digits (IIN, INN, barcodes, record numbers); postal addresses with a street, house or postcode.
4. **Names the model finds:** spaCy's `en_core_web_md` and `ru_core_news_md` named-entity models. A name needs two or more name-like words, so a test name in a table is never taken for one.
5. **Context:** initials next to a hidden name, and a name right before a hidden birth date.

A detail found once is hidden wherever the same words recur, such as a name in every page header. It counts once in the summary.

Kept on purpose: report and sample dates, the lab's name, sex, age and every result row. A date is hidden only when it's labeled as a birth date or falls in a known birth year.

**Scans:** `scanned` is true when a page is a picture under an invisible OCR text layer, or its text can't be read back (a font without a Unicode map). The picture may show details the OCR misread, so the backend sends the user to paint over the pages instead. A scanned answer has no regions and an empty summary.

### Redaction and the check

`/apply` removes the text under each region rather than covering it. It also removes the images and drawings a region fully covers, and draws a black block. Then:

- **Every image is removed** from the copy: logos, QR codes, stamps, signatures. Their pixels can't be checked, and a QR code can hold a link to the full results.
- **Other places a detail can hide are stripped:** metadata and XMP, form fields, annotations, links, attachments, JavaScript and bookmarks.
- **The file is rewritten in full,** so earlier saved versions are dropped.

The check opens the written copy and fails (`verified: false`) if any of these remain:
- text inside a region
- more copies of a hidden word than the user deliberately left visible
- an image, annotation, form field, link or attachment
- metadata
- a changed page count

The backend then falls back to painting.

### Limits

- Text drawn as vector outlines has no text layer. If a page has no text but many drawings, it's flagged as a scan; outlines mixed with real text aren't detected.
- A font without a Unicode map whose codes happen to read as Latin letters looks like readable text and isn't detected.
- A name that's unlabeled, not a profile name, and missed by the model stays visible. The user sees the result before anything is sent and can hide it.

## Running it

Python 3.13 with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run pytest                      # tests: synthetic reports only, never real documents
uv run ruff format --check src tests && uv run ruff check src tests && uv run mypy
REDACTOR_TOKEN=… S3_BUCKET=… uv run python -m labsense_redactor   # http://localhost:8000
```

Or the image:

```bash
docker build --platform linux/amd64 -t labsense-redactor .
docker run -p 8000:8000 -e REDACTOR_TOKEN=… -e S3_BUCKET=… labsense-redactor
```

| Variable | |
|---|---|
| `REDACTOR_TOKEN` | Required, at least 16 characters |
| `S3_BUCKET` | Required |
| `S3_REGION` | Default `eu-central-1` |
| `S3_ENDPOINT`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_FORCE_PATH_STYLE` | For a local S3-compatible store. In AWS, the task role supplies credentials. |
| `PORT` (8000), `WEB_CONCURRENCY` (1), `LOG_LEVEL` (`INFO`) | |

The service needs only `s3:GetObject` and `s3:PutObject` on the bucket. One process holds both models in about 0.8 GB, so 1 vCPU and 2 GB fit one worker. PDF work runs one document at a time per process, since MuPDF isn't thread-safe.

**Logs** are JSON lines with the endpoint, status, timing, page and region counts, the types found and fixed reason codes. Never document text, details, known details, storage keys or tokens.

## Releasing

CI checks every push and builds the image. A `v*` tag publishes `ghcr.io/sultannis/labsense-redactor` and prints its digest in the job summary. Deployments pin that digest.

## License

Copyright (C) 2026 The LabSense authors.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE).
