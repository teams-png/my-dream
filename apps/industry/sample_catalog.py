"""Sample products, services and records a new business starts with (see sample_kit.py).

Prices are in QAR and converted with the restaurant kit's currency factors. Each kit is a dict:
  products: P(...) rows (stocked items, optional size / colour / gender / industry attributes)
  variants: V(...) rows (one product sold in several sizes / colours: a parent plus one product per variant)
  services: S(...) rows (no stock: labour, sessions, fees, packages)
Business types without their own kit use their family's kit, then their group's.
"""


def P(name, category, price, brand="", stock=12, unit="pcs", **attrs):
    return {"name": name, "category": category, "price": price, "brand": brand, "stock": stock, "unit": unit,
            "attrs": attrs}


def V(name, category, price, brand="", sizes=(), colours=(), stock=4, **attrs):
    return {"name": name, "category": category, "price": price, "brand": brand, "sizes": list(sizes),
            "colours": list(colours), "stock": stock, "attrs": attrs}


def S(name, category, price, minutes=0):
    return {"name": name, "category": category, "price": price, "minutes": minutes}


CUSTOMERS = [("Ahmed Al-Kuwari", "+974 5550 1001", "ahmed@example.com"),
             ("Fathima Rahman", "+974 5550 1002", "fathima@example.com"),
             ("John Mathew", "+974 5550 1003", "")]
SUPPLIERS = [("Al Meera Wholesale", "+974 4440 2001"), ("Gulf Trading Co.", "+974 4440 2002")]
STAFF = [("Ravi Kumar", "Senior staff", 3500), ("Maria Santos", "Staff", 2800)]

# ------------------------------------------------------------------ retail
KITS = {
    "clothing_store": {
        "variants": [
            V("Men's cotton shirt", "Shirts", 89, "Van Heusen", sizes=["S", "M", "L", "XL"], colours=["White", "Sky blue"],
              gender="Men", material_spec="100% cotton"),
            V("Women's kurti", "Kurtis", 120, "Biba", sizes=["S", "M", "L"], colours=["Maroon", "Mustard"],
              gender="Women", material_spec="Rayon"),
            V("Kids T-shirt", "Kids wear", 35, "Max", sizes=["2-3Y", "4-5Y", "6-7Y"], colours=["Red", "Navy"],
              gender="Kids", material_spec="Cotton jersey"),
        ],
        "products": [P("Men's kandura – white", "Kandura", 180, "Al Jazeera", stock=8, size="56", colour="White",
                       gender="Men", material_spec="Japanese cotton"),
                     P("Leather belt", "Accessories", 45, "Woodland", colour="Brown", gender="Men")],
    },
    "ladies_fashion_boutique": {
        "variants": [V("Party gown", "Gowns", 450, "House design", sizes=["S", "M", "L"], colours=["Wine", "Emerald"],
                       gender="Women", material_spec="Georgette", design_reference="BTQ-G-01"),
                     V("Abaya – embroidered", "Abayas", 320, "House design", sizes=["52", "54", "56"], colours=["Black"],
                       gender="Women", material_spec="Nida")],
        "products": [P("Silk scarf", "Accessories", 75, stock=10, colour="Peach", gender="Women", material_spec="Silk"),
                     P("Clutch bag", "Bags", 140, stock=6, colour="Gold", gender="Women")],
    },
    "footwear_store": {
        "variants": [V("Running shoes", "Sports shoes", 249, "Nike", sizes=["40", "41", "42", "43"], colours=["Black"],
                       gender="Men", material_spec="Mesh"),
                     V("Women's sandals", "Sandals", 99, "Bata", sizes=["36", "37", "38", "39"], colours=["Tan", "Black"],
                       gender="Women"),
                     V("Kids school shoes", "School shoes", 79, "Bata", sizes=["30", "32", "34"], colours=["Black"],
                       gender="Kids")],
        "products": [P("Shoe polish", "Care", 12, "Kiwi", stock=30, colour="Black")],
    },
    "uniform_shop": {
        "variants": [V("School shirt", "School uniform", 45, sizes=["24", "28", "32", "36"], colours=["White"],
                       gender="Kids", organization_name="Sample School"),
                     V("Work coverall", "Workwear", 85, sizes=["M", "L", "XL"], colours=["Navy", "Orange"], gender="Unisex")],
        "products": [P("School tie", "Accessories", 15, stock=40, colour="Maroon")],
    },
    "textile": {
        "products": [P("Kanjeevaram silk saree", "Sarees", 650, "Pothys", stock=6, colour="Red", material="Silk",
                       design="Temple border", fabric_type="saree"),
                     P("Cotton shirting", "Shirting", 25, "Raymond", stock=120, unit="meter", colour="White",
                       material="Cotton", fabric_type="shirting"),
                     P("Linen suiting", "Suiting", 60, "Raymond", stock=80, unit="meter", colour="Beige",
                       material="Linen", fabric_type="suiting"),
                     P("Churidar material", "Dress material", 110, stock=15, colour="Green", material="Cotton",
                       fabric_type="dress_material")],
        "services": [S("Shirt stitching", "Tailoring", 45, 0), S("Blouse stitching", "Tailoring", 60, 0),
                     S("Pant alteration", "Alteration", 15, 0)],
    },
    "sports_shop": {
        "variants": [V("Football jersey", "Football", 99, "Adidas", sizes=["S", "M", "L"], colours=["Red", "Blue"],
                       gender="Unisex", sport_category="football"),
                     V("Running shoes", "Running", 279, "Asics", sizes=["41", "42", "43"], colours=["Grey"],
                       gender="Men", sport_category="running")],
        "products": [P("Cricket bat – English willow", "Cricket", 450, "SG", stock=5, sport_category="cricket",
                       gender="Unisex", material="English willow"),
                     P("Badminton racket", "Badminton", 160, "Yonex", stock=8, sport_category="badminton",
                       gender="Unisex"),
                     P("Football size 5", "Football", 75, "Nivia", stock=15, sport_category="football"),
                     P("Dumbbell 5 kg (pair)", "Gym equipment", 90, stock=10, sport_category="gym_equipment")],
    },
    "cycle_shop": {
        "products": [P("Mountain bike 27.5\"", "Bicycles", 1200, "Trek", stock=3, size="M", colour="Black"),
                     P("Kids bicycle 16\"", "Bicycles", 380, "Hero", stock=4, size="16\"", colour="Red", gender="Kids"),
                     P("Cycle helmet", "Accessories", 85, "Giro", stock=10, size="M"),
                     P("Inner tube 26\"", "Spare parts", 18, stock=25)],
        "services": [S("General service", "Service", 60, 60), S("Puncture repair", "Service", 15, 15)],
    },
    "mobile_shop": {
        "products": [P("Samsung Galaxy A15 128GB", "Mobiles", 699, "Samsung", stock=4, colour="Black",
                       item_type="accessory", model_number="SM-A155F", warranty_months=12),
                     P("iPhone 15 128GB", "Mobiles", 3299, "Apple", stock=2, colour="Blue", item_type="accessory",
                       warranty_months=12),
                     P("20W fast charger", "Chargers", 49, "Anker", stock=20),
                     P("Tempered glass", "Screen guards", 15, stock=50),
                     P("Silicone back cover", "Covers", 25, stock=30, colour="Clear")],
        "services": [S("Screen replacement (labour)", "Repairs", 80, 60), S("Software update", "Repairs", 30, 30)],
    },
    "mobile_accessories_shop": {
        "products": [P("20W fast charger", "Chargers", 49, "Anker", compatible_models="iPhone / Android", warranty_months=6),
                     P("Wireless earbuds", "Audio", 129, "JBL", stock=10, colour="White", warranty_months=12),
                     P("Power bank 10000 mAh", "Power banks", 89, "Xiaomi", stock=12),
                     P("Tempered glass", "Screen guards", 15, stock=50)],
    },
    "electronics_store": {
        "products": [P("55\" 4K Smart TV", "Televisions", 1899, "Samsung", stock=3, model_number="UA55CU7000",
                       warranty_months=24),
                     P("Bluetooth speaker", "Audio", 199, "JBL", stock=8, colour="Black", warranty_months=12),
                     P("Air fryer 4L", "Kitchen appliances", 299, "Philips", stock=6, warranty_months=24),
                     P("HDMI cable 2m", "Cables", 25, stock=30)],
        "services": [S("TV wall mounting", "Installation", 100, 60)],
    },
    "computer_shop": {
        "products": [P("Laptop 15.6\" i5 16GB", "Laptops", 2799, "Lenovo", stock=3, model_number="IdeaPad 5",
                       warranty_months=12),
                     P("Wireless mouse", "Accessories", 45, "Logitech", stock=20),
                     P("1TB external SSD", "Storage", 349, "Samsung", stock=6, warranty_months=36),
                     P("27\" monitor", "Monitors", 799, "Dell", stock=4, warranty_months=36)],
        "services": [S("Windows installation", "Service", 80, 60), S("Laptop cleaning", "Service", 60, 45)],
    },
    "home_appliances_store": {
        "products": [P("Split AC 1.5 ton", "Air conditioners", 1899, "LG", stock=4, warranty_months=24),
                     P("Washing machine 8 kg", "Laundry", 1499, "Samsung", stock=3, warranty_months=24),
                     P("Microwave oven 25L", "Kitchen", 399, "Panasonic", stock=6, warranty_months=12)],
        "services": [S("Installation & delivery", "Service", 100, 90)],
    },
    "perfume_shop": {
        "products": [P("Oud Royal 100ml", "Oud", 450, "Arabian Oud", stock=8, gender="Men", volume_ml=100,
                       fragrance_family="Oud / woody", concentration="Eau de Parfum"),
                     P("Rose Musk 50ml", "Floral", 220, "Ajmal", stock=10, gender="Women", volume_ml=50,
                       fragrance_family="Floral", concentration="Eau de Parfum"),
                     P("Bakhoor 50g", "Bakhoor", 60, "Rasasi", stock=20),
                     P("Attar 12ml", "Attar", 80, "Ajmal", stock=15, gender="Unisex", volume_ml=12)],
    },
    "watch_shop": {
        "products": [P("Men's chronograph watch", "Men", 899, "Casio", stock=4, gender="Men", model_number="EFR-539",
                       movement="Quartz", strap_material="Stainless steel", water_resistance="100 m"),
                     P("Women's dress watch", "Women", 650, "Fossil", stock=4, gender="Women", movement="Quartz",
                       strap_material="Leather", colour="Rose gold"),
                     P("Smart watch", "Smart", 499, "Huawei", stock=5, gender="Unisex")],
        "services": [S("Battery replacement", "Service", 25, 15), S("Strap fitting", "Service", 15, 10)],
    },
    "cosmetics_store": {
        "products": [P("Matte lipstick", "Lips", 59, "Maybelline", stock=20, colour="Ruby", shade="Ruby woo",
                       gender="Women"),
                     P("Foundation 30ml", "Face", 89, "L'Oréal", stock=12, shade="Natural beige", skin_type="All"),
                     P("Sunscreen SPF 50", "Skin care", 75, "Neutrogena", stock=15, skin_type="Oily / combination"),
                     P("Beard oil 30ml", "Men's grooming", 45, stock=10, gender="Men")],
    },
    "jewelry_shop": {
        "products": [P("22K gold bangle", "Bangles", 0, "House design", stock=2, weight_grams="12.000", purity="22K",
                       making_mode="per_gram", making_charge="15"),
                     P("22K gold chain", "Chains", 0, "House design", stock=3, weight_grams="8.000", purity="22K",
                       making_mode="per_gram", making_charge="12"),
                     P("18K diamond ring", "Rings", 0, stock=2, weight_grams="4.000", purity="18K", making_mode="fixed",
                       making_charge="150", stone_value="900", stone_details="0.20 ct diamond")],
    },
    "optical_shop": {
        "products": [P("Metal frame – rectangle", "Frames", 249, "Ray-Ban", stock=6, frame_material="Metal",
                       gender="Unisex", colour="Gunmetal"),
                     P("Single-vision lenses (pair)", "Lenses", 150, "Essilor", stock=20, lens_type="Single vision"),
                     P("Sunglasses – aviator", "Sunglasses", 399, "Ray-Ban", stock=5, gender="Men"),
                     P("Contact lens solution", "Care", 35, "Bausch + Lomb", stock=20)],
        "services": [S("Eye test", "Service", 50, 20)],
    },
    "book_store": {
        "products": [P("The Alchemist – Paulo Coelho", "Fiction", 45, "HarperCollins", isbn="9780062315007",
                       author="Paulo Coelho"),
                     P("Oxford English dictionary", "Reference", 85, "Oxford", stock=6),
                     P("A4 notebook 200 pages", "Stationery", 12, "Classmate", stock=60),
                     P("Ball pen (box of 10)", "Stationery", 10, "Cello", stock=40)],
    },
    "toys_gift_shop": {
        "products": [P("Building blocks set", "Toys", 120, "LEGO", stock=6, age_group="6+ years"),
                     P("Teddy bear 40 cm", "Soft toys", 55, stock=10, colour="Brown", age_group="All ages"),
                     P("Gift wrapping", "Gift wrap", 10, stock=100, occasion="Birthday")],
    },
    "baby_products_store": {
        "products": [P("Diapers size 3 (60)", "Diapers", 69, "Pampers", stock=20, age_group="6-12 months", size="3"),
                     P("Baby lotion 200ml", "Baby care", 25, "Johnson's", stock=20),
                     P("Baby romper", "Clothing", 39, stock=12, size="6-9M", colour="Yellow", gender="Kids")],
    },
    "furniture_store": {
        "products": [P("3-seater sofa", "Sofas", 1899, stock=2, colour="Grey", dimensions="210 x 90 x 85 cm",
                       material_spec="Fabric"),
                     P("Dining table 6-seater", "Dining", 1499, stock=2, material_spec="Solid wood"),
                     P("Office chair", "Office", 399, stock=6, colour="Black", assembly_required=True)],
        "services": [S("Delivery & assembly", "Service", 100, 90)],
    },
    "hardware_store": {
        "products": [P("Jotun interior paint 18L", "Paints", 260, "Jotun", stock=8, colour="White"),
                     P("Drill machine 13mm", "Power tools", 189, "Bosch", stock=4),
                     P("Screw set (100)", "Fasteners", 15, stock=50),
                     P("Measuring tape 5m", "Hand tools", 18, "Stanley", stock=20)],
    },
    "electrical_plumbing_store": {
        "products": [P("LED bulb 12W", "Lighting", 9, "Philips", stock=100),
                     P("Copper wire 2.5mm (90m)", "Wires", 180, stock=10),
                     P("PVC pipe 1\" (6m)", "Pipes", 22, stock=40),
                     P("Water tap – mixer", "Fittings", 95, "Grohe", stock=8)],
    },
    "building_materials_store": {
        "products": [P("Cement 50 kg bag", "Cement", 18, stock=200, unit="bag"),
                     P("Steel bar 12mm", "Steel", 32, stock=150),
                     P("Ceramic tile 60x60 (box)", "Tiles", 45, stock=60, unit="box", colour="Ivory")],
    },
    "auto_spare_parts": {
        "products": [P("Brake pads (front)", "Brakes", 180, "Toyota", stock=6, part_number="04465-0K240",
                       compatible_models="Hilux 2016-2023"),
                     P("Engine oil 5W-30 4L", "Oils", 95, "Mobil", stock=20),
                     P("Air filter", "Filters", 45, "Denso", stock=15, compatible_models="Corolla 2014-2019"),
                     P("Wiper blade 22\"", "Wipers", 25, "Bosch", stock=20)],
    },
    "tyre_battery_shop": {
        "products": [P("Tyre 205/55 R16", "Tyres", 280, "Bridgestone", stock=12, dimensions="205/55 R16"),
                     P("Car battery 70Ah", "Batteries", 320, "Varta", stock=6, warranty_months=18)],
        "services": [S("Wheel alignment", "Service", 60, 30), S("Wheel balancing", "Service", 40, 20),
                     S("Battery fitting", "Service", 20, 15)],
    },
    "car_showroom": {
        "products": [P("Toyota Corolla 2024 – XLI", "Sedans", 74000, "Toyota", stock=1, colour="White", model_year="2024",
                       transmission="Automatic", mileage="0 km"),
                     P("Nissan Patrol 2023 – used", "SUVs", 185000, "Nissan", stock=1, colour="Black", model_year="2023",
                       transmission="Automatic", mileage="18,000 km")],
        "services": [S("Registration & paperwork", "Service", 500, 0)],
    },
    "medical_shop": {
        "products": [P("Paracetamol 500mg (24 tablets)", "Pain relief", 8, "Panadol", stock=60),
                     P("Vitamin C 1000mg (30)", "Vitamins", 35, "Nature's Bounty", stock=25),
                     P("Cough syrup 100ml", "Cold & cough", 18, "Benadryl", stock=30),
                     P("Hand sanitiser 250ml", "Hygiene", 12, "Dettol", stock=40),
                     P("Digital thermometer", "Devices", 25, "Omron", stock=10)],
    },
    "protein_shop": {
        "products": [P("Whey protein 2 lb – chocolate", "Protein", 199, "Optimum Nutrition", stock=10, flavour="Chocolate"),
                     P("Creatine 300g", "Performance", 120, "MuscleTech", stock=10),
                     P("Protein bar", "Snacks", 9, "Grenade", stock=60, flavour="Cookies & cream"),
                     P("Shaker bottle", "Accessories", 25, stock=20)],
    },
    "medical_equipment_store": {
        "products": [P("Blood pressure monitor", "Monitors", 189, "Omron", stock=6, warranty_months=24),
                     P("Wheelchair – foldable", "Mobility", 650, stock=2),
                     P("Pulse oximeter", "Monitors", 79, stock=10)],
    },
    "pet_shop": {
        "products": [P("Cat food 2 kg", "Cat food", 65, "Whiskas", stock=15, pet_type="Cat", age_group="Adult"),
                     P("Dog food 3 kg", "Dog food", 95, "Pedigree", stock=10, pet_type="Dog", age_group="Adult"),
                     P("Pet collar", "Accessories", 25, stock=20, size="M", colour="Red")],
        "services": [S("Pet grooming", "Grooming", 120, 60)],
    },
    "flower_shop": {
        "products": [P("Red roses bouquet (12)", "Bouquets", 150, stock=6, flower_type="Rose", occasion="Anniversary"),
                     P("Orchid plant", "Plants", 120, stock=5, flower_type="Orchid"),
                     P("Greeting card", "Cards", 10, stock=40)],
        "services": [S("Same-day delivery", "Delivery", 25, 0)],
    },
    "kitchenware_store": {
        "products": [P("Non-stick frying pan 28cm", "Cookware", 89, "Tefal", stock=10),
                     P("Pressure cooker 5L", "Cookware", 150, "Prestige", stock=6),
                     P("Dinner set 24 pcs", "Dining", 220, stock=4, colour="White")],
    },
    "musical_instruments_store": {
        "products": [P("Acoustic guitar", "Guitars", 450, "Yamaha", stock=4, instrument_type="String"),
                     P("Keyboard 61 keys", "Keyboards", 699, "Casio", stock=3, instrument_type="Keyboard"),
                     P("Guitar strings set", "Accessories", 30, stock=20)],
        "services": [S("Guitar lesson (1 hour)", "Lessons", 100, 60)],
    },
    "printing_shop": {
        "products": [P("A4 paper ream", "Paper", 22, "Double A", stock=40, paper_size="A4", gsm="80")],
        "services": [S("Colour print A4 (per page)", "Printing", 1, 0), S("Business cards (100)", "Printing", 80, 0),
                     S("Flex banner (per m²)", "Large format", 35, 0), S("Lamination A4", "Finishing", 3, 0)],
    },
    "fuel_station": {
        "products": [P("Petrol – Super (litre)", "Fuel", 2.10, stock=5000, unit="litre", fuel_grade="Super 95"),
                     P("Diesel (litre)", "Fuel", 2.05, stock=5000, unit="litre", fuel_grade="Diesel"),
                     P("Engine oil 1L", "Lubricants", 30, "Shell", stock=30)],
        "services": [S("Car wash – express", "Car care", 25, 15)],
    },
    "agricultural_supplies_store": {
        "products": [P("NPK fertiliser 25 kg", "Fertilisers", 85, stock=20, unit="bag"),
                     P("Tomato seeds pack", "Seeds", 8, stock=50),
                     P("Garden hose 20m", "Tools", 45, stock=10)],
    },
    "bakery": {
        "products": [P("White bread loaf", "Bread", 5, stock=30, ingredients="Flour, yeast, salt", expiry_date=""),
                     P("Chocolate cake 1 kg", "Cakes", 95, stock=4, allergens="Milk, egg, gluten"),
                     P("Butter croissant", "Pastries", 6, stock=24, allergens="Milk, gluten"),
                     P("Cookies (per kg)", "Cookies", 45, stock=10, unit="kg", sold_by_weight=True)],
    },
    "fish_meat_shop": {
        "products": [P("Kingfish (kg)", "Fish", 38, stock=20, unit="kg", sold_by_weight=True, product_type="Fresh fish"),
                     P("Chicken whole (kg)", "Chicken", 18, stock=30, unit="kg", sold_by_weight=True),
                     P("Mutton (kg)", "Mutton", 55, stock=15, unit="kg", sold_by_weight=True, country_of_origin="India")],
        "services": [S("Cleaning & cutting", "Service", 5, 0)],
    },
    "fruits_vegetables_shop": {
        "products": [P("Banana (kg)", "Fruits", 6, stock=40, unit="kg", sold_by_weight=True, country_of_origin="India"),
                     P("Apple – red (kg)", "Fruits", 9, stock=30, unit="kg", sold_by_weight=True),
                     P("Tomato (kg)", "Vegetables", 5, stock=40, unit="kg", sold_by_weight=True),
                     P("Onion (kg)", "Vegetables", 4, stock=50, unit="kg", sold_by_weight=True)],
    },
    "trading_company": {
        "products": [P("Basmati rice 20 kg", "Rice", 120, "India Gate", stock=50, unit="bag", hs_code="1006.30",
                       minimum_order_quantity=10, country_of_origin="India"),
                     P("Sunflower oil 1.8L (carton of 6)", "Oils", 75, stock=40, unit="carton"),
                     P("Sugar 50 kg", "Sugar", 150, stock=30, unit="bag")],
    },
    "manufacturing": {
        "products": [P("Steel cabinet – 2 door", "Finished goods", 650, stock=10, bom_reference="BOM-CAB-01"),
                     P("Sheet metal 1mm", "Raw materials", 120, stock=40, unit="sheet")],
        "services": [S("Custom fabrication (hour)", "Services", 120, 60)],
    },
    "industrial_services": {
        "products": [P("Hydraulic hose 1/2\"", "Spares", 85, stock=20)],
        "services": [S("Generator servicing", "Maintenance", 450, 180), S("Annual maintenance visit", "Maintenance", 300, 120)],
    },
}

# ------------------------------------------------------------------ families (types without their own kit)
FAMILY_KITS = {
    "grocery": {
        "products": [P("Basmati rice 5 kg", "Rice & grains", 32, "India Gate", stock=30, pack_size="5 kg",
                       country_of_origin="India"),
                     P("Fresh milk 1L", "Dairy", 6.5, "Almarai", stock=40, pack_size="1 L"),
                     P("Sunflower oil 1.8L", "Cooking oil", 15, "Noor", stock=25),
                     P("Tomato (kg)", "Vegetables", 5, stock=40, unit="kg", sold_by_weight=True),
                     P("Tea bags (100)", "Beverages", 14, "Lipton", stock=30),
                     P("Dish wash liquid 1L", "Household", 9, "Fairy", stock=25)],
    },
    "general": {
        "products": [P("Sample product A", "General", 25, stock=20), P("Sample product B", "General", 49, stock=15),
                     P("Sample product C", "Accessories", 12, stock=40)],
        "services": [S("Delivery charge", "Services", 15, 0)],
    },
}
RETAIL_FAMILY = {
    "supermarket": "grocery", "grocery_store": "grocery", "general_retail": "grocery", "retail_shop": "grocery",
    "wholesale_business": "trading_company", "import_export": "trading_company", "ecommerce_store": "clothing_store",
}

# ------------------------------------------------------------------ service businesses with their own screens
SALON_SERVICES = {
    "saloon": [S("Haircut", "Hair", 30, 30), S("Beard trim", "Beard", 15, 15), S("Haircut + beard", "Hair", 40, 45),
               S("Hair colour", "Colour", 60, 45), S("Head massage", "Spa", 25, 20), S("Kids haircut", "Hair", 20, 20)],
    "beauty_parlour": [S("Eyebrow threading", "Threading", 15, 15), S("Facial – gold", "Facial", 120, 60),
                       S("Hair spa", "Hair", 90, 60), S("Manicure", "Nails", 60, 40), S("Pedicure", "Nails", 70, 45),
                       S("Bridal makeup", "Makeup", 900, 180)],
    "spa": [S("Swedish massage – 60 min", "Massage", 250, 60), S("Deep tissue massage – 60 min", "Massage", 300, 60),
            S("Hot stone therapy", "Therapy", 350, 75), S("Moroccan bath", "Bath", 200, 60),
            S("Foot reflexology – 30 min", "Massage", 120, 30)],
}
SALON_PRODUCTS = {
    "saloon": [P("Hair wax 100g", "Styling", 35, "Gatsby", stock=15, gender="Men"),
               P("Beard oil 30ml", "Grooming", 45, stock=10, gender="Men"),
               P("Anti-dandruff shampoo 400ml", "Hair care", 28, "Head & Shoulders", stock=12, gender="Unisex")],
    "beauty_parlour": [P("Hair serum 100ml", "Hair care", 55, "L'Oréal", stock=10, gender="Women"),
                       P("Nail polish", "Nails", 25, "Essie", stock=20, colour="Coral", gender="Women"),
                       P("Face mask sheet", "Skin care", 12, stock=30)],
    "spa": [P("Aroma massage oil 100ml", "Oils", 65, stock=10), P("Scented candle", "Gifts", 45, stock=12)],
}
SALON_PACKAGES = {"saloon": ("10 haircuts card", "Haircut", 10, 250),
                  "beauty_parlour": ("Facial – 5 sessions", "Facial – gold", 5, 500),
                  "spa": ("Massage – 5 sessions", "Swedish massage – 60 min", 5, 1100)}

GYM_PLANS = [("Monthly", 30, 250), ("Quarterly", 90, 650), ("Yearly", 365, 2200)]
GYM_PRODUCTS = [P("Whey protein 2 lb", "Supplements", 199, "Optimum Nutrition", stock=6),
                P("Gym gloves", "Accessories", 45, stock=10, size="M", gender="Unisex"),
                P("Water bottle 1L", "Drinks", 3, stock=48)]
GYM_SERVICES = [S("Personal training session", "Training", 150, 60), S("Day pass", "Passes", 40, 0)]

WASH_PACKAGES = [("Basic wash", "car", 30, 20, "Exterior wash and dry"),
                 ("Premium wash", "car", 60, 40, "Exterior + interior vacuum"),
                 ("Full detail", "suv", 250, 180, "Polish, wax and full interior cleaning"),
                 ("Bike wash", "bike", 15, 15, "")]
WASH_PRODUCTS = [P("Air freshener", "Car care", 10, stock=30), P("Microfibre cloth", "Car care", 8, stock=40)]

BOOKING_RESOURCES = {
    "hotel_apartment": [("Room 101 – Deluxe", "room", 350, "night", 2, "King bed, city view"),
                        ("Room 102 – Twin", "room", 300, "night", 2, "Two single beds"),
                        ("Suite 201", "room", 650, "night", 4, "Living room + kitchenette")],
    "car_rental": [("Toyota Yaris – 123456", "vehicle", 120, "day", 4, "Automatic, white"),
                   ("Nissan Patrol – 654321", "vehicle", 450, "day", 7, "4x4, black")],
    "equipment_rental": [("Scissor lift 8m", "equipment", 400, "day", 0, "Electric"),
                         ("Concrete mixer", "equipment", 150, "day", 0, "")],
    "wedding_party_hall": [("Grand ballroom", "hall", 8000, "event", 500, "Stage, lighting, parking"),
                           ("Mini hall", "hall", 2500, "event", 120, "")],
    "coworking_space": [("Hot desk 1", "space", 15, "hour", 1, "Open area"),
                        ("Meeting room A", "space", 60, "hour", 8, "TV + whiteboard")],
}
BOOKING_SERVICES = {"hotel_apartment": [S("Breakfast", "Food", 45), S("Airport pickup", "Transport", 120)],
                    "car_rental": [S("Child seat (per day)", "Extras", 15), S("Full insurance (per day)", "Extras", 40)],
                    "equipment_rental": [S("Delivery & pickup", "Transport", 150), S("Operator (per day)", "Extras", 300)],
                    "wedding_party_hall": [S("Buffet (per person)", "Catering", 85), S("Stage decoration", "Decor", 1500)],
                    "coworking_space": [S("Printing (per page)", "Services", 1), S("Monthly membership", "Plans", 900)]}

COURSES = {
    "school_training_institute": [("Spoken English – Level 1", 450, "monthly", "Sun–Thu 4–6 pm", "Ms. Anjali"),
                                  ("Computer basics", 600, "once", "Sat 10 am–1 pm", "Mr. Rahul")],
    "tuition_center": [("Grade 10 Maths", 350, "monthly", "Sun, Tue, Thu 5–6 pm", "Mr. Joseph"),
                       ("Grade 12 Physics", 400, "monthly", "Mon, Wed 6–7:30 pm", "Ms. Priya")],
    "nursery_daycare": [("Toddler class (2–3 years)", 1500, "monthly", "Sun–Thu 7 am–1 pm", "Ms. Fatima"),
                        ("Pre-KG", 1800, "monthly", "Sun–Thu 7 am–1 pm", "Ms. Leena")],
    "driving_school": [("Car – manual (20 lessons)", 2200, "once", "Flexible", "Mr. Saleem"),
                       ("Car – automatic (20 lessons)", 2400, "once", "Flexible", "Mr. Saleem")],
}
PROPERTIES = [("Al Sadd Tower", "building", "Al Sadd, Doha",
               [("Flat 101", "apartment", 2, "110 m²", 5500), ("Flat 102", "apartment", 1, "75 m²", 4200),
                ("Shop G1", "shop", 0, "40 m²", 7000)])]

# ------------------------------------------------------------------ service & project groups (fees and packages)
SERVICE_KITS = {
    "dental_clinic": [S("Consultation", "Consultation", 150, 20), S("Scaling & polishing", "Treatment", 300, 45),
                      S("Tooth filling", "Treatment", 350, 45), S("Root canal", "Treatment", 1500, 90)],
    "medical_clinic": [S("General consultation", "Consultation", 150, 15), S("Specialist consultation", "Consultation", 300, 20),
                       S("Blood test – CBC", "Lab", 80, 10), S("Dressing", "Procedures", 50, 15)],
    "physiotherapy_center": [S("Assessment", "Consultation", 200, 45), S("Physiotherapy session", "Therapy", 250, 45),
                             S("10-session package", "Packages", 2200, 0)],
    "diagnostic_laboratory": [S("CBC", "Haematology", 80, 10), S("Lipid profile", "Biochemistry", 120, 10),
                              S("HbA1c", "Biochemistry", 90, 10), S("Vitamin D", "Biochemistry", 150, 10)],
    "veterinary_clinic": [S("Consultation", "Consultation", 150, 20), S("Vaccination", "Preventive", 120, 15),
                          S("Grooming", "Grooming", 150, 60)],
    "home_nursing": [S("Nurse visit (2 hours)", "Visits", 250, 120), S("Elderly care – 12 hours", "Care", 900, 720)],
    "photography_studio": [S("Passport photos (6)", "Studio", 30, 10), S("Family photoshoot – 1 hour", "Shoots", 600, 60),
                           S("Wedding coverage", "Events", 6000, 480)],
    "consultancy": [S("Consultation – 1 hour", "Consulting", 500, 60), S("Business plan", "Projects", 5000, 0)],
    "auto_garage": [S("Oil change (labour)", "Service", 60, 30), S("Full service", "Service", 350, 180),
                    S("AC gas refill", "AC", 150, 45), S("Brake pad replacement (labour)", "Brakes", 100, 60)],
    "repair_services": [S("Inspection visit", "Visits", 50, 30), S("Repair labour (hour)", "Labour", 80, 60)],
    "electronics_repair": [S("Diagnosis", "Service", 50, 30), S("TV board repair", "Repairs", 250, 120)],
    "computer_repair": [S("Diagnosis", "Service", 50, 30), S("Windows reinstall", "Software", 120, 90),
                        S("Screen replacement (labour)", "Hardware", 150, 60)],
    "home_services": [S("Plumber visit", "Plumbing", 100, 60), S("Electrician visit", "Electrical", 100, 60),
                      S("Deep cleaning – 2 BHK", "Cleaning", 450, 240)],
    "laundry_dry_cleaning": [S("Shirt – wash & iron", "Laundry", 5, 0), S("Suit – dry clean", "Dry cleaning", 35, 0),
                             S("Kandura – wash & iron", "Laundry", 8, 0), S("Blanket – wash", "Laundry", 30, 0)],
    "travel_agency": [S("Air ticket service fee", "Tickets", 50, 0), S("Visa processing", "Visas", 250, 0),
                      S("Holiday package – Kerala 5 nights", "Packages", 3500, 0)],
    "law_firm": [S("Legal consultation", "Consultation", 500, 60), S("Contract drafting", "Documents", 1500, 0)],
    "insurance_brokerage": [S("Motor insurance – comprehensive", "Motor", 1800, 0), S("Health insurance – individual", "Health", 2500, 0)],
    "pest_control": [S("General pest control – apartment", "Treatment", 250, 90), S("Termite treatment", "Treatment", 800, 180)],
    "moving_packing": [S("1 BHK move", "Moving", 900, 300), S("Packing material set", "Materials", 150, 0)],
    "ac_maintenance": [S("AC service – split", "Service", 80, 45), S("AC gas refill", "Repairs", 150, 45),
                       S("Annual maintenance contract", "Contracts", 600, 0)],
    "cleaning_equipment_service": [S("Machine servicing", "Service", 200, 90), S("Spare part fitting", "Repairs", 80, 30)],
    "document_clearing": [S("Visa renewal", "Visas", 300, 0), S("Document attestation", "Attestation", 150, 0)],
    "school_training_institute": [S("Admission fee", "Fees", 200), S("Exam fee", "Fees", 100)],
    "tuition_center": [S("Admission fee", "Fees", 100), S("Study material", "Materials", 50)],
    "nursery_daycare": [S("Registration fee", "Fees", 500), S("Uniform & bag", "Materials", 150)],
    "driving_school": [S("File opening fee", "Fees", 300), S("Extra lesson (1 hour)", "Lessons", 120)],
    "real_estate_brokerage": [S("Rental commission", "Commission", 2000, 0), S("Property valuation", "Services", 1500, 0)],
}
PROJECT_SERVICES = {
    "advertising_agency": [S("Campaign design", "Creative", 3000), S("Social media post", "Creative", 150)],
    "digital_marketing_agency": [S("Social media management – monthly", "Retainers", 2500), S("Google Ads setup", "Ads", 1200)],
    "web_development": [S("Business website – 5 pages", "Websites", 4500), S("Hosting – yearly", "Hosting", 600),
                        S("Maintenance – monthly", "Support", 400)],
    "it_services": [S("IT support visit", "Support", 250), S("Network setup", "Projects", 2000)],
    "software_company": [S("Custom software – milestone", "Development", 10000), S("Annual support", "Support", 3000)],
    "accounting_audit": [S("Monthly bookkeeping", "Accounting", 1500), S("Annual audit", "Audit", 8000),
                         S("VAT filing", "Tax", 500)],
    "recruitment_agency": [S("Recruitment fee – per hire", "Fees", 3000), S("Visa processing", "Visas", 1500)],
    "security_services": [S("Security guard – monthly", "Guarding", 4500), S("CCTV installation", "Systems", 2500)],
    "event_management": [S("Birthday party package", "Packages", 2500), S("Stage & lighting", "Production", 4000)],
    "cleaning_company": [S("Office cleaning – monthly", "Contracts", 3000), S("Deep cleaning – villa", "One-time", 1200)],
    "maintenance_company": [S("Maintenance visit", "Visits", 200), S("Annual maintenance contract", "Contracts", 5000)],
    "landscaping_company": [S("Garden maintenance – monthly", "Maintenance", 800), S("Lawn installation (m²)", "Projects", 45)],
    "property_management": [S("Management fee – monthly", "Fees", 500), S("Tenancy contract fee", "Fees", 300)],
    "logistics_transport": [S("Truck trip – within city", "Transport", 350), S("Warehouse storage (pallet/month)", "Storage", 60)],
    "courier_delivery": [S("Same-day delivery", "Delivery", 25), S("Next-day delivery", "Delivery", 15)],
    "interior_design": [S("Design consultation", "Design", 500), S("3D design – per room", "Design", 1500)],
    "facility_management": [S("Facility management – monthly", "Contracts", 12000), S("Call-out visit", "Visits", 250)],
    "construction": [S("Site survey", "Pre-construction", 1500), S("Labour – mason (day)", "Labour", 250)],
}
PROJECT_MATERIALS = {
    "construction": [P("Cement 50 kg bag", "Materials", 18, stock=100, unit="bag"),
                     P("Steel bar 12mm", "Materials", 32, stock=80)],
}
