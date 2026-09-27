# Browser walkthrough

Drives the whole UI in a real browser and writes a screenshot per page, in both
themes and at three viewport widths. Screenshots go to `test-results/ui-screenshots/`
(gitignored) along with `findings.json`.

It is **not** a screenshot-diff harness. It exists because a unit test renders a
component and a browser renders the application, and the gap between those two
is where this project kept finding bugs: a CSS rule losing to a later one at
equal specificity, a page 79px wider than a phone, a section reading an endpoint
that is always empty. None of those fail a Vitest run.

So the script also records what a screenshot cannot show — console errors,
failed requests, visible error panels, and horizontal page overflow — and prints
them at the end. A page that 500s and falls back to its error panel photographs
perfectly well.

## Running it

```bash
# 1. Seed a throwaway database (from arep_implementation/)
python scripts/seed_ui_demo.py /tmp/ui_demo.db

# 2. Backend against it
ORION_ENV=dev \
ORION_SECRET_KEY=ui-walkthrough-secret-key-32-characters-long \
ORION_DATABASE_URL=sqlite:////tmp/ui_demo.db \
python -m uvicorn arep.api.app:app --port 8000

# 3. Frontend (from orion-frontend/)
npm run dev -- --port 5174

# 4. The walkthrough
npx playwright install chromium   # first time only
npm run e2e
```

`ORION_UI_BASE` overrides the URL, `ORION_UI_OUT` the output directory.

## Why it is seeded rather than empty

Every section is driven by a real endpoint, so an empty database produces eight
screenshots of the empty state. The seed deliberately includes the states that
are easy to get wrong: a collided run beside clean ones, a batch still running,
a revoked API key next to a live one, a comparison that found a regression, and
a search that broke the model.
