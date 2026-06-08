import sys
import re
import html
import ctypes
from ctypes import wintypes

'''
Usage: python costco_receipt_parser.py <input_file> <prefix>

Pushes the parsed items onto the Windows clipboard as an HTML table so that pasting
into Google Sheets yields two columns: a clickable item-name hyperlink and the
tax-inclusive price. (Pasting a plain `=HYPERLINK(...)` formula via the terminal is
fragile — terminals can swallow the tab separator and Sheets locales disagree on the
formula's argument delimiter.) The same data is also printed to stdout for review.

TODO:
 1. add capability for parsing liquor tax, e.g. "	2465	LIQUOR LITER TAX T/1080962	2.83"
    and sweetened beverage fee, e.g. "2850	SB RECOVERY/2007031	7.56"
'''
TAX_RATE = .1055
ITEM_URL_PREFIX = "https://app.warehouserunner.com/costco/"
DEBUG = False

# Win32 clipboard plumbing. We talk to user32/kernel32 directly instead of shelling
# out to PowerShell because the subprocess hand-off was dropping the clipboard payload
# on process exit on some setups.
_GMEM_MOVEABLE = 0x0002
_CF_UNICODETEXT = 13
_u32 = ctypes.windll.user32
_k32 = ctypes.windll.kernel32
_u32.OpenClipboard.argtypes = [wintypes.HWND]
_u32.OpenClipboard.restype = wintypes.BOOL
_u32.EmptyClipboard.restype = wintypes.BOOL
_u32.CloseClipboard.restype = wintypes.BOOL
_u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_u32.SetClipboardData.restype = wintypes.HANDLE
_u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
_u32.RegisterClipboardFormatW.restype = wintypes.UINT
_k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_k32.GlobalAlloc.restype = wintypes.HGLOBAL
_k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_k32.GlobalLock.restype = wintypes.LPVOID
_k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_k32.GlobalUnlock.restype = wintypes.BOOL


def _alloc_handle(data: bytes):
    h = _k32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
    if not h:
        raise OSError("GlobalAlloc failed")
    p = _k32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    _k32.GlobalUnlock(h)
    return h


def _build_cf_html(fragment: str) -> bytes:
    # The CF_HTML clipboard format requires a header whose StartHTML/EndHTML/
    # StartFragment/EndFragment fields are *byte* offsets into the UTF-8 payload.
    # Using 10-digit-wide placeholders keeps the header's own length stable so we
    # can compute the offsets after the fact and substitute them back in.
    pre = "<html><body><!--StartFragment-->"
    post = "<!--EndFragment--></body></html>"
    header_fmt = (
        "Version:0.9\r\n"
        "StartHTML:{:010d}\r\n"
        "EndHTML:{:010d}\r\n"
        "StartFragment:{:010d}\r\n"
        "EndFragment:{:010d}\r\n"
    )
    header_size = len(header_fmt.format(0, 0, 0, 0).encode("utf-8"))
    pre_b = pre.encode("utf-8")
    frag_b = fragment.encode("utf-8")
    post_b = post.encode("utf-8")
    start_html = header_size
    start_frag = start_html + len(pre_b)
    end_frag = start_frag + len(frag_b)
    end_html = end_frag + len(post_b)
    header = header_fmt.format(start_html, end_html, start_frag, end_frag).encode("utf-8")
    return header + pre_b + frag_b + post_b


def copy_to_clipboard(html_fragment: str, plain_text: str):
    cf_html = _u32.RegisterClipboardFormatW("HTML Format")
    html_bytes = _build_cf_html(html_fragment) + b"\x00"
    text_bytes = plain_text.encode("utf-16-le") + b"\x00\x00"
    if not _u32.OpenClipboard(None):
        raise OSError("OpenClipboard failed")
    try:
        _u32.EmptyClipboard()
        _u32.SetClipboardData(cf_html, _alloc_handle(html_bytes))
        _u32.SetClipboardData(_CF_UNICODETEXT, _alloc_handle(text_bytes))
    finally:
        _u32.CloseClipboard()
def parse_columns_from_file(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()

    result = []
    receipt = {"subtotal": None, "tax": None, "total": None}
    coupons_applied = 0
    unparsed = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Item / coupon line: optional leading E, then item number, name, price, optional Y/N.
        match = re.match(r'^[A-Z]?\s*(\d+)\s+(.*?)\s+(\d+\.\d+\-*)\s*([YN])?$', stripped)
        if match:
            item_number = match.group(1).strip()
            item_name = match.group(2).strip()
            item_price = match.group(3).strip()
            # for coupons, add the discount to the last item
            if item_price.endswith('-'):
                item_price = '-' + item_price[:-1]  # Move the dash to the front
                prev = result[-1]
                result[-1] = (prev[0], prev[1], prev[2] + float(item_price), prev[3])
                coupons_applied += 1
                if DEBUG:
                    print("parsed coupon for: " + str(result[-1]))
            else:
                # items usually end with a Y or N, meaning taxed or not taxed
                taxed = match.group(4).strip()
                result.append((item_number, item_name, float(item_price), taxed))
                if DEBUG:
                    print("parsed item: " + str(result[-1]))
            continue

        m = re.match(r'SUBTOTAL\s+(\d+\.\d+)', stripped, re.IGNORECASE)
        if m:
            receipt["subtotal"] = float(m.group(1))
            continue

        m = re.match(r'TAX\s+(\d+\.\d+)', stripped, re.IGNORECASE)
        if m:
            receipt["tax"] = float(m.group(1))
            continue

        m = re.match(r'.*Total\s+(\d+\.\d+)', stripped, re.IGNORECASE)
        if m:
            receipt["total"] = float(m.group(1))
            continue

        unparsed.append(stripped)

    return result, receipt, coupons_applied, unparsed

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python costco_receipt_parser.py <input_file> <prefix>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    prefix = sys.argv[2]
    parsed_columns, receipt_totals, coupons_applied, unparsed_lines = parse_columns_from_file(input_file)

    if DEBUG:
        for item_number, item_name, item_price, taxed in parsed_columns:
            print(f"{item_number}, {item_name}, {item_price:.2f}, {taxed}")

    result = []
    total_tax = 0.0
    calculated_total = 0.0
    for item_number, item_name, item_price, taxed in parsed_columns:
        item_total = item_price

        # Apply tax rate to taxed items. Since we round here when calculating the item's total price
        # (rather than taxing the subtotal), there might be a slight error when comparing the
        # calculated tax/total vs the receipt's
        if taxed and taxed == 'Y':
            item_tax = round(TAX_RATE * item_price, 2)
            item_total += item_tax
            total_tax += item_tax

        calculated_total += item_total
        result.append((item_number, item_name, item_total))

    html_rows = []
    text_rows = []
    for item_number, item_name, item_price in result:
        url = f"{ITEM_URL_PREFIX}{item_number}"
        print(f"{prefix}{item_name}\t{item_price:.2f}\t{url}")
        # Prefix sits as plain text in the cell; only the item name is the anchor.
        html_rows.append(
            f'<tr><td>{html.escape(prefix)}'
            f'<a href="{html.escape(url, quote=True)}">{html.escape(item_name)}</a>'
            f'</td><td>{item_price:.2f}</td></tr>'
        )
        text_rows.append(f"{prefix}{item_name}\t{item_price:.2f}")
    copy_to_clipboard(
        "<table>" + "".join(html_rows) + "</table>",
        "\r\n".join(text_rows),
    )
    print(f"\nCopied {len(result)} items to clipboard — paste into Sheets.")

    calculated_subtotal = sum(parsed_col[2] for parsed_col in parsed_columns)

    # Sanity checks. The receipt-reported subtotal/tax/total don't have to match exactly:
    # per-item rounding of the tax can drift a bit, so use a forgiving threshold and flag
    # only when the gap is large enough to suggest something real (missing item, unparsed
    # surcharge line, wrong tax rate, etc.).
    DRIFT_THRESHOLD = 1.00

    def _check(name, receipt_value, calculated_value):
        if receipt_value is None:
            print(f"  {name}: calculated {calculated_value:.2f} (no receipt value found)")
            return
        delta = calculated_value - receipt_value
        flag = "  [!] check receipt" if abs(delta) > DRIFT_THRESHOLD else ""
        print(f"  {name}: receipt {receipt_value:.2f}, calculated {calculated_value:.2f}, delta {delta:+.2f}{flag}")

    print("\nSanity check:")
    print(f"  Items parsed: {len(parsed_columns)}")
    print(f"  Items output: {len(result)}"
          + ("  [!] mismatch" if len(result) != len(parsed_columns) else ""))
    print(f"  Coupons applied: {coupons_applied}")
    _check("Subtotal", receipt_totals["subtotal"], calculated_subtotal)
    _check("Tax", receipt_totals["tax"], total_tax)
    _check("Total", receipt_totals["total"], calculated_total)
    if unparsed_lines:
        print(f"  Unparsed lines ({len(unparsed_lines)}) — possibly liquor tax or SB recovery surcharges:")
        for line in unparsed_lines:
            print(f"    {line}")
    