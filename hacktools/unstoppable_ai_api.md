# unstoppable.ai — model API key & base URL (hasil eksekusi 2026-11-17)

## Base URL yang hidup

| Endpoint | Uji nyata |
|---|---|
| `https://code.unstoppabledomains.com/v1` | `/v1/models` → **307** ke `https://app.unstoppable.ai/login` (butuh sesi login) |
| `https://unstoppable.ai/v1` | `/v1/models`, `/v1/chat/completions` → **307** login |
| `https://app.unstoppable.ai/` | **308** → `https://unstoppable.ai/` (alias) |
| `https://api.unstoppable.ai/v1/models` | **404** `{"message":"no Route matched with those values"}` (Kong) |
| `https://unstoppable.ai/api/health` | **200** `{"ok":true,"commit":"533fa7d9..."}` (satu-satunya yang publik) |
| `https://releases.unstoppable.ai/` | **200** S3 ListBucketResult |

## Format auth (dari source resmi repo `unstoppableweb/unstoppable-code`)
`clients/desktop/packages/protocol/src/model-gateway/discovery.ts`:

```
GET {baseUrl}/v1/models
authorization: Bearer <API_KEY>
x-api-key: <API_KEY>
anthropic-version: 2023-06-01     # hanya untuk gateway format Anthropic
```

`index.ts`: `apiKey: string().trim().min(1).max(16384).optional()` → key diisi user (BYO key).

## Gateway preset yang didukung (bukan rahasia, ada di source)
| Preset | baseUrl |
|---|---|
| OpenRouter | `https://openrouter.ai/api` |
| Vercel AI Gateway | `https://ai-gateway.vercel.sh` |
| Requesty | `https://router.requesty.ai` |
| LiteLLM (self-host) | `<url-mu>` |

Model contoh yang disarankan source: `anthropic/claude-opus-5.5`, `anthropic/claude-sonnet-5.5`,
`anthropic/claude-haiku-5.5`, `openai/gpt-6.1-sol`, `openai/gpt-6.1-terra`, `openai/gpt-6-luna`.

## Billing
`AI_CREDIT_USD_PER_CREDIT = 0.15` (source `billing/index.ts`) → 1 AI credit = $0.15 biaya gateway.

## API key model: TIDAK ADA yang hardcoded
- 22 bundle JS produksi `unstoppable.ai` + 23 bundle `unstoppabledomains.com`: nol `sk-`, `sk-ant-`,
  `sk-or-v1-`, `gsk_`, `AIza`, `hf_` (sudah di-grep, hasil kosong).
- Repo publik: nol base URL hosted-model + nol key; key diterbitkan lewat `/settings/api-keys`
  yang 307 ke login.
- Jadi jalur key: login → Settings → API keys, atau bawa key sendiri dari OpenRouter/Vercel/Requesty.

## Repo/bukti lokal
`$HOME/hacktools/ai_all/` (22 bundle), `$HOME/hacktools/urepo/` (clone 230 MB),
`$HOME/hacktools/ai_home.html`
