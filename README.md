<p align="center">
  <a href="https://fluxnote.io">
    <img src="docs/assets/fluxnote-logo.png" alt="FluxNote logo" width="120" height="120" />
  </a>
</p>

# AI Faceless Video Generator — FluxNote API Starter

Turn a prompt or your own narration into a faceless video using the **FluxNote API**. This repository contains small, dependency-free **JavaScript and Python examples** for creating narrated videos for YouTube Shorts, Instagram Reels, and TikTok.

<a href="https://fluxnote.io">
  <img src="docs/assets/fluxnote-studio.png" alt="FluxNote AI creative studio — create images, videos, faceless content and ads. Click to explore FluxNote." width="1200" />
</a>

<p align="center">
  <strong><a href="https://fluxnote.io">Start creating free ↗</a></strong>
  &nbsp; · &nbsp;
  <strong><a href="https://fluxnote.io">Explore FluxNote →</a></strong>
</p>

[Explore FluxNote](https://fluxnote.io/?utm_source=github&utm_medium=referral&utm_campaign=faceless_video_starter&utm_content=readme) · [API documentation](https://fluxnote.io/developers) · [Get an API key](https://app.fluxnote.io/developers?utm_source=github&utm_medium=referral&utm_campaign=faceless_video_starter&utm_content=api_key)

<p align="center"><strong>Follow FluxNote</strong></p>

<p align="center">
  <a href="https://www.instagram.com/fluxnote.io/" title="FluxNote on Instagram"><img src="docs/assets/social/instagram.svg" alt="FluxNote on Instagram" width="44" height="44" /></a>
  &nbsp;
  <a href="https://www.tiktok.com/@fluxnote" title="FluxNote on TikTok"><img src="docs/assets/social/tiktok.svg" alt="FluxNote on TikTok" width="44" height="44" /></a>
  &nbsp;
  <a href="https://www.youtube.com/@fluxnote" title="FluxNote on YouTube"><img src="docs/assets/social/youtube.svg" alt="FluxNote on YouTube" width="44" height="44" /></a>
  &nbsp;
  <a href="https://x.com/fluxnote_" title="FluxNote on X"><img src="docs/assets/social/x.svg" alt="FluxNote on X" width="44" height="44" /></a>
  &nbsp;
  <a href="https://www.linkedin.com/company/fluxnote" title="FluxNote on LinkedIn"><img src="docs/assets/social/linkedin.svg" alt="FluxNote on LinkedIn" width="44" height="44" /></a>
</p>

**Open-source examples, hosted generation.** The code here is MIT licensed. Video generation runs on FluxNote and requires an account, an API key, sufficient credits, and an eligible plan. It is not a local AI model or a free, unlimited generation service.

## What it does

- Generates a faceless video from a prompt or an existing script.
- Supports portrait, landscape, and square inputs through the API.
- Shows a current credit estimate before you authorize generation.
- Saves a private job receipt and resumes polling after an interruption.
- Downloads the completed MP4 without sending your API key to the media host.

```mermaid
flowchart LR
    A[Prompt or narration] --> B[Estimate credits]
    B --> C[Explicit confirmation]
    C --> D[Generate video]
    D --> E[Poll saved job ID]
    E --> F[Download MP4]
```

The two examples implement the same workflow; pick one language. Do not run both for the same intended video, as that would create two separately billed jobs.

## Quick start

Requirements: **Node.js 22+** or **Python 3.9+**. No npm or pip dependencies are required.

```bash
git clone https://github.com/FluxNote-LLC/ai-faceless-video-generator.git
cd ai-faceless-video-generator
```

Create a FluxNote API key with `catalog:read`, `videos:read`, and `videos:write` scopes. Export it in your terminal; never put it in an example JSON file or commit it to Git.

```bash
# macOS / Linux
export FLUXNOTE_API_KEY='YOUR_FLUXNOTE_API_KEY'
```

```powershell
# Windows PowerShell
$env:FLUXNOTE_API_KEY = 'YOUR_FLUXNOTE_API_KEY'
```

The scripts read environment variables; they do **not** automatically load `.env`. Node also supports `node --env-file=.env javascript/generate.mjs ...` if you copy `.env.example` to a private `.env` file.

### JavaScript

```bash
# Inspect available voices and generation options.
node javascript/generate.mjs catalog

# Validate the sample and inspect its current estimated credit cost.
node javascript/generate.mjs estimate examples/ocean-facts.json

# Only run this after reviewing the estimate: this spends credits.
node javascript/generate.mjs create examples/ocean-facts.json --confirm
```

### Python

```bash
python3 python/generate.py catalog
python3 python/generate.py estimate examples/ocean-facts.json

# This spends credits. Do not also run the JavaScript create example.
python3 python/generate.py create examples/ocean-facts.json --confirm
```

On Windows, use `python` instead of `python3` if that is your installed command.

`create` without `--confirm` only estimates. With confirmation, the script prints a receipt filename and video ID, waits up to 15 minutes, and saves `<video-id>.mp4` in your working directory. Existing output files are never overwritten.

The confirmation authorizes generation at the current service price; the estimate is **not** an enforced spending ceiling. No automatic retry is made for failed API requests.

## Examples you can customize

| Example | Input | Purpose |
| --- | --- | --- |
| [Ocean facts](examples/ocean-facts.json) | Prompt | A short educational explainer |
| [History story](examples/history-story.json) | Prompt | A factual historical narrative |
| [Motivation](examples/motivation-script.json) | Supplied narration | Preserve your own spoken text |

To supply your own script, replace the `script` value in the motivation example. Include narration only—not `Hook:`, `Story:`, production directions, or timestamps. Supply **exactly one** of `prompt` or `script`.

```json
{
  "prompt": "Explain why the ocean looks blue in a short educational video.",
  "template": "faceless",
  "voice": "adrian",
  "language": "en",
  "target_duration": 20,
  "aspect_ratio": "9:16"
}
```

Use `catalog` to check current choices before editing the samples. Voice availability, durations, quality, watermarks, and credit costs depend on the service and your account. Target duration is a request, not a guarantee of the exact final runtime.

## Resume without creating another video

Use the receipt filename printed by your chosen script:

```bash
node javascript/generate.mjs resume YOUR_JOB.receipt.json
# Or:
python3 python/generate.py resume YOUR_JOB.receipt.json
```

Both clients can read either language's receipt. Resume only reads the saved video ID and downloads its result; it does not create or cancel jobs. If an output file already exists, move it elsewhere before downloading again.

If the create request had no confirmed response, the receipt may have no video ID. Resume deliberately stops instead of risking another charge. See [recovery and troubleshooting](docs/recovery.md).

Receipts include your prompt or script, the API origin, and an idempotency key, **not your API key**. They are excluded from Git. Keep them private; on Windows, use an account-private folder because this starter does not manage Windows ACLs.

## How the API calls map

| Step | Request |
| --- | --- |
| Inspect choices | `GET /v1/options`, `GET /v1/voices` |
| Validate and estimate | `POST /v1/videos/estimate` |
| Create and render | `POST /v1/videos` with `Idempotency-Key` |
| Check status and final `media_url` | `GET /v1/videos/{id}` |
| Save media | HTTPS request to `media_url`, without API authorization |

The default API origin is `https://api.fluxnote.io`. No separate render endpoint is needed. These examples do not automatically publish to social accounts.

`FLUXNOTE_API_URL` is available for local mock testing or a trusted alternative deployment. Never point it at an untrusted service: it receives your API key. Remote origins must use HTTPS; plain HTTP is accepted only on loopback hosts. API redirects are rejected, and media redirects must remain HTTPS.

## Test without spending credits

Install both runtimes to run the full suite:

```bash
python3 -m unittest discover -s tests -v
node --test tests/javascript.test.mjs
```

Tests use a local mock API and fake media responses—no real key, account, generation, or customer data. GitHub Actions runs the tests on Linux, macOS, and Windows with Node 22 and 24.

## Build something useful

Start with one script, inspect the result, and adapt the inputs for your own workflow. Review facts, rights to supplied content, and the generated video before publishing.

For the hosted application, visit [FluxNote](https://fluxnote.io). For integration details beyond this starter, see the [developer documentation](https://fluxnote.io/developers).

**Ready to create your next video? [Start creating with FluxNote →](https://fluxnote.io)**

## License and support

[MIT](LICENSE) applies to the new example code and documentation in this repository. It does not grant rights to FluxNote's hosted service, proprietary source code, trademarks, or underlying models. Service access and output usage remain subject to applicable service terms.

For example-code bugs, open a GitHub issue with a minimal reproduction and **no credentials, receipts, private prompts, or signed media URLs**. For account or billing questions, email support@fluxnote.io. See [security reporting](SECURITY.md) for sensitive issues.
