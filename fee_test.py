def calculate_fee(price):
    listing_fee = max(1, int(price * 0.05))
    exchange_fee = max(1, int(price * 0.10))
    return listing_fee + exchange_fee


print("Price 10:", 10 - calculate_fee(10))
print("Price 117:", 117 - calculate_fee(117))
