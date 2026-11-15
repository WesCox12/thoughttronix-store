# PRD: The ThoughtTronix Store — Product Images

*Commissioned by ThoughtTronix Marketing. "Your Thoughts, Our Business."*

---

## Problem Statement

The core platform shipped with a promise: "no media handling in the core platform (this arrives later)." It is later. Every product in the catalog is still represented by a category placeholder — a tasteful navy panel with an emoji on it — and Marketing has noticed that customers do not develop strong feelings about a navy panel.

Marketing has delivered 13 product images (PNG, 1.7–2.5 MB each, mostly portrait). Employees have no way to attach them: the `Product` model carries no image field, the back-office product form has no upload, and the project has no media settings. Even if they could be attached, serving 2 MB originals into a catalog grid would make the catalog page download tens of megabytes to draw cards roughly 400 pixels wide.

We need employees to upload, replace, and remove one image per product through the existing back office; every product to show its image when it has one and its category placeholder when it does not; bad uploads to be turned away with a message a person can act on; and the catalog to stay fast and visually consistent.

## Solution

One optional image per product, stored as a field on `Product`. Every upload — from the back office, the Django admin, or the seed command — is validated, then processed exactly once: fitted without cropping onto an 800×800 canvas padded in the storefront's navy (`#141824`), and saved as WebP. The original upload is not kept. The result is a uniform square of roughly 50–100 KB, regardless of what was uploaded.

Templates never decide between image and placeholder themselves; a model property returns the right URL. The catalog card, the product detail page, and the back office (list thumbnail and edit-page preview) display it.

The seed command attaches Marketing's images to the demo world, so a freshly seeded store shows the feature working.

## User Stories

**Visitor / customer**

1. As a visitor, I see each product's image on its catalog card and detail page when it has one.
2. As a visitor, I see the product's category placeholder when it has no image, in the same square frame, so the catalog grid stays even.
3. As a visitor, catalog pages load quickly: images are small, sized in advance so the page does not jump, and loaded lazily as I scroll.

**Employee (staff)**

4. As an employee, I can upload an image while creating or editing a product, on the existing back-office product form.
5. As an employee, I can see the product's current image (or a note that the placeholder is in use) on the edit page before I change anything.
6. As an employee, I can replace a product's image by uploading a new file.
7. As an employee, I can remove a product's image with the form's Clear checkbox; the product falls back to its placeholder.
8. As an employee, I can see a thumbnail column in the back-office product list, so products still on a placeholder are easy to spot.
9. As an employee, when I upload something unusable, the form re-displays with a specific, readable error beside the image field and the rest of my input preserved. I never see a server error.
10. As an employee, editing a product's other fields (price, name, tags) never alters or reprocesses its image.

**Admin**

11. As an admin, uploads through the Django admin are validated with the same rules and messages and processed the same way.

**Any developer**

12. As a developer, running `manage.py seed` produces a demo world in which 12 products carry Marketing's images and the rest show placeholders, still in under a minute.

## Implementation Decisions

**Data model.** One optional `ImageField` on `Product` (`image`, `blank=True`, `upload_to="products/"`). No separate image model and no gallery. Adds the **Pillow** dependency. A migration adds the column; existing products get no image and keep their placeholder.

**Media settings.** `MEDIA_ROOT = BASE_DIR / "media"`, `MEDIA_URL = "/media/"`. Media is served by Django only when `DEBUG` is on (`static()` helper in `config/urls.py`). `media/` is gitignored. Production media serving is out of scope.

**Display rule lives on the model.** `Product.display_image_url` returns `image.url` when an image is set, otherwise the static URL of `category.placeholder_image`. Templates use only this property. The catalog, detail, and back-office list querysets already `select_related("category")`, so the fallback adds no queries.

**Validation: model-field validators, shared by every form.** The rules are `validators=[...]` on `Product.image`, defined as plain functions in `products/validators.py` (the same pattern as `orders/validators.py`). Because they live on the model field, every `ModelForm` — the back-office `ProductForm` and the Django admin's form — runs them during `full_clean()`, with the same messages. The rules:

| Rule | Message (wording may be polished, meaning may not change) |
|---|---|
| Must be an image Pillow can fully decode (not just a valid header) | "This file isn't a usable image. Upload a PNG, JPEG, or WebP file." |
| Detected format (from content, not extension) is PNG, JPEG, or WebP | "This is a GIF image. Product images must be PNG, JPEG, or WebP." |
| File size at most 10 MB | "This file is 14.2 MB. Product images must be 10 MB or smaller." |
| Shorter side at least 400 px | "This image is 300×200 pixels. Product images must be at least 400 pixels on each side." |
| Not a decompression bomb (Pillow's pixel-count guard, warning or error) | "This image's dimensions are too large to process." |

The first message also replaces Django's generic "invalid image" wording (raised by `forms.ImageField` before model validators run), and it must appear in **both** the back-office form and the Django admin. The decompression-bomb rule relies on Pillow's own protection at its default `Image.MAX_IMAGE_PIXELS`; both `DecompressionBombWarning` and `DecompressionBombError` count as rejections. The 10 MB limit is checked after Django has received the upload; Django has no per-file upload cap, and that is accepted for this project.

Validators **fully decode** the image (`Image.open(...).load()`), not only `verify()`, so a truncated file is rejected at validation time rather than failing later inside `save()`. Validators **skip an already-stored file** (one that is committed to storage), so editing unrelated fields does not re-open the stored image. The form's file input carries `accept="image/png,image/jpeg,image/webp"` as a convenience; it is not a substitute for the validators.

**Processing: once, in `Product.save()`, only for new uploads.** When `image` holds a new, uncommitted upload, `save()` processes it *before* calling `super().save()`:

1. Open with Pillow; apply EXIF orientation (`ImageOps.exif_transpose`); take the first frame of animated files; convert to RGBA.
2. Scale down to fit within 800×800 preserving aspect ratio (never crop; small images are not upscaled beyond 800).
3. Composite onto an 800×800 canvas filled with `#141824`, centered. Transparent areas become navy.
4. Save as WebP at quality 82 under the name `<slug>.webp`; storage adds a suffix on collision, so a replaced image gets a new URL and is never served stale from cache. The stored file name is not changed if the product's slug later changes.

The pad color and canvas size are module constants in `products/models.py` (e.g. `IMAGE_SIZE`, `IMAGE_PADDING_COLOR`). The processing helper is a small private function in `products/models.py` — **not** a new module: the project's "exactly two deep modules" rule is unchanged. Already-committed images are never reprocessed; saving a product without a new upload does no image work.

**File lifecycle: delete old files only after the database commits.** Django does not delete replaced files. On replace, on Clear, and on product deletion, the previous file is deleted via `transaction.on_commit`, so a failed save can never leave a product pointing at a deleted file. Order of operations guarantees no broken references: processing happens before any write; storage writes the file before the database row, so the worst failure is an unreferenced file in `media/`, never a missing one. Deletion cleanup uses a `post_delete` receiver (which also fires for queryset deletes, such as the seed's wipe), registered in the `products` app config.

**Back-office UI.** `ProductForm` adds `image` to its fields. `StyledModelForm` gains a branch styling file inputs with DaisyUI's `file-input w-full` (today every unknown widget gets `input w-full`). The product form template gets `enctype="multipart/form-data"` and, above the field, a preview of `display_image_url` with a note when the placeholder is in use. The default `ClearableFileInput` provides replace and Clear — no new views, URLs, or HTMX endpoints. The back-office product list gets a small square thumbnail column.

**Storefront display.** Catalog card and detail page render the image in an `aspect-square` frame with a `#141824` background: `<img src="{{ product.display_image_url }}" alt="{{ product.name }}" width="800" height="800" loading="lazy" class="object-cover">` (detail page may omit `loading="lazy"`, being above the fold). Uploaded images are already exactly square, so `object-cover` is a safety net for files that bypassed processing. The 4:3 placeholder SVGs use `object-contain` on the same navy, so each placeholder is shown complete, never cropped, and placeholder and photo frames match. Cart, checkout, and order pages stay text-only.

**Seed images.** Marketing's files are committed as `products/seed_images/<slug>.png` — the file name *is* the mapping; no mapping table. The seed, after creating each product, attaches `seed_images/<slug>.png` if it exists by assigning it to `product.image` and saving, which runs the same model processing as any upload. (The seed saves models directly, not through a form, so validators do not run there; the committed files are known-good and the seed's tests verify the stored results.) The mapping:

| Marketing file | Committed as |
|---|---|
| Calm Collar GPT Man.png | `calm-collar.png` |
| CrowdCalm Array No Text.png | `crowdcalm-array.png` |
| DreamWeaver Matrix GPT 3.png | `dreamweaver.png` |
| Hush GPT No Text.png | `hush.png` |
| MindSync Duo.png | `mindsync-duo.png` |
| MindSync GPT 2.png | `mindsync.png` |
| MoodSet GPT No Text.png | `moodset.png` |
| RecallPro.png | `recallpro.png` |
| Seraphine GPT Text.png | `seraphine.png` |
| SoulSear No Text.png | `soulsear-mark-ii.png` |
| SyncRest GPT No Text.png | `syncrest.png` |
| Veil GPT Text.png | `veil.png` |
| SyncRest GPT Text.png | *not committed* (the No Text version is used) |

The root-level `product-images/` folder and `product-images.zip` are removed from the working tree once the files are moved, and `product-images.zip` is gitignored.

**Out of scope.** Multiple images or galleries; keeping originals or multiple renditions; thumbnail libraries; images in cart, checkout, or order pages; production media hosting; a reprocessing command; per-image alt text (alt is the product name).

## Testing Decisions

pytest + pytest-django, per `docs/testing.md`. A shared fixture in `conftest.py` points `MEDIA_ROOT` at pytest's `tmp_path` for any test that touches images, so the real `media/` folder is never written. Test images are generated in memory with Pillow — no binary fixtures checked in. Tests never invoke the seed command, except the seed's own tests in `products/tests.py`, which also use the temporary media fixture.

Coverage priorities, in order:

1. **`products/validators.py`** — each rule rejects with its own message: a renamed text file, a truncated PNG, a GIF, an oversized file, a 300×200 image, a decompression bomb (lower `Image.MAX_IMAGE_PIXELS` in the test); valid PNG, JPEG, and WebP pass; an already-committed file is skipped.
2. **Processing in `Product.save()`** — a new upload is stored as an 800×800 WebP; portrait, landscape, and transparent inputs are padded with `#141824` and not cropped (check corner pixel colors); saving a product with only a price change does not rewrite the file (name unchanged).
3. **File lifecycle** — replacing deletes the old file after commit; Clear deletes the file and the product falls back to its placeholder; deleting a product deletes its file; a failed save leaves the previous image intact.
4. **`display_image_url`** — returns the media URL when set, the category placeholder otherwise.
5. **Back-office views** — staff can upload, replace, and clear through `ProductForm` (multipart POSTs); an invalid upload re-renders the form with the field error and status 200, never 500; non-staff still get 302/403.
6. **Admin** — an invalid upload through the admin add/change form shows the same field error.
7. **Templates** — catalog and detail render the image URL when set and the placeholder otherwise; the back-office list renders a thumbnail.
8. **The seed command** — still idempotent; after seeding, exactly the 12 mapped products have images and each stored file is an 800×800 WebP.
