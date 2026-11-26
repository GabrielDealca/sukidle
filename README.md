# Sukidle (working name) — Philippine Supermarket Price-Guessing Game

> **For Claude Code:** This README is the project brief and build plan. Read it fully before writing code.
> Work phase by phase (see **Build Phases**). **Phase 0 is discovery only.** Report your findings and
> wait for approval before you write the scraper.

---

## ⚠️ Top priority: working functionality first, UI design last

**The goal right now is a working proof of concept, not a polished product.**

1. **Function before form.** Data in → puzzle scheduled → guesses checked on the server → correct result back.
   This loop must work end to end and be tested before any time goes into visual design.
2. **The v1 UI is deliberately plain.** Unstyled or minimally styled HTML/React is fine: a product image, name,
   size, a price input, a list of guesses with higher/lower/close, and a result message. No animations, themes,
   custom fonts or illustrations yet.
3. **The design concept in §7 is the future direction, not v1 scope.** Don't build the cash register / receipt / online-cart
   UI, seasonal themes or Taglish copy until the owner signs off that the proof of concept works.
4. **When in doubt, choose the simpler option** that proves the idea (e.g. a CSV import over a full scraper,
   no Redis until throttling actually matters). Infrastructure choices are fixed, though: PostgreSQL everywhere,
   deployed to AWS via GitHub Actions (§2, §12).
5. **Definition of "proof of concept done":**
   - [ ] Real product + price data loaded (≥30 items is enough at first)
   - [ ] A puzzle is chosen for today (Asia/Manila date)
   - [ ] A player can submit up to 6 guesses and gets correct higher / lower / close / win feedback
   - [ ] The answer is never exposed to the client before the game ends
   - [ ] Refreshing the page keeps the player's progress for the day
   - [ ] Automated tests cover the rules and the answer-hiding behavior
   - [ ] Runs locally with one command

---

## 1. What we're building

A daily, Wordle-style browser game for Filipino shoppers. Each day shows **one supermarket product**
(photo, name, pack size). Players get **6 guesses** to land within **5%** of its real shelf price in pesos.

- Feedback per guess: **higher / lower**, plus **"close"** when within 25%.
- One puzzle per day. The day rolls over at **00:00 Asia/Manila**.
- No account needed to play. Stats and streaks live on the device.
- An optional account (for leaderboards and prizes) comes later.
- Prices come from **SM Markets** (SM Supermarket / SM Hypermarket / Savemore), as fixed snapshots taken from the **smmarkets.ph website**.
  Whether a reference branch is needed depends on Phase 0: if the site's prices vary by selected store, we pin one
  branch per snapshot; if they don't, the branch concept is dropped and prices are recorded as the online price.

Inspiration: Costcodle (US, Costco). This version is built for the Philippines, with local UI,
local products and Taglish copy.

### Non-goals (for now)
- No live/real-time pricing. Prices are **dated snapshots**.
- No ad networks. Money comes from partnerships and sponsorships (see §9).
- No native mobile app. Build a responsive web app / PWA only.

### Brand rules (important)
- Do **not** use "SM" in the product name, domain, logo or app icon.
- Do **not** use SM logos, SM brand colors or copied SM page layouts.
- Show this disclaimer in the footer and on the About page: *"Independent fan project. Not affiliated with,
  endorsed by, or sponsored by SM Retail Inc. or any of its affiliates. Prices are reference snapshots
  and may differ in stores."*
- The game name must be configurable (`APP_NAME` env var, default `Sukidle`), because it may change.

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.12, Django 5 + Django REST Framework** | The owner's main stack. Django admin gives us a free curation UI. |
| Database | **PostgreSQL 16 on AWS RDS** (local: Postgres in Docker) | Relational data, JSONB for raw scrape payloads, solid date/time-zone handling. Managed backups. |
| Cache / rate-limit | **Redis** (container on the EC2 box; add it only when throttling/leaderboards need it) | Caches the daily puzzle, throttles the guess API, holds leaderboard sorted sets. |
| Jobs | **Django management commands + cron** (Celery later, only if needed) | Scrapes run rarely. Keep it simple. |
| Scraping | **httpx** (JSON endpoints) → **Playwright** fallback (rendered pages) | Prefer the site's own JSON calls. Use a browser only if we must. |
| Frontend | **React + Vite + TypeScript, Tailwind** | Simple SPA that talks to the DRF API. |
| Source control & CI/CD | **GitHub** + **GitHub Actions** | Tests on every PR; automatic deploy to AWS on merge to `main`. |
| Hosting | **AWS EC2** (one small instance) running Docker Compose: nginx + Django/gunicorn (+ Redis later). nginx also serves the built React app. | Simple, cheap, matches what the owner already runs. |
| DNS | **AWS Route 53** | Domain's hosted zone; A record → EC2 Elastic IP. |
| Images | **AWS S3** (+ CloudFront later if needed) | Store our own processed copies. Never hotlink the source site. |

Local dev: `docker compose up` must bring up everything (Postgres included). **Use PostgreSQL everywhere** (local, CI and production), not SQLite.

**Fixed infrastructure decisions (don't swap these out):** GitHub, GitHub Actions, AWS EC2, AWS Route 53,
AWS RDS (PostgreSQL). See §12 for the deployment setup.

---

## 3. Repository layout

```
/
├── README.md                 ← this file
├── docker-compose.yml        # local dev (includes Postgres)
├── docker-compose.prod.yml   # EC2 (no Postgres; uses RDS)
├── .env.example
├── .github/workflows/
│   ├── ci.yml                # lint + tests on PRs
│   └── deploy.yml            # build + deploy to EC2 on push to main
├── deploy/
│   ├── nginx/                # nginx config (serves frontend build, proxies /api and /admin)
│   └── scripts/              # deploy.sh run on the EC2 host, migrate, collectstatic
├── backend/
│   ├── manage.py
│   ├── config/               # settings (base/dev/prod), urls, wsgi
│   ├── catalog/              # stores, branches, products, prices, images
│   ├── ingest/               # scrapers, normalizers, import commands
│   ├── puzzles/              # daily puzzle scheduling + game API
│   ├── players/              # anonymous players, accounts, stats
│   ├── leaderboard/
│   ├── promos/               # campaigns, partner vouchers, winners
│   └── tests/
└── frontend/
    ├── src/
    │   ├── components/       # Register, Receipt, ProductCard, Keypad, ShareCard…
    │   ├── themes/           # seasonal themes (default, pasko, summer, back-to-school…)
    │   ├── i18n/             # en + taglish copy
    │   └── api/
    └── public/
```

---

## 4. Data extraction (the core of the backend)

### 4.0 Phase 0 — Discovery (do this first, write no scraper yet)

Investigate **smmarkets.ph** and report back with:

1. **robots.txt and Terms of Use.** Quote anything relevant to automated access. If the terms forbid
   scraping, **stop** and recommend the manual path (§4.4) instead.
2. **How product data loads.** Open product listing and product detail pages and inspect network requests.
   Look for a JSON/GraphQL API (common on e-commerce platforms such as Magento, Shopify, VTEX or custom).
   Record:
   - endpoint URLs, method, required headers/cookies
   - how the **branch/store** is selected (cookie, header, query param), since prices may differ by branch
   - pagination scheme and page size
   - fields available: id, SKU/barcode, name, brand, size/unit, price, sale price, image URLs, category
3. **Category tree.** List the top-level categories and roughly how many products each has.
4. **A sample of 5 products**, given as normalized JSON (see §5 schema).
5. Recommendation: `httpx` JSON client vs Playwright, and the expected request volume for a full category crawl.

Write the findings to `docs/discovery.md`. **Wait for approval.**

### 4.1 Scraping rules (non-negotiable)

- **One reference branch** (configurable, e.g. a Metro Manila SM Supermarket). Never mix branches within one snapshot.
- **Be polite.** Max ~1 request/second, random jitter, honest User-Agent naming the project and a contact email.
  Back off on 429/5xx. Never get around blocks, CAPTCHAs or logins.
- **Rarely.** Take a full snapshot **monthly** at most. Puzzles use the price from the snapshot dated nearest to the puzzle.
- **Fetch only what we need.** Product metadata and price. No user data, reviews or anything behind a login.
- Store the **raw response** (JSONB) next to the normalized record, so we can re-parse without re-fetching.
- Every scrape is a `ScrapeRun` row: started/finished timestamps, branch, counts, errors.

### 4.2 Pipeline

```
fetch (ingest.sources.smmarkets)  →  raw_payloads (JSONB)
   → normalize (ingest.normalize)  →  Product / PriceSnapshot upserts
   → enrich (pack-size parse, unit price, category map)
   → curate (Django admin: mark puzzle-worthy, fix names, pick photo)
   → schedule (puzzles.scheduler)  →  DailyPuzzle rows
```

Management commands:

```
python manage.py scrape_smmarkets --branch=<code> [--category=<slug>] [--dry-run]
python manage.py normalize_run <scrape_run_id>
python manage.py import_csv path/to/manual_prices.csv     # manual path, §4.4
python manage.py fetch_images --missing-only
python manage.py schedule_puzzles --days=60
```

Design the source as a pluggable adapter (`ingest/sources/base.py` → `SourceAdapter` with
`list_categories()`, `iter_products(category)`, `parse(raw) -> NormalizedProduct`), so we can add Puregold,
Robinsons or manual sources later without touching downstream code.

### 4.3 Normalization details

- **Money:** store as integer **centavos** (`price_centavos`). Never use floats.
- **Pack size parsing:** `"Lucky Me Pancit Canton Original 60g x 6"` → `size_value=60, size_unit=g, pack_count=6`.
  Handle `g, kg, ml, L, pcs, pack, sachet, tie-pack, x N`. Unit tests with ≥40 real-world strings.
- **Sale vs regular price:** store both. The puzzle answer is **always the regular price** (owner decision).
  The sale/promo price is still stored (on `PriceSnapshot`, and copied to `DailyPuzzle.promo_price_centavos`
  on themed days) for partnership and sponsorship use, e.g. "today's item is on promo at ₱X" sponsor slots. It is
  never used to check guesses.
- **Dedup key:** barcode/SKU when available. Otherwise `(source, source_product_id)`.
- **Name cleanup:** trim promo noise ("NEW!", "BUY 1 TAKE 1") but keep brand + variant + size.

### 4.4 Manual / fallback path

Needed if the terms forbid scraping, or to add items the site doesn't list:

- CSV import with columns `name, brand, size_text, price_php, branch, observed_on, photo_path, barcode, category`.
- Prices observed in-store (shelf-tag photos) are tagged `source=manual_instore`.
- Admin form for one-off entries.

### 4.5 Images

- Download once, resize (800px max, WebP), upload to S3. Keep `source_url` and `license_note`.
- Prefer, in order: our own photos → manufacturer press/product images → source-site images (flagged for review).
- The frontend only ever loads images from our CDN.

---

## 5. Database schema (PostgreSQL)

```
Retailer            id, name, slug                              -- "SM Markets" (internal label only)
Branch              id, retailer_id, code, name, city, is_reference
Category            id, name, slug, parent_id, puzzle_weight
Product             id, retailer_id, source_product_id, barcode, brand, name,
                    size_value, size_unit, pack_count, category_id,
                    image_key, image_source_url, license_note,
                    is_puzzle_eligible (bool), difficulty (1-5, nullable),
                    tags (text[] e.g. {'noche-buena','pasalubong','baon'}),
                    created_at, updated_at
                    UNIQUE (retailer_id, source_product_id)
ScrapeRun           id, branch_id, source, started_at, finished_at, status,
                    products_seen, products_upserted, errors (jsonb)
RawPayload          id, scrape_run_id, url, fetched_at, payload (jsonb)
PriceSnapshot       id, product_id, branch_id, scrape_run_id (nullable),
                    price_centavos, sale_price_centavos (nullable),
                    observed_on (date), source ('smmarkets_online'|'manual_instore'|...)
                    INDEX (product_id, observed_on DESC)

DailyPuzzle         id, puzzle_number, play_date (date, Asia/Manila, UNIQUE),
                    product_id, answer_snapshot_id, answer_centavos (denormalized, regular price),
                    promo_price_centavos (nullable; theme/promo price, never the answer),
                    theme ('default'|'pasko'|'summer'|'balik-eskwela'|...),
                    status ('scheduled'|'live'|'archived')

Player              id (uuid), created_at, account_id (nullable)
Account             id, email or mobile (verified), display_name, consent_marketing (bool),
                    consent_promo_terms_version, created_at        -- only for prize/leaderboard
GameSession         id, player_id, puzzle_id, started_at, finished_at,
                    won (bool), guesses_used, UNIQUE (player_id, puzzle_id)
Guess               id, session_id, index (1-6), guess_centavos, result ('higher'|'lower'|'win'),
                    is_close (bool), created_at

Campaign            id, name, partner_name, starts_on, ends_on, rules_md,
                    permit_ref (e.g. DTI permit no.), selection ('top_n'|'skill_threshold'),
                    status
Prize               id, campaign_id, description, voucher_value_centavos, quantity
Winner              id, campaign_id, account_id, prize_id, rank, notified_at, claimed_at
```

Rules:
- `answer_centavos` is **never** sent to the client before the session is finished.
- Keep all `PriceSnapshot` history so we can later add a "Then vs now" inflation mode.

---

## 6. Game API (DRF)

```
GET  /api/puzzle/today            → { puzzle_number, play_date, product: {name, brand, size_text, image_url, category},
                                      theme, max_guesses: 6 }        (no price!)
POST /api/puzzle/today/guess      { player_id, guess_php: "89.75" }
                                  → { index, result: higher|lower|win, is_close, finished, answer_php? }
GET  /api/puzzle/{number}/result  → answer + aggregate stats (only after the player finished, or the day has passed)
GET  /api/stats/today             → distribution of guesses-to-win (for the share screen)
GET  /api/leaderboard?period=week|month|campaign
POST /api/account/request-otp     (phase 4)
POST /api/account/verify
```

Server-side game logic (`puzzles/rules.py`, pure functions, fully unit-tested):

```
win   = abs(guess - answer) <= 0.05 * answer
close = abs(guess - answer) <= 0.25 * answer
result = 'win' if win else ('higher' if guess < answer else 'lower')
```

- Validate the guess: ₱0.25–₱100,000, max 2 decimals.
- Rate limit with Redis: max 6 accepted guesses per player per puzzle, plus per-IP throttling.
- Day boundary: `Asia/Manila`. Allow a 10-minute grace window to finish yesterday's game.
- Leaderboard score (proposal): win = 100 − (guesses_used−1)×15, plus a closeness bonus. The streak multiplier is capped.

### Puzzle scheduler (`schedule_puzzles`)
- Pre-schedule ≥30 days ahead. Admins can override any day.
- Don't repeat a product within 365 days, or the same brand within 7 days.
- Rotate categories by `puzzle_weight`. Mix price bands (₱20s sachets → ₱1,000+ items).
- **Seasonal theming by PH calendar:** Pasko / Noche Buena (Sep–Dec, "ber" months), Valentine's,
  summer / outing (Mar–May), Balik-eskwela (Jun–Aug), Undas (Nov 1–2), Holy Week (no-meat items).
  Pick items tagged for the season and set `DailyPuzzle.theme`.

---

## 7. Frontend

> **v1 = functional only (see "Top priority" at the top).** Build the plain v1 scope at the end of this section first.
> Everything under "Concept" and "Philippine-specific touches" is **later**, after the proof of concept is approved.

### Concept (LATER): "Online cart meets checkout counter"
The screen combines two experiences that Filipino shoppers know:

**Top half: the online shopping view (online shoppers)**
- A product detail card in the style of a grocery app: big product photo, brand, name, size, category breadcrumb
  (`Pantry › Noodles`).
- A price field shown as `₱ ???.??` with a crossed-out "SRP?" tag.
- The guess input looks like the quantity/price box, and the submit button is styled **"Add to Cart → I-check out!"**.
- Previous guesses appear as small "cart items" with arrow badges.

**Bottom half: the cash register (in-store shoppers)**
- A **POS register display** (green or red seven-segment digits) shows the latest guess.
- A **thermal-paper receipt (resibo)** prints a line per guess, with a print animation:
  ```
  GUESS 1 ........ ₱ 45.00   ▲ TAAS PA
  GUESS 2 ........ ₱ 95.00   ▼ BABA  (MALAPIT NA!)
  GUESS 3 ........ ₱ 79.50   ✔ SAKTO!
  ```
- Receipt footer: puzzle number, date, "Salamat po! Balik po kayo bukas." (Thank you, come back tomorrow), and a fake
  barcode that encodes the share text. **Do not** copy any real store's receipt header or format.
- An on-screen **numeric keypad** with peso coin/bill quick-add buttons (₱1, ₱5, ₱10, ₱20, ₱50, ₱100…)
  for mobile players. This works like counting barya (loose change).

### Philippine-specific touches (LATER)
- **Taglish feedback copy** (`i18n/taglish.json`, with English fallback):
  higher → "Taas pa!" (go higher), lower → "Baba pa!" (go lower), close → "Malapit na!" (almost there),
  win → "Sakto!" / "Ang galing mo, suki!" (spot on / great job, regular customer), loss → "Sayang! Bawi bukas."
  (too bad, try again tomorrow).
- **Suki card:** the streak tracker is a loyalty-stamp card. Each day won is a stamp, and 7 stamps give a "Suki ng Linggo" badge.
- **Cashier voice:** "Next customer, please!" on page load. "May sukli po kayo" ("here's your change") shows the
  difference between the guess and the price after the game ends.
- **Seasonal themes:** Christmas parol (lantern) lights and Noche Buena ham/queso de bola items from September onward
  (the "ber" months), summer beach colors, a school-supplies theme in June.
- **Colors:** an original palette inspired by jeepney / sari-sari store signage and price-tag yellow + red.
  **Avoid SM's blue/white brand look.**
- **Share card:** emoji grid for Messenger, Viber and FB. Example:
  `🛒 Sukidle #42 3/6  🔼🟨 🔽🟩 ✅  ₱ sakto!`
- Price in `₱` with centavos. Format with `en-PH` locale.

### v1 frontend scope (build this first — plain, functional)
- One page: product image, name, size, a price input and a Submit button.
- A plain list of guesses, each showing higher / lower / close / win (text or simple arrows).
- End-of-game message with the answer, plus a copy-to-clipboard share text.
- Progress for the day saved in localStorage, so a refresh doesn't reset the game.
- A footer with the disclaimer.
- No keypad, receipt, themes, animations or custom styling yet. No login UI until Phase 4.

---

## 8. Privacy, legal and compliance checklist

- **Data Privacy Act (RA 10173):** anonymous play collects only a random UUID. Accounts (for prizes) need a
  privacy notice, explicit consent, the minimum data needed, and deletion on request. Register with the NPC if required.
- **Sales promotions:** in the Philippines, a promo with prizes generally needs a **DTI permit** (Consumer Act, RA 7394).
  Chance-based "lucky winner" draws are more regulated than skill-based "top N" prizes.
  **The preferred setup: the partner (e.g. SM) runs the promo under its own permit.** We supply the
  leaderboard data. Record the permit number in `Campaign.permit_ref`, and show the full mechanics on a campaign page.
- **Trademarks:** see the brand rules in §1. Have a PH IP lawyer review before any monetization or partner pitch.
- **Scraping:** follow robots.txt and the terms (§4.1). Keep a kill switch: `INGEST_ENABLED=false`.

---

## 9. Partnerships plan (instead of ads)

**Goal:** seasonal voucher campaigns (e.g. "Pasko Price Master": top weekly players win e-gift certificates)
co-run with SM Markets, or with FMCG brands whose products appear in the game.

**Steps**
1. **Grow the audience first** (no money involved): get ~3–6 months of daily players.
   Track DAU, retention (D1/D7/D30), shares per day, and top-viewed products in a simple `/admin/metrics` page.
2. **Build the pitch kit:** one-pager + metrics + mock-ups of a branded campaign page and a
   "Today's item brought to you by ___" slot.
3. **Who to approach:**
   - SM Markets marketing / SM Advantage–SM Markets loyalty team, for store vouchers and seasonal promos
     (Christmas, anniversary sale, back-to-school).
   - FMCG brands (noodles, canned goods, snacks, beverages), for sponsored "featured product" days plus product bundles as prizes.
     This avoids needing SM's approval and is often easier to close.
4. **Campaign mechanics (skill-based):** a top-N weekly or monthly leaderboard among verified accounts. Ties are broken
   by fewest guesses, then earliest finish. Players must opt in to the campaign terms.
5. **Fulfilment:** the partner issues e-vouchers. We provide the verified winner list via a CSV export from Django admin.
   Winners are announced in-app with consent.

**Build support for this in Phase 4:** `promos` app, campaign pages, opt-in flow, winner export, anti-abuse
(one account per verified mobile, device/IP checks, flagging guess timings that look like bots).

---

## 10. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| **0. Discovery** | `docs/discovery.md` (§4.0) | Owner approves the data approach |
| **1. Data foundation** | GitHub repo + `ci.yml` from day one, Django project, Postgres schema, source adapter, normalizer + pack-size parser with tests, CSV import, Django admin curation screens, image pipeline | One reference-branch snapshot loaded; ≥300 puzzle-eligible products curated |
| **2. Game backend** | Rules module, puzzle scheduler, game API, Redis throttling, server-side answer hiding | API tests pass; 30 days scheduled |
| **3. Frontend v1 (plain) + deploy** | Functional, unstyled game page (§7 "v1 frontend scope"); AWS infra (EC2, RDS, Route 53, S3) and `deploy.yml` (§12) | Proof-of-concept checklist at the top is fully ticked **and live on the domain via an automatic deploy**; owner approves |
| **3b. UI design** | Online-cart + register/receipt UI, Taglish copy, keypad, themes | Only after Phase 3 is approved |
| **4. Accounts & promos** | OTP accounts, leaderboard, campaigns, winner export, privacy notice | Ready to pitch partners |
| **5. Later** | "Unlimited" practice mode, then-vs-now inflation mode, more retailers, PWA install | — |

---

## 11. Conventions for Claude Code

- Python: ruff + black, type hints, pytest. Business rules live in pure functions with tests.
- Money is always integer centavos in the backend. Convert to `₱` strings only at the API edge.
- All dates for puzzles use `Asia/Manila`. Store timestamps in UTC.
- Never log or return `answer_centavos` from any endpoint that's reachable before a game finishes. Write a test for this.
- Secrets: never committed. Locally in `.env`; in production in GitHub Actions secrets and/or AWS SSM Parameter Store.
  `.env.example` lists the keys: `DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DATABASE_URL, REDIS_URL, APP_NAME,
  REFERENCE_BRANCH_CODE, INGEST_ENABLED, SCRAPE_CONTACT_EMAIL, AWS_REGION, S3_BUCKET, CDN_BASE_URL`.
- Work on feature branches and open PRs into `main`. `main` must always be deployable. Small PRs per phase step.
  Update this README when a decision changes.

---

## 12. Deployment (GitHub → GitHub Actions → AWS)

### Infrastructure (AWS, single region, e.g. `ap-southeast-1` Singapore for low latency to PH)
| Piece | Setup |
|---|---|
| **EC2** | One small instance (e.g. t3.small / t4g.small), Ubuntu LTS, Docker + Docker Compose. Elastic IP attached. Runs `docker-compose.prod.yml`: **nginx** (TLS, serves the React build, proxies `/api` and `/admin`) + **Django/gunicorn** (+ Redis later). |
| **RDS** | PostgreSQL 16, smallest instance class (e.g. db.t4g.micro), single-AZ for now, automated backups on (7 days). **Not publicly accessible.** Its security group only allows 5432 from the EC2 security group. |
| **Route 53** | Hosted zone for the game's domain. `A` records for the apex and `www` → EC2 Elastic IP. Optional `staging.` subdomain later. |
| **TLS** | Let's Encrypt via certbot on the EC2 host (auto-renew). |
| **S3** | One bucket for product images (public-read through a bucket policy on `images/*` only, or CloudFront later). Django uploads via an IAM role attached to the EC2 instance, so no access keys on the box. |
| **Security groups** | EC2: 80/443 open to the world; 22 restricted to the owner's IP, or closed entirely if using SSM Session Manager. RDS: 5432 from the EC2 SG only. |

Document every manual AWS step in `deploy/README-infra.md`. (Terraform/CDK is a later nice-to-have, not v1.)

### Environments (owner decision)
| Env | Branch | Deploys | Domain |
|---|---|---|---|
| **staging** | `main` | Automatically on every merge to `main` | `staging.<domain>` |
| **production** | `production` | Only when the owner manually merges `main` → `production` (PR) | apex + `www` |

To keep costs down, staging shares the EC2 instance (a separate Compose project, routed by nginx `server_name`)
and the RDS instance (a separate database `sukidle_staging` with its own DB user). Split them out later if load requires it.

### GitHub Actions
**`ci.yml`** runs on every pull request and on push to `main` / `production`:
1. Start a Postgres 16 service container.
2. Backend: install deps, `ruff`, `black --check`, `python manage.py migrate`, `pytest`.
3. Frontend: `npm ci`, typecheck, `npm run build`.

**`deploy.yml`** runs after CI passes: push to `main` → staging, push to `production` → production
(also runnable manually via `workflow_dispatch`):
1. Build the backend Docker image and the frontend static build.
2. Push the image to **GitHub Container Registry (ghcr.io)**.
3. Connect to EC2. Preferred: **AWS SSM `send-command`** using GitHub OIDC → an IAM role (no long-lived AWS keys, no open SSH port). Fallback: SSH with a deploy key stored in GitHub secrets.
4. On the host, `deploy/scripts/deploy.sh` does: pull the new image → `migrate` → `collectstatic` → `docker compose up -d` → health-check `GET /api/health`. If the health check fails, roll back to the previous image tag.
5. Use `staging` and `production` GitHub Environments, each with its own secrets.

**Scheduled jobs:** the daily puzzle rollover needs no job (the puzzle is looked up by Asia/Manila date). The
`schedule_puzzles` top-up and any data imports run as **cron on the EC2 host** (`docker compose exec web python manage.py …`).
Keep them out of GitHub Actions.

### Required GitHub secrets / variables
`AWS_ROLE_ARN` (OIDC), `AWS_REGION`, `EC2_INSTANCE_ID`, and the production env values (or the SSM Parameter Store
path that holds them). `GITHUB_TOKEN` handles ghcr.io pushes.

### Health & ops
- `GET /api/health` checks the DB connection and returns the app version (git SHA).
- Errors are logged to stdout → CloudWatch Logs via the CloudWatch agent (can reuse the owner's existing
  CloudWatch → GitHub Issues → Slack error-forwarding pattern later).
- RDS snapshots + automated backups cover data. The S3 bucket has versioning on.

---

## 13. Owner decisions & open questions
1. **Name: Sukidle** (decided). Domain still to be chosen.
2. **Reference branch:** prices come from the smmarkets.ph website. Phase 0 checks whether prices vary by selected
   store; a branch is pinned only if they do.
3. **Answer = always the regular price** (decided). Theme/promo prices are stored for partnership and sponsorship use.
4. **Registrar (open):** Route 53 is usually cheaper long-term for `.com` (flat renewal, no upsells); GoDaddy is
   needed for `.ph`. DNS is hosted in Route 53 either way.
5. **Staging now** (decided): `main` auto-deploys to staging; the owner manually merges `main` → `production`.
