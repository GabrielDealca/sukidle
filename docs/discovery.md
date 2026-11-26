# Phase 0: Discovery (smmarkets.ph)

**Date:** 2026-11-26
**Method:** curl with User-Agent `SukidleDiscovery/0.1 (research)`, about 1 request per second, **8 requests in total**
(robots.txt, homepage, sitemap index, 2 sitemap files, 3 read-only GraphQL GET queries). Nothing blocked us: no
login, CAPTCHA, block or rate limit.

Legend: **[Observed]** = seen in a response. **[Inferred]** = deduced from platform conventions or indirect evidence.

## TL;DR / Recommendation

- **The Terms & Conditions forbid reusing the site's content (including "data compilations") for any purpose
  without SM Markets' express, prior written consent.** The terms never say "scraping", but this clause covers
  showing their prices in a public game. Per README §4.0, **deep investigation stopped here**: no cross-store price
  checks, no category counts, and only 1 sample product.
- **Technically it would be easy:** plain Magento 2 GraphQL (`/graphql`, anonymous GET, clean JSON). httpx would be
  enough; no Playwright needed.
- **Recommended path:**
  1. **Now:** build the proof of concept on the **manual / CSV path (README §4.4)**, using in-store shelf-tag
     observations (`source=manual_instore`). Use our own product photos, never retailer images.
  2. **In parallel (optional):** email SM Markets (support@smsupermarket.com, the contact given in the terms) and
     ask for written permission. This also starts the partnership conversation in README §9.
  3. **Only if permission is granted:** build the httpx GraphQL adapter described below.

---

## 1. robots.txt and Terms of Use

### 1a. robots.txt [Observed], full text from https://smmarkets.ph/robots.txt

```
User-agent: *
Disallow: /catalog/
Disallow: /customer/
Disallow: /sendfriend/
Disallow: /review/
Disallow: /*SID=
Disallow: /checkout/
Disallow: /onestepcheckout/
Disallow: /customer/
Disallow: /customer/account/
Disallow: /customer/account/login/
Disallow: /catalogsearch/
Disallow: /catalog/product_compare/
Disallow: /catalog/category/view/
Disallow: /catalog/product/view/
Disallow: /*?dir*
Disallow: /*?dir=desc
Disallow: /*?dir=asc
Disallow: /*?limit=all
Disallow: /*?mode*
Disallow: /customer/account/login/referer/
Disallow: /customer/account/forgotpassword/
Disallow: /customer/account/create/
Disallow: /sm-hypermarket-homepage-2
Disallow: /?___store=*
Disallow: /store-locator?___store=*
Disallow: /sm-supermarket-homepage-2?___store=*
Disallow: /*___store=*
Disallow: /*?p=*
Disallow: /*&p=*
Disallow: /*search.html?query*

Sitemap: https://smmarkets.ph/media/sitemap.xml
```

What it allows and blocks [Inferred from the text]:
- **Allowed:** product pages (`/<slug>.html`), category pages and `/graphql`.
- **Blocked:** paginated listings (`?p=`), store switching by URL parameter (`___store=`), search and `?limit=all`.
- There is no `Crawl-delay` line.

### 1b. Terms & Conditions [Observed], https://smmarkets.ph/terms-conditions

- **How it was read:** the site is a single-page app, so the text was fetched through GraphQL `cmsPage`.
- **Operators named:** Supervalue, Inc., Sanford Marketing Corporation and Super Shopping Market, Inc.
- **Not read:** the app version at `/static-page-terms-conditions-app`.

The words "scrape", "crawl", "robot", "spider" and "data mining" do not appear. Relevant clauses, quoted exactly:

**Intellectual Property:**
> "All information and content available on the Platform, including but not limited to trademarks, logos, service
> marks, features, functions, text, graphics, logos, button icons, images, audio clips, data compilations and
> software, and the compilation and organization thereof (collectively, the "Content") are our property or the
> property of our parents, subsidiaries, affiliates, partners or licensors, and are protected by local and
> international laws, including laws governing copyrights and trademarks.
>
> Except as required under applicable law, neither the Content nor any portion of the Platform may be used,
> reproduced, duplicated, copied, sold, resold, accessed, modified, or otherwise exploited, in whole or in part, for
> any purpose without our express, prior written consent. Nothing contained on the Platform grants or should be
> construed as granting, by implication, estoppel, or otherwise, any license or right to use any trademarks, trade
> names, service marks or logos displayed on the Platform, without the written permission of SM Markets or such
> third party owner, as may be applicable."

**Use of the Platform:**
> "In using the Platform and the services therein, you agree to: 1. do so only for lawful purposes; …"

**Products, Pricing, Content and Specifications:**
> "The products and services featured on the Platform (collectively, the "Products") and their contents,
> specifications, and prices are subject to change at any time, without need of prior notice. The prices of the
> Products may be different from that in SM Markets physical stores."

**Accuracy of Information** (excerpt):
> "The prices and amount indicated serves only as a guide price and amount. Final prices and amount due will be
> reflected during payment and collection of items in the store."

**Right to Refuse Service:**
> "We reserve the right, at our sole discretion, to refuse service to anyone for any reason at any time."

**Contact given in the terms:** support@smsupermarket.com

**Assessment** [Inferred, not legal advice]:
- The clause names "data compilations" and bans using, reproducing or copying them "for any purpose" without written
  consent.
- Copying product names and prices into a public game is reproducing that Content. **Treat this as a ban on
  scraping for Sukidle's purpose.**
- Product images and brand logos also belong to third parties.

---

## 2. Platform and how data loads

### Platform [Observed]

The site is **Magento 2 running PWA Studio (Venia storefront)**. Evidence:
- `/venia-static/` assets and `runtime/vendors/client` JS bundles.
- `data-media-backend="https://smmarkets.ph/media/"` on the root element.
- An `x-magento-cache-id` response header.
- Hosted on Nexcess, behind a Fastly CDN with Singapore and Manila points of presence.

### How product data loads [Observed]

- **There is no product data in the HTML.** The page is client-rendered.
- **All data comes from Magento GraphQL** at `https://smmarkets.ph/graphql`. **GET** with `?query=` works without
  auth or cookies, and responses are CDN-cached.
- **Headers the server accepts (CORS):** `Content-Type, Authorization, X-Requested-With, Store, Currency,
  X-Magento-Cache-Id`.
- **Pagination:** `products(pageSize:, currentPage:)` with `page_info` and `total_count`. The UI uses
  `grid_per_page` = 12. The server's maximum `pageSize` was not tested.

Example query (observed working):
```graphql
{ products(filter:{url_key:{eq:"20386830-pantene-conditioner-3-minute-collagen-repair-300ml"}}, pageSize:1) {
    total_count page_info{page_size total_pages}
    items{ __typename id uid sku name url_key stock_status
      price_range{minimum_price{regular_price{value currency} final_price{value currency} discount{amount_off percent_off}}}
      special_price small_image{url} categories{uid name url_path} } } }
```

### Fields

**Confirmed present [Observed]:**

| Field | Example value / note |
|---|---|
| `id` | `6277` |
| `uid` | `"NjI3Nw=="` |
| `sku` | `"20386830"`. An internal article number, not an EAN. |
| `name` | Includes the size after a pipe: `"Pantene Conditioner 3 Minute Collagen Repair \| 300ml"` |
| `url_key` | |
| `stock_status` | |
| `price_range` | `regular_price`, `final_price`, `discount` |
| `special_price` | `"0.00"` when there is no sale |
| `small_image.url` | |
| `categories` | `name`, `url_path` |

**Not seen:**
- No separate brand field. The brand appears to be the first word or words of the name [Inferred].
- No barcode (EAN) field.
- No size or unit field. The size is only in the name and URL slug.

**Images:** the sample product returned the site's **placeholder** image.

**Sitemap [Observed]:** `https://smmarkets.ph/media/sitemap.xml` points to 2 files of about 10 MB each, with
**15,102 URLs** in total, about 14.3k of them product URLs.

---

## 3. Store / branch selection

**Mechanism:**
- `availableStores` returns **427 store views**. About 400 do not carry an "(INACTIVE)" prefix. [Observed]
- Codes look like `sm_supermarket_butuan`, `sm_hypermarket_clark` and `sm_savemore_imall_antipolo`. [Observed]
- The list also includes non-grocery stores: Ace Hardware, The SM Store, Miniso and Watts Japan. [Observed]
- Every store view is in one website (`base`). [Observed]
- The anonymous default store is `default`. [Observed]
- **The store is chosen with the `Store: <store_code>` HTTP header** on GraphQL requests. That header is in CORS
  and `Vary`. [Observed headers; the mechanism is Inferred]

**Do prices differ between stores? NOT VERIFIED.** The check was skipped because of the terms finding.

Indirect evidence [Inferred]:
- Each branch is its own store view, which is the usual setup when price or stock differs per branch.
- But everything sits in one Magento website, and stock Magento varies price per website only. So per-branch prices
  would need custom code. Both setups are possible.
- The terms say online prices "may be different from that in SM Markets physical stores".

---

## 4. Category tree (from the sitemap) [Observed]

- Fresh Produce, Fresh Meat & Seafood, Frozen Goods, Bakery, Chilled/Dairy Items
- Pantry, Snacks, Beverage, Babies & Kids, Home Care, Pet Care
- Ready to Cook, Ready to Heat/Eat, International Goods
- Health & Beauty, Health & Hygiene Essentials
- Home Appliances & Essentials, Food Service Center, Only in SM Markets
- DIY/Hardware, Stationery, Furniture, Miniso, Watts Japan
- Promos, Christmas Markets, Markets Recipe

**Product counts per category were not collected** because of the terms finding.

---

## 5. Sample products

Only 1 was fetched (for platform identification). The parsed fields are derived from the name [Inferred]:

```json
{
  "source_product_id": "6277",
  "sku": "20386830",
  "barcode": null,
  "brand": "Pantene",
  "name": "Pantene Conditioner 3 Minute Collagen Repair | 300ml",
  "size_text": "300ml",
  "size_value": 300,
  "size_unit": "ml",
  "pack_count": 1,
  "price_php": 345.00,
  "sale_price_php": null,
  "image_url": "(site placeholder image)",
  "category_path": ["Health & Beauty", "Hair"],
  "product_url": "https://smmarkets.ph/20386830-pantene-conditioner-3-minute-collagen-repair-300ml.html"
}
```

**Parsing notes from sitemap slugs [Observed]:**
- Sizes appear as `12ml-6pcs`, `1-38l` (1.38 L), `1000g-1500g` (variable-weight items), `b1t1` (buy 1 take 1)
  and `6-1pcs` (6+1 promo packs).
- Slug format changed over time: older slugs put the SKU first, newer ones put it last.

---

## 6. Client recommendation and request volume (only relevant if permission is granted)

- **Client:** httpx against `/graphql`. No Playwright needed.
- **One store:** about 14.3k products at `pageSize` 100 is about 145 requests, or about 2.5 minutes at 1 request
  per second. If `pageSize` is capped lower, it becomes about 300–720 requests.
- **Every store:** up to about 400 stores, so about 58k requests, or about 16 hours. In practice you would pick
  1–3 representative branches.

---

## Uncertainties / not verified

- **Legal reading:** the interpretation of the terms is not legal advice. The app version of the terms was not read.
- **Per-store prices: unknown.**
- **Store header:** the `Store`-header mechanism comes from Magento convention; it was not traced in the JS.
- **Server limits:** the maximum `pageSize` and any WAF or rate limits are unknown.
- **Missing attributes:** barcode, brand and size custom attributes are unknown; GraphQL introspection was not tried.
- **Category counts and image coverage:** not collected.
- **Default-store price:** the observed ₱345.00 is the price for store view `default`, which may not match any real
  branch.
