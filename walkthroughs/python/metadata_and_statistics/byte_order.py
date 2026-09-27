# Sort four cities by their UTF-8 bytes, then by the same bytes read as signed numbers.
cities = ["Zürich", "Łódź", "Aarhus", "Århus"]
for city in cities:
    print(city, city.encode().hex(" "))

def signed(city):  # each byte as Java's byte reads it: 0x80 and above are negative
    return [b - 256 if b > 127 else b for b in city.encode()]

print("unsigned bytes:", ", ".join(sorted(cities, key=str.encode)))
print("signed bytes:  ", ", ".join(sorted(cities, key=signed)))
print("Python's sort: ", ", ".join(sorted(cities)))  # by code point, as UTF-8's bytes are
