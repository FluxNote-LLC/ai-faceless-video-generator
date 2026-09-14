# Recovery and troubleshooting

## Interrupted polling or download

Keep the printed `.receipt.json` file. Run `resume` with that file to poll the same video. Closing the terminal, pressing Ctrl+C, or reaching the 15-minute wait limit does not cancel a server job.

If the result requires review, open FluxNote and complete that step before resuming. If generation failed, inspect the video's credit settlement in FluxNote before deciding whether to start another job.

## Create request with an uncertain outcome

The receipt is saved **before** submission, with one idempotency key and the exact input. If the network fails or the process stops before saving the response, it may not have a video ID.

1. Do not repeat `create`: that generates a fresh key and can create a second billed job.
2. Check your videos in the FluxNote application. If you find the matching job, set the receipt's `id` to that video's ID and use `resume`.
3. If you cannot establish the outcome, contact support. Keep the receipt locally; share only the identifiers needed to investigate.
4. An integration implementing replay must use the **same idempotency key and exact original input**, after checking the service's current replay guarantees. This starter does not automatically replay uncertain submissions or assume keys are retained forever.

## Common errors

| Error | What to check |
| --- | --- |
| HTTP 401 | API key is missing, invalid, or revoked |
| HTTP 403 | Key scopes or account access |
| HTTP 402 | Available credits |
| HTTP 409 | An existing idempotency key is being used incompatibly |
| HTTP 422 | Current catalog, required fields, or script formatting |
| HTTP 429 | Wait for `Retry-After` before retrying; do not loop on writes |
| Connection failure | Connectivity or a refused API redirect; preserve any receipt |
| Wait timed out | Resume polling; the server job continues |
| Output exists | Move the existing MP4, then resume; no files are overwritten |
| Download failed | Resume to refresh the media URL; check connectivity |

The clients intentionally do not print raw error-response bodies, which could contain private input. HTTP status and local guidance are provided instead.

## Cost and privacy boundaries

- Estimates do not create videos. `--confirm` explicitly authorizes a generation request that spends credits.
- Neither client implements a hard credit cap or automatic cancellations.
- Samples default to one video per command. Run paid live tests sequentially.
- Receipts contain your input and must remain private. POSIX files are created with mode `0600`; use a private Windows directory with appropriate inherited permissions.
- Your key goes only to the configured API origin, never to the media download request.
- Do not share `.env`, receipts, private scripts, or signed URLs in public issues.
