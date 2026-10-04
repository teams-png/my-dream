"""
Kerala restaurant starter menu — the dishes a typical Kerala / Malabar restaurant in the Gulf or Kerala sells.
Prices are in QAR; other currencies use CURRENCY_FACTORS. Each dish has an illustration in
static/restaurant/kerala/<code>.png (made by `manage.py make_kerala_menu_art`).

Row: (code, name, malayalam, price_qar, description, vegetarian, spice, prep_minutes, featured, art, colour)
art is the illustration style: rice, curry, fry, bread, dosa, meals, fish, glass, cup, dessert, snack, roll, grill
"""

CATEGORIES = [
    # (name, kitchen station)
    ("Breakfast", "Breakfast & breads"),
    ("Breads", "Breakfast & breads"),
    ("Kerala Meals", "Main kitchen"),
    ("Biryani & Rice", "Main kitchen"),
    ("Chicken", "Main kitchen"),
    ("Beef", "Main kitchen"),
    ("Mutton", "Main kitchen"),
    ("Fish & Seafood", "Main kitchen"),
    ("Egg", "Main kitchen"),
    ("Vegetarian", "Main kitchen"),
    ("Kappa Specials", "Main kitchen"),
    ("Grill & Shawarma", "Grill & shawarma"),
    ("Nadan Snacks", "Tea & juice counter"),
    ("Tea & Coffee", "Tea & juice counter"),
    ("Juices & Shakes", "Tea & juice counter"),
    ("Desserts & Payasam", "Tea & juice counter"),
]

STATIONS = {"Main kitchen": "#dc2626", "Breakfast & breads": "#d97706", "Grill & shawarma": "#7c3aed",
            "Tea & juice counter": "#0891b2"}

# A café / juice shop gets only these sections.
CAFE_CATEGORIES = {"Breakfast", "Breads", "Nadan Snacks", "Tea & Coffee", "Juices & Shakes", "Desserts & Payasam",
                   "Grill & Shawarma"}

CURRENCY_FACTORS = {"QAR": 1, "AED": 1, "SAR": 1, "INR": 10, "OMR": 0.1, "BHD": 0.1, "KWD": 0.085, "USD": 0.275,
                    "GBP": 0.22, "EUR": 0.25}

DISHES = {
    "Breakfast": [
        ("puttu-kadala", "Puttu & Kadala Curry", "പുട്ട് & കടല", 8, "Steamed rice puttu with black chickpea curry.", True, "medium", 10, True, "breakfast", "#f5f0e6"),
        ("appam-egg-roast", "Appam & Egg Roast", "അപ്പം & മുട്ട റോസ്റ്റ്", 9, "Two lacy appams with spicy egg roast.", False, "medium", 12, True, "breakfast", "#f3e3c3"),
        ("appam-chicken-stew", "Appam & Chicken Stew", "അപ്പം & ചിക്കൻ സ്റ്റൂ", 12, "Two appams with mild coconut-milk chicken stew.", False, "mild", 12, False, "breakfast", "#f6ecd9"),
        ("idiyappam-egg-curry", "Idiyappam & Egg Curry", "ഇടിയപ്പം & മുട്ടക്കറി", 9, "String hoppers with Kerala egg curry.", False, "medium", 12, False, "breakfast", "#f7f3ea"),
        ("plain-dosa", "Plain Dosa", "ദോശ", 5, "Crisp rice-and-lentil dosa with chutney and sambar.", True, "mild", 8, False, "dosa", "#e8b866"),
        ("masala-dosa", "Masala Dosa", "മസാല ദോശ", 7, "Dosa filled with spiced potato masala.", True, "mild", 10, True, "dosa", "#e2a94e"),
        ("ghee-roast-dosa", "Ghee Roast Dosa", "നെയ്റോസ്റ്റ്", 8, "Paper-thin dosa roasted in pure ghee.", True, "none", 10, False, "dosa", "#d9973a"),
        ("idli-sambar", "Idli Sambar (3 pcs)", "ഇഡ്ഡലി സാമ്പാർ", 5, "Soft steamed idlis with sambar and coconut chutney.", True, "mild", 8, False, "breakfast", "#fafaf5"),
        ("uzhunnu-vada", "Uzhunnu Vada (2 pcs)", "ഉഴുന്നു വട", 3, "Crispy urad dal vada with chutney.", True, "mild", 8, False, "snack", "#c8873a"),
        ("upma", "Rava Upma", "ഉപ്പുമാവ്", 5, "Semolina upma with banana and pappadam.", True, "mild", 8, False, "breakfast", "#efe0b0"),
        ("pathiri-chicken", "Pathiri & Chicken Curry", "പത്തിരി & ചിക്കൻ കറി", 12, "Malabar rice pathiri with chicken curry.", False, "medium", 12, False, "bread", "#f7f1e3"),
        ("poori-masala", "Poori Masala", "പൂരി മസാല", 7, "Puffed pooris with potato masala.", True, "mild", 10, False, "bread", "#e7b462"),
    ],
    "Breads": [
        ("kerala-porotta", "Kerala Porotta", "പൊറോട്ട", 1.5, "Flaky layered Malabar porotta.", True, "none", 5, True, "bread", "#e9c27a"),
        ("wheat-porotta", "Wheat Porotta", "ഗോതമ്പ് പൊറോട്ട", 2, "Layered porotta made with whole wheat.", True, "none", 5, False, "bread", "#c99a5a"),
        ("chapathi", "Chapathi", "ചപ്പാത്തി", 1, "Soft whole-wheat chapathi.", True, "none", 4, False, "bread", "#d8b27a"),
        ("appam", "Appam", "അപ്പം", 1.5, "Lacy fermented rice hopper.", True, "none", 5, False, "bread", "#f5ead2"),
        ("idiyappam", "Idiyappam (3 pcs)", "ഇടിയപ്പം", 3, "Steamed rice string hoppers.", True, "none", 6, False, "bread", "#f8f5ee"),
        ("pathiri", "Pathiri (3 pcs)", "പത്തിരി", 3, "Thin Malabar rice pathiri.", True, "none", 6, False, "bread", "#f6f0e2"),
        ("neypathiri", "Neypathiri (3 pcs)", "നെയ്പത്തിരി", 4, "Deep-fried rice pathiri with fennel and shallots.", True, "none", 8, False, "bread", "#e3b765"),
        ("kappa-boiled", "Boiled Kappa", "കപ്പ പുഴുങ്ങിയത്", 5, "Boiled tapioca with chilli-shallot chammanthi.", True, "medium", 8, False, "fry", "#f2e6b8"),
    ],
    "Kerala Meals": [
        ("veg-meals", "Kerala Veg Meals", "ഊണ്", 12, "Matta rice, sambar, rasam, avial, thoran, pickle, pappadam & payasam.", True, "mild", 8, True, "meals", "#c27c48"),
        ("fish-curry-meals", "Fish Curry Meals", "മീൻ കറി ഊണ്", 18, "Kerala meals with kudampuli fish curry and fish fry.", False, "medium", 10, True, "meals", "#b85a2e"),
        ("chicken-curry-meals", "Chicken Curry Meals", "ചിക്കൻ കറി ഊണ്", 17, "Kerala meals with nadan chicken curry.", False, "medium", 10, False, "meals", "#a7542a"),
        ("beef-curry-meals", "Beef Curry Meals", "ബീഫ് കറി ഊണ്", 17, "Kerala meals with beef curry.", False, "medium", 10, False, "meals", "#7a3b1e"),
        ("mini-meals", "Mini Meals", "മിനി ഊണ്", 9, "Smaller portion of rice with sambar, thoran and pickle.", True, "mild", 6, False, "meals", "#cf9257"),
        ("kanji-payar", "Kanji & Payar", "കഞ്ഞി & പയർ", 7, "Rice porridge with green gram, pickle and pappadam.", True, "none", 8, False, "curry", "#efe8d8"),
        ("onam-sadya", "Kerala Sadya (Special)", "സദ്യ", 35, "Banana-leaf feast with 20+ dishes and two payasams. Pre-order.", True, "mild", 20, True, "meals", "#d4a017"),
    ],
    "Biryani & Rice": [
        ("thalassery-chicken-biryani", "Thalassery Chicken Biryani", "തലശ്ശേരി ചിക്കൻ ബിരിയാണി", 18, "Kaima rice dum biryani with chicken, fried onions and cashews.", False, "medium", 15, True, "rice", "#e9b949"),
        ("malabar-mutton-biryani", "Malabar Mutton Biryani", "മട്ടൻ ബിരിയാണി", 25, "Slow-cooked mutton dum biryani, Malabar style.", False, "medium", 18, True, "rice", "#d9a43c"),
        ("beef-biryani", "Beef Biryani", "ബീഫ് ബിരിയാണി", 17, "Fragrant kaima rice with spiced beef.", False, "medium", 15, False, "rice", "#c98c34"),
        ("fish-biryani", "Fish Biryani", "മീൻ ബിരിയാണി", 20, "Biryani with masala-fried kingfish.", False, "medium", 15, False, "rice", "#e0b04a"),
        ("prawns-biryani", "Prawns Biryani", "ചെമ്മീൻ ബിരിയാണി", 24, "Biryani with roasted prawns.", False, "medium", 15, False, "rice", "#e7a54b"),
        ("egg-biryani", "Egg Biryani", "മുട്ട ബിരിയാണി", 12, "Biryani rice with masala boiled eggs.", False, "mild", 12, False, "rice", "#efc45a"),
        ("veg-biryani", "Vegetable Biryani", "വെജ് ബിരിയാണി", 12, "Kaima rice with mixed vegetables and ghee.", True, "mild", 12, False, "rice", "#e8c35f"),
        ("ghee-rice", "Ghee Rice", "നെയ്ച്ചോറ്", 8, "Kaima rice cooked in ghee with fried onions.", True, "none", 8, False, "rice", "#f2d77e"),
        ("chicken-fried-rice", "Chicken Fried Rice", "ചിക്കൻ ഫ്രൈഡ് റൈസ്", 15, "Indo-Chinese fried rice with chicken.", False, "mild", 12, False, "rice", "#e6cf8a"),
        ("kuzhimanthi-chicken", "Kuzhimanthi Chicken", "കുഴിമന്തി", 22, "Smoky Arabic-style rice with tender chicken.", False, "none", 15, True, "rice", "#e4b36a"),
    ],
    "Chicken": [
        ("nadan-chicken-curry", "Nadan Chicken Curry", "നാടൻ ചിക്കൻ കറി", 14, "Village-style chicken curry with roasted coconut.", False, "hot", 15, True, "curry", "#9c3a16"),
        ("chicken-roast", "Kerala Chicken Roast", "ചിക്കൻ റോസ്റ്റ്", 16, "Chicken slow-roasted with onions and spices.", False, "hot", 15, False, "fry", "#8f2f14"),
        ("chicken-pepper-fry", "Chicken Pepper Fry", "ചിക്കൻ കുരുമുളക് ഫ്രൈ", 16, "Dry chicken fry with crushed black pepper.", False, "hot", 15, False, "fry", "#5e3217"),
        ("chicken-65", "Chicken 65", "ചിക്കൻ 65", 15, "Crispy spiced fried chicken bites.", False, "hot", 12, True, "fry", "#c0391b"),
        ("chicken-varutharachathu", "Chicken Varutharachathu", "ചിക്കൻ വറുത്തരച്ചത്", 16, "Chicken in roasted-coconut gravy.", False, "medium", 15, False, "curry", "#7d3315"),
        ("chilli-chicken", "Chilli Chicken", "ചില്ലി ചിക്കൻ", 16, "Indo-Chinese chicken with capsicum and chilli.", False, "hot", 12, False, "fry", "#a82f1c"),
        ("chicken-ularthiyathu", "Chicken Ularthiyathu", "ചിക്കൻ ഉലർത്തിയത്", 16, "Chicken tossed dry with coconut slices and curry leaves.", False, "hot", 15, False, "fry", "#6e2c12"),
        ("butter-chicken", "Butter Chicken", "ബട്ടർ ചിക്കൻ", 18, "Creamy tomato-butter chicken curry.", False, "mild", 15, False, "curry", "#e07a3a"),
    ],
    "Beef": [
        ("beef-ularthiyathu", "Beef Ularthiyathu (Beef Fry)", "ബീഫ് ഉലർത്തിയത്", 16, "Kerala's famous dry beef fry with coconut slices.", False, "hot", 15, True, "fry", "#4a2412"),
        ("beef-curry", "Beef Curry", "ബീഫ് കറി", 15, "Beef in thick spicy Kerala gravy.", False, "hot", 15, False, "curry", "#5c2a14"),
        ("beef-roast", "Beef Roast", "ബീഫ് റോസ്റ്റ്", 16, "Beef slow-roasted with onions and pepper.", False, "hot", 15, False, "fry", "#552612"),
        ("beef-chilli", "Beef Chilli", "ബീഫ് ചില്ലി", 17, "Crispy beef strips in chilli sauce.", False, "hot", 12, False, "fry", "#7a2a18"),
        ("beef-pepper-fry", "Beef Pepper Fry", "ബീഫ് കുരുമുളക് ഫ്രൈ", 17, "Beef fried with crushed black pepper.", False, "hot", 15, False, "fry", "#3d2010"),
    ],
    "Mutton": [
        ("mutton-curry", "Mutton Curry", "മട്ടൻ കറി", 22, "Tender mutton in Kerala spices.", False, "hot", 18, False, "curry", "#7a3014"),
        ("mutton-roast", "Mutton Roast", "മട്ടൻ റോസ്റ്റ്", 24, "Dry-roasted mutton with onions.", False, "hot", 18, True, "fry", "#5e2812"),
        ("mutton-stew", "Mutton Stew", "മട്ടൻ സ്റ്റൂ", 22, "Mild coconut-milk stew with mutton and vegetables.", False, "mild", 18, False, "curry", "#efe2c4"),
        ("mutton-pepper-fry", "Mutton Pepper Fry", "മട്ടൻ കുരുമുളക് ഫ്രൈ", 24, "Mutton fried with black pepper and curry leaves.", False, "hot", 18, False, "fry", "#43230f"),
    ],
    "Fish & Seafood": [
        ("kudampuli-fish-curry", "Kudampuli Fish Curry", "മീൻ കറി", 15, "Red fish curry with kudampuli (Malabar tamarind).", False, "hot", 15, True, "curry", "#b2301a"),
        ("fish-molee", "Fish Molee", "മീൻ മോളി", 18, "Kingfish in mild coconut-milk gravy.", False, "mild", 15, False, "curry", "#f0d58c"),
        ("karimeen-pollichathu", "Karimeen Pollichathu", "കരിമീൻ പൊള്ളിച്ചത്", 30, "Pearl spot fish masala-grilled in banana leaf.", False, "medium", 20, True, "fish", "#3f6b2a"),
        ("ayala-fry", "Ayala Fry (Mackerel)", "അയല വറുത്തത്", 10, "Whole mackerel fried in red masala.", False, "hot", 12, False, "fish", "#b5481f"),
        ("neymeen-fry", "Neymeen Fry (Kingfish)", "നെയ്മീൻ ഫ്രൈ", 25, "Kingfish steak fried in Kerala masala.", False, "hot", 12, True, "fish", "#a8401d"),
        ("mathi-fry", "Mathi Fry (Sardine)", "മത്തി ഫ്രൈ", 10, "Crispy fried sardines.", False, "hot", 10, False, "fish", "#9c3e1c"),
        ("prawns-roast", "Prawns Roast", "ചെമ്മീൻ റോസ്റ്റ്", 24, "Prawns roasted with onions and spices.", False, "hot", 15, True, "fry", "#d2502a"),
        ("prawns-curry", "Prawns Curry", "ചെമ്മീൻ കറി", 22, "Prawns in coconut gravy.", False, "medium", 15, False, "curry", "#e07434"),
        ("koonthal-roast", "Koonthal Roast (Squid)", "കൂന്തൽ റോസ്റ്റ്", 22, "Squid rings roasted Kerala style.", False, "hot", 15, False, "fry", "#a0451e"),
        ("crab-roast", "Crab Roast", "ഞണ്ട് റോസ്റ്റ്", 28, "Whole crab roasted in thick masala.", False, "hot", 20, False, "fry", "#c2421c"),
        ("kallumakkaya-fry", "Kallumakkaya Fry (Mussels)", "കല്ലുമ്മക്കായ ഫ്രൈ", 20, "Malabar mussels fried with masala.", False, "hot", 15, False, "fry", "#7b3a1a"),
    ],
    "Egg": [
        ("egg-roast", "Egg Roast", "മുട്ട റോസ്റ്റ്", 7, "Boiled eggs in spicy onion roast.", False, "medium", 10, False, "curry", "#b2541f"),
        ("egg-curry", "Egg Curry", "മുട്ടക്കറി", 7, "Eggs in coconut-milk curry.", False, "mild", 10, False, "curry", "#d9903c"),
        ("omelette", "Omelette", "ഓംലെറ്റ്", 4, "Onion-chilli omelette.", False, "mild", 5, False, "fry", "#f2c14e"),
        ("bulls-eye", "Bulls Eye", "ബുൾസ് ഐ", 3, "Sunny-side-up egg with pepper.", False, "none", 5, False, "fry", "#f5d36b"),
        ("egg-burji", "Egg Burji", "മുട്ട ബുർജി", 6, "Spiced scrambled eggs.", False, "mild", 6, False, "fry", "#e8b84a"),
    ],
    "Vegetarian": [
        ("kadala-curry", "Kadala Curry", "കടലക്കറി", 6, "Black chickpeas in roasted-coconut gravy.", True, "medium", 8, False, "curry", "#6b3a1a"),
        ("sambar", "Sambar", "സാമ്പാർ", 5, "Lentil and vegetable sambar.", True, "mild", 6, False, "curry", "#c8752a"),
        ("avial", "Avial", "അവിയൽ", 8, "Mixed vegetables in coconut and curd.", True, "none", 8, False, "curry", "#e9dc9a"),
        ("cabbage-thoran", "Cabbage Thoran", "കാബേജ് തോരൻ", 6, "Cabbage stir-fried with grated coconut.", True, "none", 6, False, "fry", "#cfe3a0"),
        ("veg-stew", "Vegetable Stew", "വെജിറ്റബിൾ സ്റ്റൂ", 8, "Mild coconut-milk stew with vegetables.", True, "mild", 8, False, "curry", "#f2ead2"),
        ("veg-kurma", "Vegetable Kurma", "വെജ് കുറുമ", 9, "Vegetables in creamy kurma gravy.", True, "mild", 10, False, "curry", "#e7c77d"),
        ("parippu-curry", "Parippu Curry (Dal)", "പരിപ്പ് കറി", 6, "Moong dal with ghee and coconut.", True, "none", 6, False, "curry", "#e9c24d"),
        ("mushroom-roast", "Mushroom Roast", "കൂൺ റോസ്റ്റ്", 12, "Mushrooms roasted with onions and spices.", True, "medium", 12, False, "fry", "#7d5636"),
        ("paneer-butter-masala", "Paneer Butter Masala", "പനീർ ബട്ടർ മസാല", 16, "Paneer cubes in rich tomato-butter gravy.", True, "mild", 12, False, "curry", "#e37b3a"),
        ("gobi-manchurian", "Gobi Manchurian", "ഗോബി മഞ്ചൂരിയൻ", 14, "Crispy cauliflower in Manchurian sauce.", True, "medium", 12, False, "fry", "#9c3d22"),
        ("moru-curry", "Moru Curry", "മോരു കറി", 5, "Spiced yoghurt curry with turmeric.", True, "none", 6, False, "curry", "#f1d65a"),
    ],
    "Kappa Specials": [
        ("kappa-fish-curry", "Kappa & Fish Curry", "കപ്പയും മീൻകറിയും", 15, "Mashed tapioca with red fish curry — a Kerala classic.", False, "hot", 12, True, "meals", "#d9c06a"),
        ("kappa-biryani", "Kappa Biryani", "കപ്പ ബിരിയാണി", 18, "Tapioca cooked with beef and spices.", False, "hot", 15, False, "rice", "#b8873e"),
        ("kappa-puzhukku", "Kappa Puzhukku", "കപ്പ പുഴുക്ക്", 8, "Tapioca mashed with coconut and green chillies.", True, "mild", 10, False, "curry", "#efe0a0"),
        ("kappa-beef", "Kappa & Beef Fry", "കപ്പയും ബീഫും", 18, "Tapioca with beef ularthiyathu.", False, "hot", 15, False, "meals", "#7a4a22"),
    ],
    "Grill & Shawarma": [
        ("alfaham-half", "Alfaham Chicken (Half)", "അൽഫാം", 22, "Charcoal-grilled spiced chicken with mayonnaise and khubz.", False, "medium", 25, True, "grill", "#a3461c"),
        ("shawaya-half", "Shawaya Chicken (Half)", "ഷവായ", 18, "Rotisserie chicken with garlic sauce and fries.", False, "mild", 20, False, "grill", "#c76a28"),
        ("chicken-shawarma-roll", "Chicken Shawarma Roll", "ഷവർമ", 6, "Shawarma chicken, garlic sauce and pickles in khubz.", False, "mild", 6, True, "roll", "#e1b46a"),
        ("shawarma-plate", "Shawarma Plate", "ഷവർമ പ്ലേറ്റ്", 15, "Shawarma chicken with fries, salad and khubz.", False, "mild", 10, False, "grill", "#d79a52"),
    ],
    "Nadan Snacks": [
        ("pazham-pori", "Pazham Pori", "പഴംപൊരി", 2, "Ripe banana fritters.", True, "none", 5, True, "snack", "#e8a83a"),
        ("unniyappam", "Unniyappam (5 pcs)", "ഉണ്ണിയപ്പം", 5, "Sweet rice-jaggery-banana fritters.", True, "none", 5, False, "snack", "#7a4a1e"),
        ("parippu-vada", "Parippu Vada", "പരിപ്പുവട", 1.5, "Crunchy lentil fritter.", True, "mild", 5, False, "snack", "#c0812f"),
        ("sukhiyan", "Sukhiyan", "സുഖിയൻ", 1.5, "Sweet green-gram balls in crisp batter.", True, "none", 5, False, "snack", "#b9792c"),
        ("egg-puffs", "Egg Puffs", "മുട്ട പഫ്സ്", 3, "Flaky puff with half egg and masala.", False, "mild", 5, False, "snack", "#e7b65a"),
        ("chicken-puffs", "Chicken Puffs", "ചിക്കൻ പഫ്സ്", 4, "Flaky puff with chicken masala.", False, "mild", 5, False, "snack", "#ddaa52"),
        ("samosa", "Samosa", "സമൂസ", 1.5, "Crispy samosa with spiced filling.", True, "mild", 5, False, "snack", "#d29a45"),
        ("beef-cutlet", "Beef Cutlet", "ബീഫ് കട്ലറ്റ്", 2.5, "Crumb-fried beef and potato cutlet.", False, "mild", 6, False, "snack", "#8c5428"),
        ("chicken-roll", "Chicken Roll", "ചിക്കൻ റോൾ", 6, "Chicken filling rolled in a crispy wrap.", False, "mild", 8, False, "roll", "#d9a057"),
        ("banana-chips", "Banana Chips (250 g)", "കായ ഉപ്പേരി", 8, "Kerala banana chips fried in coconut oil.", True, "none", 1, False, "snack", "#f0cf4a"),
    ],
    "Tea & Coffee": [
        ("chaya", "Chaya (Kerala Tea)", "ചായ", 1.5, "Strong milk tea, pulled the Kerala way.", True, "none", 3, True, "cup", "#c79a6a"),
        ("sulaimani", "Sulaimani", "സുലൈമാനി", 1.5, "Black tea with lemon and spices.", True, "none", 3, False, "cup", "#b5651d"),
        ("karak-chai", "Karak Chai", "കരക്ക് ചായ", 2, "Thick cardamom-saffron milk tea.", True, "none", 4, False, "cup", "#b07a4a"),
        ("kattan-kaapi", "Kattan Kaapi", "കട്ടൻ കാപ്പി", 1.5, "Black coffee with jaggery.", True, "none", 3, False, "cup", "#3e2412"),
        ("filter-coffee", "Filter Coffee", "ഫിൽറ്റർ കോഫി", 3, "South Indian filter coffee.", True, "none", 4, False, "cup", "#8a5a34"),
        ("ginger-tea", "Ginger Tea", "ഇഞ്ചി ചായ", 2, "Milk tea with fresh ginger.", True, "none", 4, False, "cup", "#c9a074"),
        ("boost-horlicks", "Boost / Horlicks", "ബൂസ്റ്റ് / ഹോർലിക്സ്", 4, "Hot malted milk drink.", True, "none", 3, False, "cup", "#8b5a3c"),
    ],
    "Juices & Shakes": [
        ("lime-juice", "Fresh Lime Juice", "നാരങ്ങ വെള്ളം", 6, "Fresh lime with sugar or salt.", True, "none", 3, False, "glass", "#d8ec7a"),
        ("lime-mint", "Lime Mint", "ലൈം മിന്റ്", 8, "Lime blended with fresh mint.", True, "none", 3, False, "glass", "#9fd36a"),
        ("avil-milk", "Avil Milk", "അവിൽ മിൽക്ക്", 12, "Malabar special: banana, beaten rice, milk and nuts.", True, "none", 5, True, "glass", "#ead8b8"),
        ("sharjah-shake", "Sharjah Shake", "ഷാർജ ഷേക്ക്", 12, "Banana, chilled milk, Boost and nuts.", True, "none", 4, True, "glass", "#b98a5e"),
        ("mango-lassi", "Mango Lassi", "മാംഗോ ലസ്സി", 10, "Mango and yoghurt drink.", True, "none", 3, False, "glass", "#f6b73c"),
        ("sweet-lassi", "Sweet Lassi", "ലസ്സി", 8, "Chilled sweet yoghurt drink.", True, "none", 3, False, "glass", "#f5f0e1"),
        ("watermelon-juice", "Watermelon Juice", "തണ്ണിമത്തൻ ജ്യൂസ്", 10, "Fresh watermelon juice.", True, "none", 3, False, "glass", "#ef4b5a"),
        ("orange-juice", "Fresh Orange Juice", "ഓറഞ്ച് ജ്യൂസ്", 12, "Freshly squeezed orange.", True, "none", 3, False, "glass", "#f7941d"),
        ("kulukki-sarbath", "Kulukki Sarbath", "കുലുക്കി സർബത്ത്", 8, "Shaken lime-basil seed sarbath with green chilli.", True, "mild", 3, True, "glass", "#c9e265"),
        ("tender-coconut", "Tender Coconut Water", "ഇളനീർ", 10, "Fresh tender coconut water.", True, "none", 2, False, "glass", "#eef5d8"),
        ("sambaram", "Sambaram (Buttermilk)", "സംഭാരം", 4, "Spiced buttermilk with ginger and curry leaves.", True, "none", 2, False, "glass", "#f3f2e6"),
        ("falooda", "Falooda", "ഫലൂദ", 15, "Rose milk, vermicelli, basil seeds, jelly and ice cream.", True, "none", 6, True, "glass", "#f2a7c3"),
    ],
    "Desserts & Payasam": [
        ("palada-payasam", "Palada Payasam", "പാലട പ്രഥമൻ", 8, "Rice ada slow-cooked in milk.", True, "none", 3, True, "dessert", "#f3dfc4"),
        ("semiya-payasam", "Semiya Payasam", "സേമിയ പായസം", 6, "Vermicelli in sweet milk with cashews and raisins.", True, "none", 3, False, "dessert", "#f0e1c8"),
        ("ada-pradhaman", "Ada Pradhaman", "അട പ്രഥമൻ", 8, "Rice ada in jaggery and coconut milk.", True, "none", 3, False, "dessert", "#8a5a2c"),
        ("pal-payasam", "Pal Payasam", "പാൽ പായസം", 8, "Rice and milk payasam, temple style.", True, "none", 3, False, "dessert", "#f4e6d0"),
        ("caramel-pudding", "Caramel Pudding", "കാരമൽ പുഡ്ഡിംഗ്", 8, "Soft egg caramel pudding.", False, "none", 2, False, "dessert", "#d9922e"),
        ("gulab-jamun", "Gulab Jamun (2 pcs)", "ഗുലാബ് ജാമുൻ", 6, "Warm milk dumplings in sugar syrup.", True, "none", 2, False, "dessert", "#8c3a1a"),
        ("tender-coconut-pudding", "Tender Coconut Pudding", "ഇളനീർ പുഡ്ഡിംഗ്", 10, "Chilled pudding with tender coconut.", True, "none", 2, False, "dessert", "#f6f2e4"),
        ("vanilla-ice-cream", "Vanilla Ice Cream", "ഐസ് ക്രീം", 6, "Two scoops of vanilla ice cream.", True, "none", 1, False, "dessert", "#fbf3dc"),
    ],
}

# Sample staff (name, role, department, salary in QAR, shift)
STAFF = [
    ("Rajesh Kumar", "Head chef", "Kitchen", 3500, "Morning"),
    ("Shameer P.", "Porotta & tandoor master", "Kitchen", 2800, "Evening"),
    ("Biju Thomas", "Cook", "Kitchen", 2200, "Morning"),
    ("Anil Das", "Kitchen helper", "Kitchen", 1400, "Evening"),
    ("Faisal K.", "Captain / head waiter", "Service", 2000, "Evening"),
    ("Arun Mohan", "Waiter", "Service", 1500, "Morning"),
    ("Joseph Varghese", "Waiter", "Service", 1500, "Evening"),
    ("Nisha Joseph", "Cashier", "Front office", 2200, "Morning"),
    ("Rashid Ali", "Delivery driver", "Delivery", 1800, "Evening"),
    ("Sunil Kumar", "Cleaner", "Service", 1200, "Morning"),
]

SHIFTS = [("Morning", "06:00", "15:00"), ("Evening", "15:00", "23:59")]

# Sample expenses (category, description, amount in QAR, day of last month)
EXPENSES = [
    ("Rent", "Shop rent", 12000, 1),
    ("Electricity", "Kahramaa electricity bill", 1800, 5),
    ("Water", "Kahramaa water bill", 400, 5),
    ("Internet", "Ooredoo internet", 300, 6),
    ("Gas", "LPG gas cylinders", 1500, 8),
    ("Kitchen supplies", "Parcel boxes, foil and tissues", 900, 10),
    ("Marketing", "Instagram & Talabat promotion", 500, 12),
    ("Maintenance", "Kitchen exhaust cleaning", 350, 18),
    ("Transportation", "Delivery bike fuel", 600, 25),
]

TABLES = [("Family hall", "F", 6, 4), ("Main hall", "T", 8, 4), ("Outdoor", "O", 4, 2)]

MODIFIERS = {
    "Spice level": {"required": False, "max": 1, "options": [("Less spicy", 0), ("Medium spicy", 0), ("Extra spicy", 0)],
                    "categories": {"Chicken", "Beef", "Mutton", "Fish & Seafood", "Biryani & Rice", "Kappa Specials"}},
    "Extras": {"required": False, "max": 4, "options": [("Extra porotta", 1.5), ("Extra gravy", 2), ("Boiled egg", 2),
                                                         ("Pappadam", 0.5), ("Raita", 1)],
               "categories": {"Kerala Meals", "Biryani & Rice", "Chicken", "Beef", "Mutton"}},
    "Sugar": {"required": False, "max": 1, "options": [("Less sugar", 0), ("No sugar", 0), ("Extra sugar", 0)],
              "categories": {"Tea & Coffee", "Juices & Shakes"}},
}
