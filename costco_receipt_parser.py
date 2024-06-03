import sys
import re

TAX_RATE = .1035
DEBUG = False
def parse_columns_from_file(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    
    result = []
    
    for line in lines:
        # Using regex to capture the item name and price, ensuring the price starts with a number and a decimal point
        match = re.match(r'^[A-Z]?\s*\d+\s+(.*?)\s+(\d+\.\d+\-*)\s*([YN])?$', line.strip())
        if match:
            item_name = match.group(1).strip()
            item_price = match.group(2).strip()
            # for coupons, add the discount to the last item
            if item_price.endswith('-'):
                item_price = '-' + item_price[:-1]  # Move the dash to the front
                result[-1] = (result[-1][0], result[-1][1] + float(item_price), result[-1][2])
            else:
                # items usually end with a Y or N, meaning taxed or not taxed
                taxed = match.group(3).strip()
                result.append((item_name, float(item_price), taxed))
            
        # Using regex to capture subtotal
        match = re.match(r'SUBTOTAL\s+(\d+\.\d+)', line.strip())
        if match:
            subtotal = float(match.group(1).strip())
            print(f"Receipt subtotal: {subtotal:.2f}")
        
        # Using regex to capture tax
        match = re.match(r'TAX\s+(\d+\.\d+)', line.strip())
        if match:
            tax = float(match.group(1).strip())
            print(f"Receipt tax: {tax:.2f}")
        
        # Using regex to capture total
        match = re.match(r'.*Total\s+(\d+\.\d+)', line.strip())
        if match:
            total = float(match.group(1).strip())
            print(f"Receipt total: {total:.2f}")
        
    print()
    return result

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python costco_receipt_parser.py <input_file> <prefix>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    prefix = sys.argv[2]
    parsed_columns = parse_columns_from_file(input_file)
    
    if DEBUG:
        for item_name, item_price, taxed in parsed_columns:
            print(f"{item_name}, {item_price:.2f}, {taxed}")
    
    result = []
    total_tax = 0.0
    calculated_total = 0.0
    for item_name, item_price, taxed in parsed_columns:
        item_total = item_price

        # Apply tax rate to taxed items. Since we round here when calculating the item's total price
        # (rather than taxing the subtotal), there might be a slight error when comparing the
        # calculated tax/total vs the receipt's
        if taxed and taxed == 'Y':
            item_tax = round(TAX_RATE * item_price, 2)
            item_total += item_tax
            total_tax += item_tax
        
        calculated_total += item_total
        result.append((item_name, item_total))
    
    for item_name, item_price in result:
        print(f"{prefix}{item_name}, {item_price:.2f}")

    print()
    subtotal = sum(parsed_col[1] for parsed_col in parsed_columns)
    print(f"Calculated subtotal: {subtotal}")
    print(f"Calculated tax: {total_tax:.2f}")
    print(f"Calculated total: {calculated_total:.2f}")
    