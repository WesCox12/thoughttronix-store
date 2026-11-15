# PROMPTS.md — AI Usage Log

This file is the record of AI use on this codebase. At the end of every
agent session, direct the agent to write the session log with this prompt:

> Append a session log to PROMPTS.md at the repo root, under today's date,
> newest entry at the top. Record every prompt I gave you this session, in
> order, including any corrections. End the entry with a short summary:
> the outcome, any places where I deviated from a recommended answer or
> asked follow-up questions, and anything that went sideways.

Two rules:

- Entries are added only by that prompt, never unprompted.
- New entries go at the top. Never rewrite or delete an old entry — the
  log is part of your work, and an honest log of a session that went
  sideways is worth more than a tidy one.

Each entry has this shape:

    ## YYYY-MM-DD — <one-line summary>

    ### Prompts
    1. ...

    ### Summary
    - **Outcome:** what was built and what was kept
    - **Deviations:** recommendations overridden, follow-up questions asked
    - **Sideways:** failures, wrong turns, and how they were caught

## 2026-11-15 — Plan product images with a `/grill-me` design interview (no implementation)

### Prompts
1. /grill-me I want to add product images to the ThoughtTronix Store. Marketing provided 13 PNG images in the product-images/ directory at the repository root. Employees need to upload and manage product images through the existing back office. Every product must display its uploaded image when available, or the existing placeholder otherwise. Invalid or unusable image uploads must be rejected with a clear, readable error message. Catalog pages should remain fast, and product images should look consistent. Interview me about the design decisions we need to make before implementation.
2. A. One image per product, using an optional ImageField on the existing Product model. I want to keep the implementation simple and use the existing back-office form. Products without uploaded images should continue displaying their category placeholders.
3. D. Process images once on upload and use CSS object-cover as a safety net.
4. D. Don't crop the product images. Preserve their original aspect ratios and fit them inside a consistent 800x800 canvas with neutral padding. Save the optimized result as WebP.
5. B, using #141824 to match the existing placeholders and dark storefront. Yes I want comparison previews
6. B
7. If we choose B, ensure that: Existing images aren't reprocessed when unrelated product fields change. Invalid uploads produce readable validation errors rather than server errors. Processing failures don't leave partially saved products or broken image references. The implementation doesn't introduce unnecessary complexity or violate our CLAUDE.md architecture rules. Tell me whether B is still the best choice after inspecting those details. Do not implement anything yet.
8. A. Put the shared image validation rules on the Product model's ImageField so both the back-office form and Django admin enforce them.
9. B+D
10. D. Include the marketing images in the seed data.
11. A. Assign the SoulSear image to SoulSear Mark II.
12. A. Use "SyncRest GPT No Text.png" for the SyncRest product.
13. A. Display product images on catalog cards, product detail pages, and in the back office (list thumbnails and edit previews).
14. Yes. Write prd/product-images.md and plans/product-images.md using the same conventions as the existing project documentation. Also create HANDOFF.md It should summarize our agreed decisions, implementation phases, important files, testing requirements, and any unresolved questions. Do not implement the feature yet. Do not delete the original ZIP or modify .gitignore yet. We can handle those changes during implementation after reviewing the plan. Once the documents are complete, report which files were created or modified so I can review them before starting a fresh Claude Code session.
15. I approve the PRD, implementation plan, and HANDOFF.md. Resolve the remaining questions using these decisions: Provide readable invalid-image errors in both the back office and Django admin. Use Pillow's decompression-bomb protection. Display complete placeholders without cropping. Use WebP quality 82. Keep the 10 MB upload limit. Keep existing image filenames when product slugs change. Apply EXIF orientation correction. Use the first frame of animated images. Update the documents only where needed. Then add an entry to PROMPTS.md documenting this /grill-me planning session, following the existing format. Do not implement the feature yet. Do not modify application code, the ZIP, or .gitignore. Do not commit yet. Report the final git status.

### Summary
- **Outcome:** A 12-question design interview for product images,
  answered one question at a time, each with options and a
  recommendation. Agreed: one optional `ImageField` on `Product`;
  uploads validated by model-field validators (PNG/JPEG/WebP, at most
  10 MB, at least 400 px, decompression-bomb guard), so the back office
  and the admin share them; each new upload processed once in
  `Product.save()` into an 800×800 WebP padded with `#141824`, no
  cropping; old files deleted after commit. The back office gets an edit
  preview and list thumbnails, and 12 Marketing images go into the seed
  under slug file names. Wrote `prd/product-images.md`,
  `plans/product-images.md` (five phases), and `HANDOFF.md`. After the
  user's review, the documents were updated with the user's answers to
  the six open questions. No application code, settings, `.gitignore`,
  or the ZIP were changed; nothing was committed.
- **Deviations:** The user took the recommended option on 10 of 12
  questions. Two exceptions:
  - Image shape: the user chose no-crop padding onto an 800×800 canvas
    over the recommended 1:1 center crop.
  - Where processing lives: the user asked whether `Product.save()`
    (option B) could meet four conditions, instead of the recommended
    `Product.set_image()` method. Inspection found `Product` is
    registered in the Django admin, so Claude agreed that B was better.
    That also changed an earlier answer: the validation rules moved
    from `ProductForm.clean_image` onto the model field (prompt 8).

  Follow-ups: the user asked for padding-color comparison previews
  (prompt 5) and, at the end, gave final decisions on the six open
  questions (prompt 15).
- **Sideways:**
  - Pillow isn't a project dependency yet. The comparison previews were
    rendered with a throwaway `uv run --no-project --with pillow` script
    in the session scratchpad, so `pyproject.toml` and `uv.lock` were
    left untouched. The contact sheet confirmed navy padding blends into
    the dark marketing images, while white looks out of place.
  - Several Marketing file names didn't map cleanly to products: two
    SyncRest versions, three possible SoulSear products, and "MindSync
    GPT 2". They were resolved as their own questions instead of being
    guessed.
  - The first PRD draft said the seed ran "validation-free" processing,
    which was unclear. It was reworded during drafting to explain that
    the seed saves models directly, so the validators don't run there.
  - The first attempt to insert this entry failed because it was
    anchored on the wrong text. Nothing was written; it was retried
    anchored on the previous entry's heading.

## 2026-11-08 — Add `Product.is_featured`, a back-office toggle, and a storefront "Featured" badge

### Prompts
1. add an is_featured field to products. It is a boolean and defaults to not-featured, so existing products stay unfeatured.
2. apply the migration
3. verify in the browser
4. load it again
5. it says forbidden
6. it still says 403 forbidden
7. I don't see any featured options on the site
8. I should be able to edit a product and have a featured checkbox
9. Now add a featured badge. A featured product shows a "Featured" badge in two places: the catalog listing and the product detail page. Both places must show it.
10. Append a session log to PROMPTS.md at the repo root, under today's date, newest entry at the top. Record every prompt I gave you this session, in order, including any corrections. End the entry with a short summary: the outcome, any places where I deviated from a recommended answer or asked follow-up questions, and anything that went sideways.

### Summary
- **Outcome:** Added `is_featured = BooleanField(default=False)` to
  `Product` with migration `products/0003_product_is_featured` (applied
  locally; every existing product is unfeatured). Added `is_featured` to
  the back-office `ProductForm`; it renders as a DaisyUI toggle beside
  "Is available", like every other checkbox in the back office. Added a
  solid `badge-accent` "Featured" badge to the catalog cards and the
  product detail page. New tests: one covers saving the flag through the
  back-office edit form, and two check the badge on both pages, shown
  when featured and hidden when not. Suite: 167 passed; ruff clean.
- **Deviations:** After prompt 7, Claude offered three places to surface
  the field (back-office form, back-office list badge, storefront) and
  recommended the first two. The user asked for only the back-office
  form checkbox (prompt 8). Later the user put the badge on the
  storefront catalog and detail pages (prompt 9), not on the back-office
  list. Prompts 4–7 were follow-ups after the browser check didn't show
  what the user expected.
- **Sideways:**
  - Claude in Chrome wasn't connected, and no headless browser was
    installed. "Verify in the browser" (and "load it again") was done
    instead with `curl` against the live dev server, logged in to the
    Django admin. Claude reported that it wasn't a real browser check.
  - The first round only added the model field. It appeared in the
    Django admin and nowhere else on the site, which led to prompt 7.
    Claude had mentioned this in its first reply, but the user expected
    to see the field on the site.
  - The user got 403s on the Django admin change page. The server log
    showed the browser was logged in as `employee`, a staff user with no
    model permissions (the project uses no Groups). Claude then told the
    user to visit `/admin/logout/`, which was wrong: Django 5+ logs out
    only via POST, so the GET returned 405 and the 403 persisted
    (prompt 6). Fixed by pointing to the admin's Log out button or a
    private window.
  - The dev server had been started with `--noreload`, so it had to be
    restarted to pick up the form change.
  - Claude's attempt to log in as `employee` with `curl` failed. The
    password extraction from `seed.py` was guessed wrong. Verification
    was redone as `admin`.
  - The compiled Tailwind CSS didn't include `badge-accent`, because the
    server ran without the Tailwind watcher. Caught by grepping the
    stylesheet, and fixed with `tailwind build --force`.
  - To check the badge live, Claude briefly set Calm Collar (pk 18) to
    featured in the local database, then set it back.
