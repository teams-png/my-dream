"""Canonical business-type catalogue used by registration, seeding and navigation."""

DEDICATED_TYPES = {
    "mobile_shop": "Mobile Shop", "gym": "Gym / Fitness Center", "spa": "Spa",
    "textile": "Textile", "vehicle_wash": "Vehicle Wash / Car Wash",
    "sports_shop": "Sports Shop", "cycle_shop": "Cycle Shop",
    "saloon": "Saloon / Barber Shop", "beauty_parlour": "Beauty Parlour / Beauty Salon",
    "medical_shop": "Medical Shop / Pharmacy", "protein_shop": "Protein & Supplements Shop",
    "construction": "Construction / Contracting Company",
}

RETAIL_TYPES = {
    "general_retail": "General Retail", "watch_shop": "Watch Shop", "perfume_shop": "Perfume Shop",
    "book_store": "Book & Stationery Shop", "retail_shop": "Retail Shop", "supermarket": "Supermarket",
    "grocery_store": "Grocery Store", "clothing_store": "Clothing Store",
    "ladies_fashion_boutique": "Ladies Fashion / Boutique", "electronics_store": "Electronics Store",
    "computer_shop": "Computer Shop", "furniture_store": "Furniture Store", "hardware_store": "Hardware Store",
    "cosmetics_store": "Cosmetics Store", "jewelry_shop": "Jewelry Shop", "auto_spare_parts": "Auto Spare Parts",
    "medical_equipment_store": "Medical Equipment Store", "flower_shop": "Flower Shop", "pet_shop": "Pet Shop",
    "bakery": "Bakery", "trading_company": "Trading Company", "wholesale_business": "Wholesale Business",
    "import_export": "Import & Export", "car_showroom": "Car Showroom", "printing_shop": "Printing Shop",
    "manufacturing": "Manufacturing", "industrial_services": "Industrial Services",
    "footwear_store": "Footwear / Shoe Shop", "baby_products_store": "Kids / Baby Products Store",
    "toys_gift_shop": "Toys & Gift Shop", "home_appliances_store": "Home Appliances Store",
    "electrical_plumbing_store": "Electrical & Plumbing Store",
    "building_materials_store": "Building Materials Store", "tyre_battery_shop": "Tyre & Battery Shop",
    "fish_meat_shop": "Fish / Meat Shop", "fruits_vegetables_shop": "Fruits & Vegetables Shop",
    "ecommerce_store": "E-commerce / Online Store", "mobile_accessories_shop": "Mobile Accessories Shop",
    "uniform_shop": "Uniform Shop", "kitchenware_store": "Kitchenware / Household Store",
    "musical_instruments_store": "Musical Instruments Shop",
    "agricultural_supplies_store": "Agricultural Supplies Store", "optical_shop": "Optical Shop",
    "fuel_station": "Fuel Station", "restaurant": "Restaurant / Cafeteria",
    "cafe_juice_shop": "Café / Juice Shop",
}

SERVICE_TYPES = {
    "dental_clinic": "Dental Clinic", "medical_clinic": "Medical Clinic",
    "physiotherapy_center": "Physiotherapy Center", "veterinary_clinic": "Veterinary Clinic",
    "photography_studio": "Photography / Videography Studio", "driving_school": "Driving School",
    "tuition_center": "Tuition Center", "consultancy": "Consultancy", "auto_garage": "Auto Garage",
    "repair_services": "Repair Services", "home_services": "Home Services",
    "laundry_dry_cleaning": "Laundry / Dry Cleaning",
    "catering_company": "Catering Company", "car_rental": "Car Rental",
    "equipment_rental": "Equipment Rental", "hotel_apartment": "Hotel / Hotel Apartment",
    "nursery_daycare": "Nursery / Daycare", "school_training_institute": "School / Training Institute",
    "travel_agency": "Travel Agency", "diagnostic_laboratory": "Diagnostic Laboratory",
    "law_firm": "Law Firm / Legal Consultancy", "insurance_brokerage": "Insurance Brokerage",
    "pest_control": "Pest Control Company", "moving_packing": "Moving / Packing Company",
    "ac_maintenance": "AC Maintenance Company", "electronics_repair": "Electronics Repair Centre",
    "computer_repair": "Computer / Laptop Repair", "home_nursing": "Home Nursing",
    "cleaning_equipment_service": "Cleaning Equipment Service",
    "document_clearing": "Immigration / Document Clearing",
    "real_estate_brokerage": "Real Estate Brokerage", "wedding_party_hall": "Wedding / Party Hall",
    "coworking_space": "Co-working Space",
}

PROJECT_TYPES = {
    "advertising_agency": "Advertising Agency", "digital_marketing_agency": "Digital Marketing Agency",
    "web_development": "Web Development", "it_services": "IT Services", "software_company": "Software Company",
    "accounting_audit": "Accounting / Audit", "recruitment_agency": "Recruitment Agency",
    "security_services": "Security Services", "event_management": "Event Management",
    "cleaning_company": "Cleaning Company", "maintenance_company": "Maintenance Company",
    "landscaping_company": "Landscaping Company",
    "property_management": "Property Management", "logistics_transport": "Logistics / Transport Company",
    "courier_delivery": "Courier / Delivery Company", "interior_design": "Interior Design Company",
    "facility_management": "Facility Management",
}

RESTAURANT_TYPES = {
    "restaurant": "Restaurant / Cafeteria",
    "cafe_juice_shop": "Café / Juice Shop",
    "catering_company": "Catering Company",
}

ALIASES = {
    "fitness_center": "gym", "tailoring_shop": "textile", "car_wash": "vehicle_wash",
    "fitness_sports_store": "sports_shop", "barber_shop": "saloon", "beauty_salon": "beauty_parlour",
    "pharmacy": "medical_shop", "contracting_company": "construction",
}

BUSINESS_TYPE_MAP = {**DEDICATED_TYPES, **RETAIL_TYPES, **SERVICE_TYPES, **PROJECT_TYPES}
BUSINESS_TYPE_CHOICES = list(BUSINESS_TYPE_MAP.items())

# Adaptive labels/defaults used by the shared service and project engines.  Every
# catalogue entry receives a profile below, so adding a business type without a
# working UI profile is caught by tests instead of silently falling back.
SERVICE_PROFILE_TYPES = {
    "dental_clinic": "person", "medical_clinic": "person", "physiotherapy_center": "person",
    "diagnostic_laboratory": "person", "home_nursing": "person", "nursery_daycare": "student",
    "school_training_institute": "student", "driving_school": "student", "tuition_center": "student",
    "veterinary_clinic": "pet", "auto_garage": "vehicle", "car_rental": "vehicle",
    "equipment_rental": "asset", "repair_services": "asset", "electronics_repair": "asset",
    "computer_repair": "asset", "cleaning_equipment_service": "asset",
}

PROJECT_TERMS = {
    "advertising_agency": ("Campaigns", "Partners", "Campaign brief"),
    "digital_marketing_agency": ("Campaigns", "Partners", "Campaign brief"),
    "web_development": ("Projects", "Freelancers / Vendors", "Scope / Repository"),
    "it_services": ("Projects", "Vendors", "Service location / Scope"),
    "software_company": ("Projects", "Freelancers / Vendors", "Scope / Repository"),
    "accounting_audit": ("Engagements", "Consultants", "Engagement scope"),
    "recruitment_agency": ("Recruitment Projects", "Recruiters / Partners", "Role / Location"),
    "security_services": ("Service Contracts", "Guards / Vendors", "Service location"),
    "event_management": ("Events", "Vendors", "Venue"),
    "cleaning_company": ("Service Contracts", "Teams / Vendors", "Service location"),
    "maintenance_company": ("Maintenance Projects", "Technicians / Vendors", "Site / Asset"),
    "landscaping_company": ("Landscaping Projects", "Teams / Vendors", "Site address"),
    "property_management": ("Properties / Contracts", "Owners / Vendors", "Property address"),
    "logistics_transport": ("Transport Jobs", "Drivers / Carriers", "Route / Delivery area"),
    "courier_delivery": ("Delivery Jobs", "Drivers / Partners", "Route / Delivery area"),
    "interior_design": ("Design Projects", "Designers / Contractors", "Site address"),
    "facility_management": ("Facility Contracts", "Teams / Vendors", "Facility address"),
}


# Industry modules switched on per business type (on top of the group's engine).
INDUSTRY_FEATURES = {
    # rooms / vehicles / equipment / halls / desks booked by date and time
    "bookings": {"hotel_apartment", "car_rental", "equipment_rental", "wedding_party_hall", "coworking_space"},
    # products sold by weight (kg) and weighing-scale barcodes at the POS
    "weighed": {"supermarket", "grocery_store", "fish_meat_shop", "fruits_vegetables_shop", "bakery",
                "agricultural_supplies_store"},
    # students, courses, monthly fees and attendance
    "education": {"school_training_institute", "tuition_center", "nursery_daycare", "driving_school"},
    # properties, units, tenancy contracts and monthly rent
    "leases": {"property_management", "real_estate_brokerage"},
    # gold rate x weight + making charge pricing
    "gold": {"jewelry_shop"},
}

# (resource, resource plural, booking, default rate unit) for the bookings module
BOOKING_TERMS = {
    "hotel_apartment": ("Room", "Rooms", "Reservation", "night"),
    "car_rental": ("Vehicle", "Vehicles", "Rental", "day"),
    "equipment_rental": ("Equipment", "Equipment", "Rental", "day"),
    "wedding_party_hall": ("Hall", "Halls", "Event booking", "event"),
    "coworking_space": ("Space", "Spaces", "Booking", "hour"),
}


# (course, courses, student, students) for the education module
EDUCATION_TERMS = {
    "school_training_institute": ("Course", "Courses", "Student", "Students"),
    "tuition_center": ("Batch", "Batches", "Student", "Students"),
    "nursery_daycare": ("Class", "Classes", "Child", "Children"),
    "driving_school": ("Package", "Packages", "Learner", "Learners"),
}


def business_features(code):
    code = ALIASES.get(code, code)
    return {name for name, codes in INDUSTRY_FEATURES.items() if code in codes}


def business_profile(code):
    """Return complete UI/workflow metadata for any registered business type."""
    code = ALIASES.get(code, code)
    group = business_group(code)
    profile = {"code": code, "group": group, "name": BUSINESS_TYPE_MAP.get(code, "Business"),
               "features": sorted(business_features(code))}
    if code in BOOKING_TERMS:
        resource, resources, booking, unit = BOOKING_TERMS[code]
        profile.update(resource_label=resource, resources_label=resources, booking_label=booking,
                       default_rate_unit=unit)
    if code in EDUCATION_TERMS:
        course, courses, student, students = EDUCATION_TERMS[code]
        profile.update(course_label=course, courses_label=courses, student_label=student, students_label=students)
    if group == "service":
        profile.update(profile_type=SERVICE_PROFILE_TYPES.get(code, "organization"),
                       records_label="Clients / Subjects", work_label="Cases / Work Orders",
                       provider_label="Staff")
    elif group == "project":
        projects, providers, location = PROJECT_TERMS.get(code, ("Projects", "Vendors", "Location / Scope"))
        profile.update(projects_label=projects, provider_label=providers, location_label=location)
    elif group == "restaurant":
        profile.update(records_label="Guests", work_label="Orders", provider_label="Kitchen / Staff")
    else:
        profile.update(records_label="Customers", work_label="Sales", provider_label="Suppliers")
    return profile


def business_group(code):
    code = ALIASES.get(code, code)
    if code in RESTAURANT_TYPES: return "restaurant"
    if code in RETAIL_TYPES: return "retail"
    if code in SERVICE_TYPES: return "service"
    if code in PROJECT_TYPES: return "project"
    return code if code in DEDICATED_TYPES else "retail"


BUSINESS_PROFILES = {code: business_profile(code) for code in BUSINESS_TYPE_MAP}
