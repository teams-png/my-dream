"""Fetches the default product / service pictures into static/products/cut/<key>.webp.

They are Microsoft's Fluent Emoji 3D renders (MIT licence, https://github.com/microsoft/fluentui-emoji):
realistic 3D objects on a transparent background, so they sit cleanly on any tile. The files are committed,
so servers never run this. Real photos put in static/products/photos/ (see cutout_photos) take precedence.
"""
import io
from pathlib import Path
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from apps.inventory.pictures import ART

BASE = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/"
# picture key -> file in the fluentui-emoji repository
FLUENT = {
    "shave": "Razor/3D/razor_3d.png",
    "hair_style": "Person getting haircut/Default/3D/person_getting_haircut_3d_default.png",
    "hair_wash": "Shower/3D/shower_3d.png",
    "head_massage": "Person getting massage/Default/3D/person_getting_massage_3d_default.png",
    "face_mask": "Person getting massage/Default/3D/person_getting_massage_3d_default.png",
    "pedicure": "Foot/Default/3D/foot_3d_default.png",
    "bridal": "Person with veil/Default/3D/person_with_veil_3d_default.png",
    "aromatherapy": "Blossom/3D/blossom_3d.png",
    "scrub": "Sponge/3D/sponge_3d.png",
    "body_wrap": "Herb/3D/herb_3d.png",
    "foot_massage": "Foot/Default/3D/foot_3d_default.png",
    "foot_spa": "Hot springs/3D/hot_springs_3d.png",
    "herbal": "Herb/3D/herb_3d.png",
    "spa_oil": "Lotion bottle/3D/lotion_bottle_3d.png",
    "towel": "Roll of paper/3D/roll_of_paper_3d.png",
    "sadya": "Bento box/3D/bento_box_3d.png",
    "curry": "Pot of food/3D/pot_of_food_3d.png",
    "fish_curry": "Shallow pan of food/3D/shallow_pan_of_food_3d.png",
    "fried_rice": "Cooked rice/3D/cooked_rice_3d.png",
    "appam": "Flatbread/3D/flatbread_3d.png",
    "porotta": "Flatbread/3D/flatbread_3d.png",
    "tandoori": "Meat on bone/3D/meat_on_bone_3d.png",
    "mojito": "Tropical drink/3D/tropical_drink_3d.png",
    "ac": "Snowflake/3D/snowflake_3d.png",
    "air_freshener": "Herb/3D/herb_3d.png",
    "apple": "Red apple/3D/red_apple_3d.png",
    "badminton": "Badminton/3D/badminton_3d.png",
    "bag": "Handbag/3D/handbag_3d.png",
    "banana": "Banana/3D/banana_3d.png",
    "bath": "Bathtub/3D/bathtub_3d.png",
    "battery": "Battery/3D/battery_3d.png",
    "beard": "Person beard/Default/3D/person_beard_3d_default.png",
    "belt": "Knot/3D/knot_3d.png",
    "bicycle": "Bicycle/3D/bicycle_3d.png",
    "biryani": "Curry rice/3D/curry_rice_3d.png",
    "blocks": "Puzzle piece/3D/puzzle_piece_3d.png",
    "book": "Closed book/3D/closed_book_3d.png",
    "box": "Package/3D/package_3d.png",
    "brake": "Gear/3D/gear_3d.png",
    "bread": "Bread/3D/bread_3d.png",
    "broom": "Broom/3D/broom_3d.png",
    "bug": "Ant/3D/ant_3d.png",
    "bulb": "Light bulb/3D/light_bulb_3d.png",
    "burger": "Hamburger/3D/hamburger_3d.png",
    "cake": "Birthday cake/3D/birthday_cake_3d.png",
    "camera": "Camera/3D/camera_3d.png",
    "candle": "Candle/3D/candle_3d.png",
    "cap": "Billed cap/3D/billed_cap_3d.png",
    "car": "Automobile/3D/automobile_3d.png",
    "cement": "Brick/3D/brick_3d.png",
    "charger": "Electric plug/3D/electric_plug_3d.png",
    "chart": "Bar chart/3D/bar_chart_3d.png",
    "chicken": "Poultry leg/3D/poultry_leg_3d.png",
    "cleaning": "Sponge/3D/sponge_3d.png",
    "code": "Laptop/3D/laptop_3d.png",
    "coffee": "Hot beverage/3D/hot_beverage_3d.png",
    "cookies": "Cookie/3D/cookie_3d.png",
    "course": "Graduation cap/3D/graduation_cap_3d.png",
    "cricket": "Cricket game/3D/cricket_game_3d.png",
    "croissant": "Croissant/3D/croissant_3d.png",
    "design": "Triangular ruler/3D/triangular_ruler_3d.png",
    "desk": "Technologist/Default/3D/technologist_3d_default.png",
    "dessert": "Custard/3D/custard_3d.png",
    "diaper": "Baby bottle/3D/baby_bottle_3d.png",
    "doctor": "Stethoscope/3D/stethoscope_3d.png",
    "document": "Page facing up/3D/page_facing_up_3d.png",
    "dosa": "Flatbread/3D/flatbread_3d.png",
    "dress": "Dress/3D/dress_3d.png",
    "drill": "Nut and bolt/3D/nut_and_bolt_3d.png",
    "driving": "Vertical traffic light/3D/vertical_traffic_light_3d.png",
    "egg": "Egg/3D/egg_3d.png",
    "equipment": "Building construction/3D/building_construction_3d.png",
    "fabric": "Thread/3D/thread_3d.png",
    "facial": "Person in steamy room/Default/3D/person_in_steamy_room_3d_default.png",
    "fee": "Credit card/3D/credit_card_3d.png",
    "fish": "Fish/3D/fish_3d.png",
    "flowers": "Bouquet/3D/bouquet_3d.png",
    "food_service": "Fork and knife with plate/3D/fork_and_knife_with_plate_3d.png",
    "football": "Soccer ball/3D/soccer_ball_3d.png",
    "fries": "French fries/3D/french_fries_3d.png",
    "fuel": "Fuel pump/3D/fuel_pump_3d.png",
    "gift": "Wrapped gift/3D/wrapped_gift_3d.png",
    "glass_guard": "Shield/3D/shield_3d.png",
    "glasses": "Glasses/3D/glasses_3d.png",
    "gloves": "Gloves/3D/gloves_3d.png",
    "guitar": "Guitar/3D/guitar_3d.png",
    "gym": "Person lifting weights/Default/3D/person_lifting_weights_3d_default.png",
    "hair_care": "Lotion bottle/3D/lotion_bottle_3d.png",
    "hair_colour": "Artist palette/3D/artist_palette_3d.png",
    "haircut": "Scissors/3D/scissors_3d.png",
    "hall": "Classical building/3D/classical_building_3d.png",
    "headphones": "Headphone/3D/headphone_3d.png",
    "helmet": "Rescue workers helmet/3D/rescue_workers_helmet_3d.png",
    "house": "House/3D/house_3d.png",
    "ice_cream": "Ice cream/3D/ice_cream_3d.png",
    "insurance": "Shield/3D/shield_3d.png",
    "jewel": "Prayer beads/3D/prayer_beads_3d.png",
    "juice": "Cup with straw/3D/cup_with_straw_3d.png",
    "keyboard_music": "Musical keyboard/3D/musical_keyboard_3d.png",
    "kids_wear": "Teddy bear/3D/teddy_bear_3d.png",
    "laptop": "Laptop/3D/laptop_3d.png",
    "makeup": "Lipstick/3D/lipstick_3d.png",
    "massage": "Person getting massage/Default/3D/person_getting_massage_3d_default.png",
    "meat": "Cut of meat/3D/cut_of_meat_3d.png",
    "medicine": "Pill/3D/pill_3d.png",
    "megaphone": "Megaphone/3D/megaphone_3d.png",
    "microwave": "Package/3D/package_3d.png",
    "milk": "Glass of milk/3D/glass_of_milk_3d.png",
    "monitor": "Desktop computer/3D/desktop_computer_3d.png",
    "motor_oil": "Oil drum/3D/oil_drum_3d.png",
    "mouse": "Computer mouse/3D/computer_mouse_3d.png",
    "nails": "Nail polish/Default/3D/nail_polish_3d_default.png",
    "noodles": "Steaming bowl/3D/steaming_bowl_3d.png",
    "notebook": "Notebook/3D/notebook_3d.png",
    "oil": "Olive/3D/olive_3d.png",
    "onion": "Onion/3D/onion_3d.png",
    "package": "Ticket/3D/ticket_3d.png",
    "paint": "Paintbrush/3D/paintbrush_3d.png",
    "pan": "Cooking/3D/cooking_3d.png",
    "party": "Party popper/3D/party_popper_3d.png",
    "pass": "Admission tickets/3D/admission_tickets_3d.png",
    "people": "Busts in silhouette/3D/busts_in_silhouette_3d.png",
    "perfume": "Cherry blossom/3D/cherry_blossom_3d.png",
    "pet": "Paw prints/3D/paw_prints_3d.png",
    "phone": "Mobile phone/3D/mobile_phone_3d.png",
    "pipe": "Potable water/3D/potable_water_3d.png",
    "pizza": "Pizza/3D/pizza_3d.png",
    "plane": "Airplane/3D/airplane_3d.png",
    "printer": "Printer/3D/printer_3d.png",
    "protein": "Flexed biceps/Default/3D/flexed_biceps_3d_default.png",
    "repair": "Hammer and wrench/3D/hammer_and_wrench_3d.png",
    "rice": "Cooked rice/3D/cooked_rice_3d.png",
    "ring": "Ring/3D/ring_3d.png",
    "room": "Bed/3D/bed_3d.png",
    "salad": "Green salad/3D/green_salad_3d.png",
    "sandals": "Womans sandal/3D/womans_sandal_3d.png",
    "sandwich": "Sandwich/3D/sandwich_3d.png",
    "saree": "Sari/3D/sari_3d.png",
    "scarf": "Scarf/3D/scarf_3d.png",
    "seeds": "Seedling/3D/seedling_3d.png",
    "shawarma": "Stuffed flatbread/3D/stuffed_flatbread_3d.png",
    "shirt": "Necktie/3D/necktie_3d.png",
    "shoes": "Running shoe/3D/running_shoe_3d.png",
    "shrimp": "Fried shrimp/3D/fried_shrimp_3d.png",
    "sofa": "Couch and lamp/3D/couch_and_lamp_3d.png",
    "speaker": "Speaker high volume/3D/speaker_high_volume_3d.png",
    "stone": "Rock/3D/rock_3d.png",
    "storage": "Floppy disk/3D/floppy_disk_3d.png",
    "sugar": "Salt/3D/salt_3d.png",
    "sunglasses": "Sunglasses/3D/sunglasses_3d.png",
    "syrup": "Test tube/3D/test_tube_3d.png",
    "table": "Chair/3D/chair_3d.png",
    "tape": "Straight ruler/3D/straight_ruler_3d.png",
    "tea": "Teacup without handle/3D/teacup_without_handle_3d.png",
    "teddy": "Teddy bear/3D/teddy_bear_3d.png",
    "thermometer": "Thermometer/3D/thermometer_3d.png",
    "threading": "Sewing needle/3D/sewing_needle_3d.png",
    "tomato": "Tomato/3D/tomato_3d.png",
    "tooth": "Tooth/3D/tooth_3d.png",
    "transport": "Delivery truck/3D/delivery_truck_3d.png",
    "trousers": "Jeans/3D/jeans_3d.png",
    "tshirt": "T-shirt/3D/t-shirt_3d.png",
    "tyre": "Wheel/3D/wheel_3d.png",
    "washing": "Basket/3D/basket_3d.png",
    "watch": "Watch/3D/watch_3d.png",
    "water": "Droplet/3D/droplet_3d.png",
    "website": "Globe with meridians/3D/globe_with_meridians_3d.png",
    "wheelchair": "Manual wheelchair/3D/manual_wheelchair_3d.png",
    "wiper": "Cloud with rain/3D/cloud_with_rain_3d.png",
    "wire": "Yarn/3D/yarn_3d.png",
    "wrench": "Wrench/3D/wrench_3d.png",
}
LICENCE = """Default product pictures: Fluent Emoji by Microsoft, MIT License.
Copyright (c) Microsoft Corporation. https://github.com/microsoft/fluentui-emoji/blob/main/LICENSE
"""


class Command(BaseCommand):
    help = "Download the transparent 3D default pictures (needs access to raw.githubusercontent.com)."

    def add_arguments(self, parser):
        parser.add_argument("--only", default="", help="comma-separated keys")

    def handle(self, *args, only="", **options):
        out = Path(settings.BASE_DIR) / "static" / "products" / "cut"
        out.mkdir(parents=True, exist_ok=True)
        keys = [k for k, _e, _w in ART if not only or k in only.split(",")]
        missing = [k for k in keys if k not in FLUENT]
        if missing:
            self.stderr.write(f"no 3D picture mapped for: {', '.join(missing)}")
        session = requests.Session()
        for key in keys:
            if key not in FLUENT:
                continue
            r = session.get(BASE + quote(FLUENT[key]), timeout=30)
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGBA")
            im.save(out / f"{key}.webp", "WEBP", quality=90, method=6)
            self.stdout.write(key)
        (out / "LICENSE.txt").write_text(LICENCE)
        self.stdout.write(self.style.SUCCESS(f"{len(keys) - len(missing)} pictures in {out}"))
