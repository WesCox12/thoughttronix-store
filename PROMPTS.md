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
