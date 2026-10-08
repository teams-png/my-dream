"""Default pictures for products and services that have no photo of their own.

Every item gets a picture: its uploaded photo, or a ready illustration picked from its name, then its category,
then the business type. The illustrations are WebP images in static/products/ (made by `manage.py make_product_art`).
"""
import re
from functools import lru_cache
from pathlib import Path

from django.templatetags.static import static

# (key, emoji, words that point to it — matched against the item's name, then its category)
ART = [
    # salon, beauty, spa
    ("haircut", "✂️", "haircut haircuts barber"), ("beard", "🧔", "beard shave moustache trim"),
    ("hair_colour", "🎨", "hair_colour colour color dye highlight"), ("hair_care", "🧴", "shampoo serum conditioner hair oil lotion wax gel spa"),
    ("massage", "💆", "massage reflexology therapy head_massage"), ("facial", "🧖", "facial face mask skin peel"),
    ("nails", "💅", "manicure pedicure nail nails polish"), ("makeup", "💄", "makeup bridal lipstick foundation cosmetic"),
    ("threading", "🪡", "threading eyebrow waxing"), ("bath", "🛁", "bath moroccan sauna steam"),
    ("candle", "🕯️", "candle aroma"), ("stone", "🪨", "hot_stone"),
    ("perfume", "🌸", "perfume attar oud musk fragrance bakhoor rose"),
    # fashion
    ("shirt", "👔", "shirt formal kandura thobe coverall"), ("tshirt", "👕", "t-shirt tshirt jersey tee top"),
    ("dress", "👗", "dress gown kurti abaya frock boutique party_gown"), ("saree", "🥻", "saree sari silk"),
    ("trousers", "👖", "pant pants jeans trouser"), ("kids_wear", "🧸", "romper kids wear baby"),
    ("shoes", "👟", "shoe shoes sneaker running footwear shoe_polish"), ("sandals", "👡", "sandal sandals heels slipper"),
    ("bag", "👜", "bag clutch handbag wallet"), ("scarf", "🧣", "scarf shawl hijab"), ("belt", "🪢", "belt tie"),
    ("fabric", "🧵", "fabric cloth suiting shirting churidar stitching tailoring alteration blouse"),
    ("cap", "🧢", "cap hat"), ("glasses", "👓", "frame glasses spectacles lens lenses eye test optical"),
    ("sunglasses", "🕶️", "sunglasses aviator"), ("watch", "⌚", "watch chronograph strap smart_watch dress_watch"),
    ("ring", "💍", "ring diamond"), ("jewel", "📿", "bangle chain necklace gold jewellery jewelry earring"),
    # electronics
    ("phone", "📱", "phone mobile iphone galaxy samsung redmi smartphone handset"), ("charger", "🔌", "charger cable hdmi adapter port plug"),
    ("headphones", "🎧", "earbuds headphones earphone audio"), ("speaker", "🔊", "speaker sound"),
    ("laptop", "💻", "laptop computer pc windows laptop_cleaning"), ("monitor", "🖥️", "monitor tv television screen led"),
    ("mouse", "🖱️", "mouse keyboard"), ("battery", "🔋", "battery powerbank power_bank"), ("storage", "💾", "ssd storage drive memory"),
    ("camera", "📷", "camera photo photos passport photoshoot photography cctv wedding_coverage"), ("printer", "🖨️", "print printing printer banner flex lamination cards colour_print"),
    ("glass_guard", "🛡️", "tempered glass screen guard cover case"), ("repair", "🛠️", "repair service diagnosis fix labour board inspection screen_replacement"),
    ("ac", "❄️", "ac conditioner cooling gas_refill ac_service"), ("washing", "🧺", "washing laundry iron dry_clean blanket washing_machine"),
    ("microwave", "📦", "microwave oven fryer appliance"),
    # food & grocery
    ("milk", "🥛", "milk dairy yogurt laban"), ("bread", "🍞", "bread bun loaf"), ("cake", "🎂", "cake"),
    ("croissant", "🥐", "croissant pastry puff"), ("cookies", "🍪", "cookies biscuit"), ("rice", "🍚", "rice basmati grain"),
    ("oil", "🫒", "oil olive sunflower ghee"), ("sugar", "🧂", "sugar salt spice masala"), ("tea", "🍵", "tea coffee"),
    ("banana", "🍌", "banana"), ("apple", "🍎", "apple fruit fruits"), ("tomato", "🍅", "tomato vegetables vegetable"),
    ("onion", "🧅", "onion garlic"), ("fish", "🐟", "fish kingfish seafood prawn"), ("chicken", "🍗", "chicken poultry"),
    ("meat", "🥩", "mutton beef meat lamb cutting"), ("water", "💧", "water drinks drink juice"),
    ("cleaning", "🧽", "dish wash cleaning detergent household soap sanitiser sanitizer hygiene deep cleaning"),
    ("protein", "💪", "protein whey creatine supplement supplements shaker"),
    # health
    ("medicine", "💊", "tablet tablets medicine paracetamol capsule vitamins vitamin pain relief refill"),
    ("syrup", "🧪", "syrup cough lab test cbc lipid hba1c biochemistry haematology"), ("thermometer", "🌡️", "thermometer oximeter blood_pressure blood_test"),
    ("doctor", "🩺", "consultation doctor clinic specialist assessment physiotherapy nurse nursing dressing elderly"), ("tooth", "🦷", "tooth teeth dental scaling filling root canal"),
    ("wheelchair", "🦽", "wheelchair mobility"), ("pet", "🐾", "pet dog cat collar grooming vaccination veterinary"),
    # sports & fitness
    ("gym", "🏋️", "gym dumbbell weights membership personal training workout fitness"), ("football", "⚽", "football soccer"),
    ("cricket", "🏏", "cricket bat"), ("badminton", "🏸", "badminton racket shuttle"), ("bicycle", "🚲", "bicycle bike cycle tube"),
    ("helmet", "⛑️", "helmet"), ("pass", "🎟️", "pass day_pass"), ("gloves", "🧤", "gloves"),
    # home, hardware, auto
    ("paint", "🖌️", "paint jotun brush"), ("drill", "🔩", "drill screw screws fasteners bolt tools tool"), ("tape", "📏", "tape measure"),
    ("bulb", "💡", "bulb led light lighting electrician"), ("wire", "🧶", "wire cable copper"), ("pipe", "🚰", "pipe tap plumbing plumber water_tap"),
    ("cement", "🧱", "cement brick steel tile tiles metal sheet"), ("sofa", "🛋️", "sofa couch furniture"),
    ("table", "🪑", "table chair dining cabinet"), ("pan", "🍳", "pan cookware cooker kitchenware pressure_cooker dinner_set"),
    ("car", "🚗", "car toyota nissan sedan suv vehicle wash detail seat car_wash"), ("tyre", "🛞", "tyre tire wheel alignment balancing"),
    ("brake", "⚙️", "brake pads filter spare_part hydraulic"), ("fuel", "⛽", "petrol diesel fuel"), ("motor_oil", "🛢️", "lubricant engine_oil oil_change"),
    ("wiper", "🌧️", "wiper"), ("air_freshener", "🌿", "air freshener plant plants orchid garden lawn landscaping"),
    ("flowers", "💐", "bouquet flowers roses flower"), ("gift", "🎁", "gift wrap wrapping greeting toys toy"),
    ("teddy", "🧸", "teddy soft toy"), ("blocks", "🧩", "blocks lego puzzle"), ("diaper", "🍼", "diaper diapers baby_lotion"),
    ("book", "📕", "book dictionary novel alchemist"), ("notebook", "📓", "notebook pen pens stationery paper ream"),
    ("guitar", "🎸", "guitar strings"), ("keyboard_music", "🎹", "keyboard piano"), ("seeds", "🌱", "seeds fertiliser fertilizer npk agriculture hose"),
    # services, bookings, education, projects
    ("room", "🛏️", "room suite hotel deluxe twin bed stay"), ("hall", "🏛️", "hall ballroom wedding banquet"),
    ("desk", "🧑‍💻", "desk co-working coworking meeting"), ("equipment", "🏗️", "lift mixer equipment scissor construction site survey mason operator"),
    ("food_service", "🍽️", "breakfast buffet catering"), ("transport", "🚚", "pickup delivery truck trip transport moving move courier logistics packing"),
    ("plane", "✈️", "ticket visa holiday travel air_ticket"), ("document", "📄", "document attestation contract drafting legal law paperwork registration legal_consultation"),
    ("insurance", "🛡️", "insurance motor health"), ("bug", "🐜", "pest termite pest_control"),
    ("course", "🎓", "course class batch english grade maths physics lesson lessons toddler kg admission exam study"),
    ("driving", "🚦", "driving manual automatic file opening"), ("house", "🏠", "flat villa apartment rent tenancy property shop g1"),
    ("website", "🌐", "website hosting web"), ("code", "💻", "software development it support network"),
    ("megaphone", "📣", "campaign social media ads marketing advertising"), ("chart", "📊", "audit bookkeeping accounting vat tax business_plan"),
    ("people", "🧑‍🤝‍🧑", "recruitment hire staff guard security"), ("party", "🎉", "party birthday event stage decoration"),
    ("broom", "🧹", "office_cleaning facility"), ("wrench", "🔧", "maintenance call-out generator servicing service"),
    ("design", "📐", "design 3d design_consultation"), ("fee", "💳", "fee fees commission charge membership valuation"),
    ("package", "🎫", "package card sessions"), ("box", "📦", ""),
]
ART_BY_KEY = {key: emoji for key, emoji, _words in ART}
_WORDS = [(key, [w.replace("_", " ") for w in words.split()]) for key, _e, words in ART]  # a_b = phrase "a b"
TYPE_DEFAULT = {"saloon": "haircut", "beauty_parlour": "makeup", "spa": "massage", "gym": "gym", "vehicle_wash": "car",
                "mobile_shop": "phone", "pharmacy": "medicine", "medical_shop": "medicine", "textile": "fabric",
                "clothing_store": "tshirt", "ladies_fashion_boutique": "dress", "footwear_store": "shoes",
                "supermarket": "rice", "grocery_store": "rice", "bakery": "bread", "jewelry_shop": "jewel",
                "electronics_store": "monitor", "computer_shop": "laptop", "restaurant": "food_service",
                "hotel_apartment": "room", "car_rental": "car", "dental_clinic": "tooth", "medical_clinic": "doctor"}


def _tokens(text):
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", (text or "").lower())


def pick(name, category="", business_code=""):
    """The illustration key for an item: by its name, then its category, then the business type.
    The longest matching word wins ("Hair colour" -> colour, "Beard oil" -> beard)."""
    for text in (name, category):
        tokens = _tokens(text)
        joined = f" {' '.join(tokens)} "
        best, best_len = None, 0
        for key, keys in _WORDS:
            for w in keys:
                if " " in w:
                    hit = f" {w} " in joined or f" {w}s " in joined
                else:
                    hit = w in tokens or (len(w) > 4 and any(t.startswith(w) and len(t) - len(w) <= 2 for t in tokens))
                if hit and len(w) > best_len:
                    best, best_len = key, len(w)
        if best:
            return best
    return TYPE_DEFAULT.get(business_code, "box")


PHOTO_DIR = Path(__file__).resolve().parents[2] / "static" / "products" / "photos"


@lru_cache(maxsize=1)
def _photos():
    """Keys that have a real photo (static/products/photos/<key>.jpg); the illustration is the fallback."""
    return {p.stem for p in PHOTO_DIR.glob("*.jpg")} if PHOTO_DIR.is_dir() else set()


def art_url(key):
    if key in _photos():
        return static(f"products/photos/{key}.jpg")
    return static(f"products/{key}.webp")


def picture_url(product, business_code=""):
    """The product's own photo if it has one, else its illustration."""
    image = getattr(product, "image", None)
    if image:
        try:
            return image.url
        except ValueError:
            pass
    category = product.category.name if getattr(product, "category_id", None) else ""
    return art_url(pick(product.name.split(" — ")[-1], category, business_code))
