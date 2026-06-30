# Best-Selling Products Analysis

**Date:** 2026-06-30
**Source:** Sales export by category (Product title · Net sales · Quantity ordered).
Raw data in [`data/`](./data/). Note: although the source files were named
"top_20", each is the **full category list**, not just the top 20.

## Why this lives here

This is a cabinet-door image generator. Knowing which door/drawer styles
actually sell tells us which styles in the generator's catalog
(`backend/styles/catalog.py`) deserve the best prompt tuning and which RTF
SKUs matter most. See [Implications for the generator](#implications-for-the-generator).

---

## Category totals

| Category | Products | Net sales | Units | Avg $/unit | Top‑3 share |
|----------|---------:|----------:|------:|-----------:|------------:|
| Wood Cabinet Doors | 79 | $765,351 | 10,574 | $72 | 48% |
| Wood Drawer Fronts | 64 | $131,173 | 3,435 | $38 | 51% |
| Thermofoil Cabinet Doors | 27 | $143,322 | 1,678 | $85 | 68% |
| Thermofoil Drawer Fronts | 21 | $27,314 | 669 | $41 | 50% |
| **Total** | — | **$1,067,160** | **16,356** | — | — |

**Shape of the business:**
- **Wood dominates** — $896K (84%) of revenue vs $171K (16%) thermofoil.
- **Doors >> drawer fronts** — roughly a 5–6× revenue ratio in both materials.
  Drawer fronts are an attach/accessory line, not a primary driver.
- **Thermofoil is highly concentrated** — its top 3 doors are 68% of the
  category; a single SKU (AR756) is ~43% of all thermofoil door revenue.
- **Cabinet doors carry a higher unit price** than drawer fronts ($72–85 vs
  $38–41), as expected from their larger surface area.

---

## Wood Cabinet Doors — top 10 (of 79)

| # | Product | Net sales | Units |
|--:|---------|----------:|------:|
| 1 | Shaker | $234,515 | 3,997 |
| 2 | Revere | $92,628 | 1,310 |
| 3 | Alpine | $38,402 | 546 |
| 4 | Adobe | $30,267 | 602 |
| 5 | 3/4" Heritage | $29,997 | 396 |
| 6 | Custom | $29,762 | 275 |
| 7 | Liberty | $27,322 | 354 |
| 8 | Arcadia | $26,010 | 273 |
| 9 | True Louver | $20,510 | 73 |
| 10 | Aries | $16,424 | 144 |

**Shaker is the franchise:** 31% of category revenue and 38% of category units
on its own. Shaker + Revere + Alpine ≈ half of all wood-door sales.

---

## Wood Drawer Fronts — top 10 (of 64)

| # | Product | Net sales | Units |
|--:|---------|----------:|------:|
| 1 | Shaker | $47,105 | 1,521 |
| 2 | Revere | $10,622 | 257 |
| 3 | Alpine | $9,531 | 250 |
| 4 | Harmony | $5,521 | 93 |
| 5 | Tacoma (Plank Style) | $5,122 | 135 |
| 6 | Heritage | $4,420 | 120 |
| 7 | Custom | $4,382 | 67 |
| 8 | Mission | $3,501 | 86 |
| 9 | Adobe | $3,475 | 103 |
| 10 | Journey | $3,040 | 57 |

The drawer-front top 3 mirrors the door top 3 (Shaker / Revere / Alpine) —
customers match drawer fronts to their door style, so door demand drives
drawer demand.

---

## Thermofoil Cabinet Doors — top 10 (of 27)

Thermofoil products are sold by SKU; the parenthetical is the equivalent style.

| # | SKU | Style | Net sales | Units |
|--:|-----|-------|----------:|------:|
| 1 | AR756 | — (unlabeled) | $61,560 | 841 |
| 2 | DRS131 | Shaker | $21,644 | 194 |
| 3 | FS842 | — | $14,112 | 155 |
| 4 | DSS218 | Shallow Shaker | $7,723 | 76 |
| 5 | DR1 | Artesia | $6,364 | 53 |
| 6 | Thermofoil Plank (DBQ) | Tacoma / Plank | $5,581 | 57 |
| 7 | JR7 | Revere | $4,415 | 40 |
| 8 | DR133 | Victoria | $4,286 | 37 |
| 9 | DR8 | — | $3,261 | 40 |
| 10 | AR766 | — | $2,458 | 21 |

**AR756 is the thermofoil hero SKU** — bigger than the next three combined.
Identifying its profile (it carries no style label here) is worth doing, since
it anchors the whole category.

---

## Thermofoil Drawer Fronts — top 10 (of 21)

| # | SKU | Style | Net sales | Units |
|--:|-----|-------|----------:|------:|
| 1 | AR756 | — | $7,113 | 182 |
| 2 | DRS131 | Shaker | $3,478 | 81 |
| 3 | FS842 | — | $3,059 | 69 |
| 4 | Thermofoil Plank (DBQ) | Plank | $2,839 | 86 |
| 5 | DR8 | — | $2,066 | 40 |
| 6 | KB732 | — | $1,963 | 67 |
| 7 | DR1 | Artesia | $944 | 21 |
| 8 | DSS218 | Shallow Shaker | $914 | 18 |
| 9 | DR133 | — | $831 | 12 |
| 10 | FC712 | — | $778 | 19 |

Same hierarchy as thermofoil doors (AR756 → DRS131 → FS842), reinforcing that
the SKU ranking is consistent across both forms.

---

## Cross-cutting patterns

1. **A handful of styles carry the catalog.** In every category the top 3
   products are ~48–68% of revenue, while the long tail (dozens of styles)
   each contributes <1%. This is a classic head-heavy distribution.
2. **Shaker is the universal #1** across wood doors, wood drawers, and (as
   DRS131) thermofoil — the single most important geometry to render well.
3. **Style demand transfers across material and form.** The same names
   (Shaker, Revere, Alpine, Adobe, Artesia, Tacoma/Plank, Liberty, Mission,
   Victoria) recur as both wood items and thermofoil SKUs, doors and drawers.
4. **Premium low-volume specialties exist.** True Louver (~$281/unit), Sawyer
   (~$329/unit), Talbot, and Cabrillo sell in small quantities at high price —
   a different segment from the volume drivers.
5. **Zero/near-zero rows** (e.g. Hayes, Solana, Jasper drawer) indicate
   discontinued or sample-only items still in the export.

---

## Implications for the generator

The generator's `backend/styles/catalog.py` should bias quality toward what
sells. Mapping the best-sellers to catalog geometry:

Checked against the actual style keys in `catalog.py`:

| Best-seller | Geometry | Catalog coverage today |
|-------------|----------|------------------------|
| Shaker (wood + DRS131) | flat recessed panel | `shaker`, `recessed_panel`, `rtf_drawer_shaker` ✓ |
| Shallow Shaker (DSS218) | shallow recessed panel | `rtf_drawer_shaker_shallow` ✓ |
| Skinny Shaker (DN917) | narrow-rail recessed | `rtf_drawer_shaker_skinny`, `mitered_flat_panel` ✓ |
| Tacoma / Plank | vertical plank slab | `solid_plank` / `drawer_solid_plank` ✓ |
| Mission | square-frame | `mission` ✓ |
| True Louver | louvered | `louver` ✓ |
| Alpine / Harmony / Journey / Durango | named profiles | drawer keys exist (`drawer_alpine`, `drawer_harmony`, `drawer_journey`, `drawer_durango`) ✓; **no dedicated door key** |
| Graham / Vienna / Terracina / Davenport | named profiles | door keys exist ✓ |
| **Revere, Adobe, Liberty, Arcadia, Aries, Heritage, Artesia, Victoria** | named profiles | **no dedicated catalog key** — rendered via generic geometry + style notes |
| AR756, FS842, DR8, KB732 | unlabeled top thermofoil SKUs | **profiles not identified** |

**Recommended priorities (highest sales-impact first):**
1. **Nail Shaker fidelity** — it's #1 everywhere; the recessed-panel / `shaker`
   prompts are the single highest-leverage prompts in the catalog.
2. **Add/confirm the high-revenue named styles that lack a dedicated key** —
   most notably **Revere** (#2 wood door, $92K) and **Adobe**, **Liberty**,
   **Arcadia**, **Aries**, **Heritage**, **Artesia**. These are proven top-10
   sellers but currently rely on generic geometry rather than a tuned profile.
3. **Identify AR756 and the other unlabeled thermofoil SKUs** (FS842, DR8,
   KB732) — AR756 alone is ~43% of thermofoil door revenue but has no style
   mapping in this data.
4. **Deprioritize the long tail** for prompt-tuning effort; the bottom ~50
   wood styles together are a small fraction of revenue.

> Catalog coverage above reflects style *keys* present in `catalog.py`, not a
> judgment of each prompt's rendering quality — that still needs visual review
> per style.

> Caveat: this is net sales + units only — no margin, date range, or
> region. Treat it as a demand-ranking signal, not a profitability ranking.
> The high-AOV specialties (True Louver, Sawyer) may matter more to margin
> than their revenue rank suggests.
