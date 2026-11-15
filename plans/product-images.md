# Implementation Plan: The ThoughtTronix Store — Product Images

*Companion to `prd/product-images.md`. The PRD owns the requirements; this plan owns the sequence. Where a task says "per the PRD," the PRD's wording is authoritative — do not improvise alternatives. Read `docs/testing.md` before writing tests. The suite stays green at every phase boundary.*

---

## Phase 1 — Tracer Bullet: One Uploaded Image, Every Layer

**Goal:** An employee uploads an image on the back-office product form and sees it on the catalog card and detail page; every other product still shows its placeholder. No validation beyond Django's default and no processing yet — proof that the media plumbing works end to end.

**Tasks:**
1. `uv add pillow`.
2. Settings: `MEDIA_ROOT` and `MEDIA_URL` per the PRD; serve media in `config/urls.py` when `DEBUG` is on. Add `media/` to `.gitignore`.
3. `Product.image` (`ImageField`, `blank=True`, `upload_to="products/"`) and its migration. Update the stale "No media handling in the core" comment in `products/models.py`.
4. `Product.display_image_url` per the PRD's display rule.
5. Catalog card and detail page use `display_image_url` inside the square navy frame per the PRD's storefront-display decision (`aspect-square`, `object-cover` for images, `object-contain` for placeholders, `width`/`height`, `loading="lazy"` on cards).
6. `ProductForm` gains `image`; `StyledModelForm` styles file inputs as `file-input w-full`; the product form template gets `enctype="multipart/form-data"`.
7. `conftest.py`: a fixture that points `MEDIA_ROOT` at `tmp_path`, and a helper/fixture that builds an in-memory PNG upload with Pillow.

**Verification.** *Automated:* `display_image_url` returns the placeholder without an image and the media URL with one; a staff multipart POST stores an image; catalog and detail render the right URL in both cases. Full suite green, Ruff clean. *Manual:* as `employee`, upload `product-images/Seraphine GPT Text.png` to Seraphine; see it on the catalog and detail page; confirm other products still show placeholders.

**Out of bounds:** validation rules, resizing, file cleanup, back-office preview/thumbnails, seed changes.

---

## Phase 2 — Validation, Shared by Every Form

**Goal:** Unusable uploads are rejected with specific, readable messages in both the back office and the Django admin — never a server error.

**Tasks:**
1. **Validators first:** `products/validators.py` with the PRD's rules as plain functions (usable image fully decoded, format PNG/JPEG/WebP by content, ≤ 10 MB, shorter side ≥ 400 px, decompression-bomb guard), each with the PRD's message. Validators skip already-committed files. Unit tests for each before wiring anything.
2. Attach them as `validators=[...]` on `Product.image` and generate the migration (Django records field validators in migrations, so module-level functions are required).
3. Replace Django's generic "invalid image" message from `forms.ImageField` with the PRD's readable wording in **both** the back-office form and the Django admin. Set it wherever it actually reaches both forms, and prove it with a test for each.
4. Add `accept="image/png,image/jpeg,image/webp"` to the file input.

**Verification.** *Automated:* PRD coverage priority 1 in full; back-office invalid POST returns 200 with the field error and other input preserved; the same invalid file through the admin change form shows the same error. *Manual:* upload a renamed `.txt`, a tiny image, and a GIF in the back office and read each message.

**Out of bounds:** processing and file cleanup (Phase 3).

---

## Phase 3 — Processing and File Lifecycle

**Goal:** Every new upload becomes an 800×800 navy-padded WebP exactly once, and old files are cleaned up without ever leaving a broken reference.

**Tasks:**
1. Constants `IMAGE_SIZE` and `IMAGE_PADDING_COLOR` and a private processing helper in `products/models.py` per the PRD's processing steps (EXIF orientation, first frame, fit without cropping, pad `#141824`, WebP).
2. `Product.save()` processes only when `image` holds a new, uncommitted upload, and processes **before** `super().save()`. No reprocessing of committed images.
3. Old-file cleanup per the PRD: on replace and Clear, compare against the previously stored name and delete the old file via `transaction.on_commit`; on deletion, a `post_delete` receiver (registered in `ProductsConfig.ready()`) deletes the file via `transaction.on_commit`.
4. Docstrings on `save()` and the helper explaining the "new upload only" and "delete after commit" rules — this is the subtle part of the feature.

**Verification.** *Automated:* PRD coverage priorities 2 and 3 — output is 800×800 WebP; portrait, landscape, and transparent inputs are padded, not cropped (corner pixels are navy); a price-only edit leaves the file name unchanged; replace, Clear, and delete remove old files after commit; a save that fails mid-way leaves the previous image intact. Use `django_capture_on_commit_callbacks` (pytest-django) to run on-commit callbacks in tests. *Manual:* upload `MindSync Duo.png` (landscape) and a portrait image; confirm both are square with navy bars and around 50–100 KB in `media/products/`; replace one and confirm the old file is gone.

**Out of bounds:** back-office preview and list thumbnails (Phase 4), seed (Phase 5).

---

## Phase 4 — Back-Office Experience

**Goal:** Employees can see what is attached before they change it, and spot products that still need an image.

**Tasks:**
1. Product edit page: preview of `display_image_url` above the image field, with a note ("No image — showing the category placeholder") when none is set.
2. Back-office product list: a small square thumbnail column using `display_image_url`, per `templates/CLAUDE.md`'s table convention.
3. Confirm the Django admin's product form works end to end with the processing and validators (no admin code changes expected).

**Verification.** *Automated:* edit page shows the image URL or the placeholder note; list renders a thumbnail per row; PRD coverage priorities 5–7. *Manual:* as `employee`, scan the product list for placeholders; open one, upload, save, and confirm the preview and list update; use Clear and confirm the placeholder returns.

**Out of bounds:** separate remove endpoints, HTMX for images, cart/order thumbnails.

---

## Phase 5 — Seed Images and Finishing Pass

**Goal:** A freshly seeded store shows Marketing's images, and the repository is tidy.

**Tasks:**
1. Move and rename Marketing's 12 chosen files into `products/seed_images/<slug>.png` per the PRD's mapping table. Do not commit `SyncRest GPT Text.png`.
2. Seed: after creating each product, attach `seed_images/<slug>.png` if present (assign and save, so the model processes it). The seed's wipe deletes previous files via the `post_delete` receiver.
3. Remove the root-level `product-images/` folder and `product-images.zip`; add `product-images.zip` to `.gitignore`.
4. Docs: update `prd/core-platform.md`'s "Product images" note to point at `prd/product-images.md`; update `CLAUDE.md` (Pillow, `media/`, where image rules live); README if setup changes; append a `PROMPTS.md` entry.
5. Sweep: Ruff clean; full suite green.

**Verification.** *Automated:* seed runs twice without error with the same counts; exactly 12 products have images, each an 800×800 WebP; `media/products/` holds exactly 12 files after the second run (no accumulation). *Manual:* `seed`, `tailwind runserver`, browse every category — the 12 images and the remaining placeholders sit in identical square frames; DevTools Network shows catalog images in the tens of KB.

**Out of bounds:** nothing new. This phase adds no features — it finishes the ones that exist.

---
