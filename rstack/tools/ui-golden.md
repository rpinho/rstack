# ui-golden

Capture a Chromium viewport with Playwright, compare exact pixels with Pillow,
and replace a golden only through an explicit `approve` command. This tool has
no profile discovery or automatic approval.

Use a Python environment that already has `playwright` and `Pillow`, and an
existing Playwright Chromium browser. Nothing is installed by the tool. To reuse
an installed Chrome, set `UI_GOLDEN_BROWSER_CHANNEL=chrome`, or set
`UI_GOLDEN_BROWSER_EXECUTABLE` to an existing Chromium executable.

```sh
ui-golden render --url http://127.0.0.1:8000/ --viewport 1024x768 --out actual.png
ui-golden compare --golden home.png --actual actual.png --threshold 0.01
# Only after a person reviews the actual screenshot:
ui-golden approve --actual actual.png --golden home.png
```

`render --storage-state state.json` reads standard Playwright cookies and origin
local storage. `--wait-selector SELECTOR` waits for a visible application element.
Rendering waits for network idle, fonts and images; HTTP failures refuse. The
screenshot covers the viewport at device scale 1, with reduced motion, disabled
animations and a hidden caret. Service workers are blocked to capture the served
build. Keep browser, fonts and host consistent between approval and comparison.

`compare` prints JSON with `changed_pixel_fraction`, counts and the diff path.
A pixel changes if any RGBA channel changes. The denominator is all unmasked
pixels. The default diff is `actual.diff.png`; `--diff PATH` changes it. Changed
pixels are pink over a dimmed actual image. Exit status is 0 at or below the
threshold, 1 above it (or for different dimensions), and 2 for missing/invalid
input. Missing goldens print an explicit approval command. Neither render nor
compare writes to the golden.

`--mask mask.json` accepts an array of rectangles such as
`[{"x":0,"y":0,"width":100,"height":20}]`. Coordinates are viewport pixels.
Out-of-bounds rectangles and masks hiding the whole screenshot refuse. Use masks
only for reviewed dynamic regions. Screenshots are limited to 16 million pixels.

Synthetic tests:

```sh
python3 -m pytest -q rstack/tests/test_ui_golden.py
```

The browser test skips when the Python Playwright package is absent. Run it in
the configured browser environment to verify rendering as well as comparisons.

For a routed game's first screen, pass `--expect-hash '#game'`. A redirect to
home or another activity refuses capture, even if a home selector is visible.
The renderer waits for embedded frames as well as the top document, including
fonts and decoded images, and refuses HTTP errors or uncaught page exceptions.
