# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Personal household-bill-splitting utilities. Receipts copy-pasted from the Costco app are saved as plaintext under `receipts/` (filename pattern `YYYY_MM_DD.txt`) and parsed by `costco_receipt_parser.py` into an itemized, tax-applied list with a per-item prefix used downstream for bill attribution.

## Running the parser

```
python costco_receipt_parser.py <input_file> <prefix>
```

Example: `python costco_receipt_parser.py receipts/2026_05_26.txt "C "` prints each item with its tax-inclusive price prefixed by `C ` and the parsed/calculated subtotal, tax, and total.

There are no tests, build steps, lint config, or dependencies beyond the Python stdlib. The script does shell out to PowerShell + `System.Windows.Forms.Clipboard` to set the HTML clipboard payload (see below), so it's Windows-only as written.

## Output: stdout vs. clipboard

Two outputs each run:

- **stdout** is a plain `prefix+item_name \t price \t url` preview for eyeballing, plus receipt-vs-calculated totals.
- **clipboard** receives an HTML `<table>` with one `<a href="…/costco/{item_no}">prefix+item_name</a>` per `<tr>`. Pasting into Google Sheets yields two columns (clickable item-name hyperlink, price) directly — no "Split text to columns" step.

HTML clipboard (not a `=HYPERLINK(...)` formula) is used deliberately: pasting the formula via terminal-copy was fragile because some terminals replace the tab separator with spaces (collapsing everything into one malformed-formula cell) and some Sheets locales use `;` not `,` as the HYPERLINK arg separator. `app.warehouserunner.com/costco/{item_no}` resolves to the per-item product page without the URL slug.

## Receipt format the parser expects

Each item line in `receipts/*.txt` looks like:

```
E	1127099	QUESO CHIHUA	12.29 N
```

Fields are: optional leading `E`, item number, item name, price, and a taxed flag (`Y`/`N`). Tab-separated in the source files. Two non-item line shapes also matter:

- **Coupons** — a line whose price ends in `-` (e.g. `360730	/ 1894414	4.00-`). These don't produce their own item; the parser subtracts the discount from the *previous* item parsed and the dash is moved to the front of the number.
- **Totals** — lines starting with `SUBTOTAL`, `TAX`, or containing `Total` are captured separately and printed for sanity-checking against the calculated values.

## Tax handling quirk

`TAX_RATE = 0.1055` is applied **per taxed item** (rounded to 2 decimals) rather than to the subtotal. The script's own comment flags that this can cause small drift versus the receipt's printed tax/total — expected, not a bug. Don't "fix" this by switching to subtotal-based tax without checking why it was done per-item (the per-item totals are what gets shared downstream, so each line needs to carry its own tax).

## Known gaps (from the source TODO)

- Liquor tax lines (e.g. `2465	LIQUOR LITER TAX T/1080962	2.83`) and sweetened-beverage-fee lines (e.g. `2850	SB RECOVERY/2007031	7.56`) are not yet parsed. These look like items to the current regex but represent surcharges on a prior item, similar to how coupons are handled.
- No hyperlinking of item product numbers.
