# Handoff — Product Images

**Next session:** implement the product-images feature, phase by phase, starting at Phase 1. Nothing has been implemented yet; this session was design only.

The requirements live in **`prd/product-images.md`** and the sequence in **`plans/product-images.md`**. Those two files are authoritative. This handoff summarizes them and records context that isn't in them.

## Status

- Design interview complete (12 decisions, below). The user has **approved** the PRD, plan, and this handoff, and resolved every open question (see "Resolved questions").
- No code, settings, migrations, dependencies, or `.gitignore` changed.
- `product-images/` (13 PNGs) and `product-images.zip` are still untracked at the repo root. **The user asked that the zip is not deleted and `.gitignore` is not modified until implementation** (plan Phase 1 adds `media/` to `.gitignore`; Phase 5 moves the images, deletes the zip and folder, and gitignores the zip).

## Agreed decisions (details in the PRD)

1. **One optional `ImageField` on `Product`**; the category placeholder is the fallback. No gallery or separate image model.
2. **Process once on upload**; CSS `object-cover` as a safety net.
3. **No cropping:** fit inside an **800×800** canvas, saved as **WebP**; the original isn't kept.
4. **Padding color `#141824`**, matching the placeholder SVGs and the `night` theme.
5. **Validation:** PNG/JPEG/WebP by content, at most **10 MB**, shorter side at least **400 px**, decompression-bomb guard, full decode (not just `verify()`), and a specific readable message per rule.
6. **Processing in `Product.save()`**, only for new (uncommitted) uploads, done *before* `super().save()`. Old files are deleted via `transaction.on_commit` on replace, Clear, and delete (a `post_delete` receiver for delete).
7. **Validators on the model field** (`products/validators.py`), so the back-office form *and* the Django admin enforce them. `Product` is registered in the admin, which is why B was chosen over a `set_image()` method.
8. **Back office:** edit-page preview plus a styled `ClearableFileInput`; a thumbnail column in the product list. No new views, URLs, or HTMX.
9. **Seed:** images committed as `products/seed_images/<slug>.png`; the seed attaches them through the model.
10. SoulSear image → **`soulsear-mark-ii`**.
11. SyncRest → the **"No Text"** version; `SyncRest GPT Text.png` is not committed.
12. Images appear on **catalog cards, the detail page, and the back office only**. Cart, checkout, and order pages stay text-only.

Architecture check: no new deep module. The processing helper is private in `products/models.py`, and the validators follow the `orders/validators.py` pattern. The "exactly two deep modules" rule in `CLAUDE.md` still holds.

## Implementation phases (full tasks in the plan)

1. **Tracer bullet:** Pillow, media settings, field + migration, `display_image_url`, templates, multipart form, test media fixture.
2. **Validation:** `products/validators.py` with tests first, attached to the model field; readable messages in both forms.
3. **Processing and file lifecycle:** resize/pad/WebP in `save()`, on-commit cleanup, `post_delete` receiver.
4. **Back-office UX:** edit preview, list thumbnails, admin smoke check.
5. **Seed images and finishing:** move/rename files, seed attaches them, remove zip/folder, docs and `PROMPTS.md`.

## Important files

| File | Why |
|---|---|
| `products/models.py` | `Product`, `Category.placeholder_image`, `PLACEHOLDER_CATEGORIES`; the image field, `display_image_url`, processing, and `save()` go here |
| `products/forms.py` | `StyledModelForm` (needs a `file-input` branch), `ProductForm` (add `image`) |
| `products/views.py` | `ManageProductCreateView`/`UpdateView` (should need no changes; `ModelFormMixin` passes `request.FILES`) |
| `products/admin.py` | `ProductAdmin`; inherits the validators automatically |
| `products/management/commands/seed.py` | `_create_catalog()` is where images get attached; products are slugged with `slugify(name)` |
| `templates/products/catalog.html:64`, `detail.html:17` | current placeholder `<img>` tags |
| `templates/products/manage_product_form.html` | needs `enctype="multipart/form-data"` and the preview |
| `templates/products/manage_products.html` | gets the thumbnail column |
| `config/settings.py`, `config/urls.py` | `MEDIA_*` settings; serve media when `DEBUG` |
| `conftest.py` | add the temporary `MEDIA_ROOT` fixture and an in-memory image helper |
| `products/tests.py`, `products/test_backoffice.py` | existing test homes |
| `assets/images/placeholders/*.svg` | the 4:3 placeholders (background `#141824`) |

## Testing requirements

- Read `docs/testing.md` first. Plain fixtures in `conftest.py`, no factory-boy, and the suite green at every phase boundary.
- **Never write to the real `media/`:** every image test uses the `tmp_path` `MEDIA_ROOT` fixture.
- Generate test images in memory with Pillow; don't commit binary fixtures.
- Only the seed's own tests may call `seed`, and they need the media fixture too.
- Use pytest-django's `django_capture_on_commit_callbacks` to exercise the on-commit file deletion.
- Coverage priorities are listed in the PRD's Testing Decisions, 1–8.

## Resolved questions (decided by the user after review; all reflected in the PRD)

1. **Invalid-image errors:** readable in **both** the back office and the Django admin. Django's generic `forms.ImageField` wording must be replaced; where to set it so both forms show it is an implementation detail (plan Phase 2, task 3), and each form gets a test.
2. **Decompression bombs:** use Pillow's own protection at its default `MAX_IMAGE_PIXELS`; its warning and its error both reject.
3. **Placeholders:** shown complete, never cropped (`object-contain` on the navy frame).
4. **WebP quality:** 82.
5. **Upload limit:** 10 MB, checked after upload. Accepted.
6. **Slug changes:** existing image file names are kept.
7. **EXIF orientation** is corrected during processing.
8. **Animated images:** the first frame is used.

No open questions remain.

## Context not captured elsewhere

- The user describes themselves as a beginner and prefers decisions explained with options, trade-offs, and a recommendation. They want to review the plan before implementation starts and asked not to start implementing in the design session.
- Marketing image facts: 11 portrait (about 1122×1402), MindSync Duo landscape (1536×1024), Calm Collar about square (1234×1275); 1.7–2.5 MB each. All are dark scenes, which is why navy padding blends in.
- The padding-comparison preview script and contact sheet were made in the previous session's temporary scratchpad and may be gone. Regenerate with Pillow if needed. They aren't part of the repo.

## Suggested skills

- **`run`**: launch the dev server to check the catalog, detail, and back-office pages at the end of each phase.
- **`code-review`**: review each phase's diff before committing.
- **`simplify`**: tidy the processing and lifecycle code after Phase 3.
- **`handoff`**: refresh this file at the end of the implementation session.
