# Data policy for the device catalogue

This document defines what the device catalogue (`data/devices/<brand-id>.jsonl`) may
contain, where its values come from, and how errors and takedown requests are handled.
It applies to every contribution.

## Why this policy exists

The repository is licensed under GPL-3.0. Device specifications are facts — facts are
not copyrightable — but the *selection, images and marketing text* surrounding them
are a manufacturer's property. The catalogue therefore stores only factual
specifications and proves each one with a URL. This is what makes the dataset safe to
publish under GPL-3.0 (see [LICENSE](../LICENSE)).

## What may be stored

| Allowed | Not allowed |
|---|---|
| Factual specifications: U height, width, depth, weight, power draw, port counts/types, mounting style | Vendor images, renders or logos |
| Model designations and brand names (nominative use) | Marketing or descriptive copy from datasheets |
| The URL of the source the values were taken from | Copies of datasheets, PDFs or excerpts of them |
| Your own notes kept in PR descriptions or issues | Values transferred from a competitor catalogue without a source |

Brand names are used to *identify* hardware ("brand nominative use"); they do not imply
endorsement or affiliation. Brand names and models must never be presented as rackplan's
own branding.

## Provenance

- Every device record **must** carry a `source` URL pointing at the manufacturer
  datasheet or the official product page the values were taken from.
- Values are transcribed, not estimated: without a published figure the field is
  omitted. Never `0`, never an approximation, never a value from a third-party database
  without a manufacturer source.
- Where datasheets and product pages disagree, the datasheet wins; the `source` must
  then point at the datasheet.
- Mixed-unit datasheets are normalized (mm, kg, W); the record shows the normalized
  value, and rounding is trivial transcription, not measurement.

## Contributing device data

- Device records follow the schema documented in `README.md` (Data) and are validated
  with `python3 scripts/validate_devices.py`.
- Submit brand datasets as a PR, or individual devices via the device data issue form.
  A contribution naming an unverifiable source will be asked for a better one, not
  merged.
- The contributor certifies that the values come from the cited source and that no
  copyrighted material is reproduced.

## Correcting errors

- Wrong values are fixed in the record; the `source` is updated to the authoritative
  document in the same change. If a value cannot be re-verified, the field is dropped
  rather than kept on a stale citation.
- Obsolete product pages that moved are re-pointed to the closest official page
  (datasheet archive of the manufacturer); web-archived copies only when no official
  page exists.

## Takedown requests

If you are a rights holder and believe a record infringes your rights, open an issue
(without confidential detail) or contact the maintainer via the address in
[`SECURITY.md`](../SECURITY.md). The record is removed or corrected while the case is
reviewed; no rebuttal is required from you beyond identifying the infringing content.
