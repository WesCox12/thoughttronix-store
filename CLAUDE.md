# CLAUDE.md — The ThoughtTronix Store

A server-rendered Django 6 storefront and back office. The PRD (`prd/core-platform.md`) and the plan (`plans/core-platform.md`) record how the core platform was designed and built.

## Commands

- `uv sync` — install dependencies (Python 3.13, managed by uv)
- `uv run python manage.py migrate` — apply migrations
- `uv run python manage.py seed` — reset the database to the demo world
  (destructive, idempotent)
- `uv run python manage.py tailwind runserver` — dev server + Tailwind watch
- `uv run python manage.py tailwind build` — compile production CSS
- `uv run pytest` — run the test suite
- `uv run ruff check .` and `uv run ruff format .` — lint and format

## Project layout

- `config/` — the project package (settings, root urls)
- `accounts/` — custom user model (`accounts.User`, `AbstractUser` + nullable
  `job_title`). Roles are Django's own vocabulary: customers are plain users,
  employees are `is_staff`, the admin is `is_superuser`. No role field, no Groups.
- `products/` — catalog (`Category`, `Product`, `Tag`), its back-office CRUD,
  and the `seed` command. Product images (Pillow): the rules are in
  `products/validators.py`, the form-field wiring in `products/fields.py`,
  and processing plus file cleanup in `Product.save()` and a `post_delete`
  receiver in `products/models.py`. Requirements: `prd/product-images.md`.
- `products/seed_images/` — Marketing's images, named `<slug>.png`; the seed
  attaches them
- `media/` — uploaded files (`MEDIA_ROOT`; gitignored, served only when
  `DEBUG` is on). Tests use the `media_root` fixture, never the real folder.
- `orders/` — cart, checkout, orders, and back-office order management
- `dashboard/` — the staff analytics dashboard
- `PROMPTS.md` — the AI-usage log; append entries, never rewrite history
- `templates/` — project-level templates (`base.html`); app templates live in
  `templates/<app>/`
- `assets/` — static sources; `assets/css/source.css` is the Tailwind input,
  `assets/css/tailwind.css` is compiled output (gitignored, never edit)

## Architecture convention

Logic lives in models and managers; cross-model workflows get a service
module; views stay thin.

Exactly two deliberate deep modules, docstrings and type hints on every
public function: `orders/services.py` (`quote_cart` and `place_order`;
details in `orders/CLAUDE.md`) and `dashboard/queries.py` (the dashboard's
aggregations).

Back-office views gate on `is_staff` with `accounts.mixins.StaffRequiredMixin`.

Idiomatic Django throughout: class-based views, model methods, custom
managers/querysets, forms own their validation. Settings read from `.env`
via environs with working defaults — the app must run with no `.env` present.

UI is Tailwind + DaisyUI + HTMX only; template rules live in
`templates/CLAUDE.md`.

## URL conventions

- Every URL is named; every app has a namespace (`products:catalog`,
  `orders:checkout`).
- Public catalog URLs use slugs (`/products/seraphine-home-hub/`);
  back-office URLs use pks.
- `Product` defines `get_absolute_url`.

## Testing

Before writing or changing tests, read `docs/testing.md`. The suite must be
green at every phase boundary, and the destructive seed command is never
used for ordinary test setup.