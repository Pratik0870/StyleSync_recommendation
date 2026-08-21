"""Controlled vocabularies for the AI Beauty & Fashion Match catalog.

Every mapping here is exhaustive over the values actually present in
`ashraq/fashion-product-images-small` (46 baseColour, 141 articleType,
45 subCategory, 7 masterCategory, 8 usage, 5 gender). The ingestion pipeline
asserts exhaustiveness, so an unmapped value fails the build rather than
silently becoming "unknown".

Nothing in this module scores or ranks anything. It only normalises the raw
catalog vocabulary into stable attribute values.
"""

# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------
# Each raw baseColour maps to (colour_family, representative_hex, is_neutral,
# is_metallic). The hex is a *representative* of the family, not a measurement
# of the product - the source data gives a colour name, never a pixel value.

COLOUR_MAP: dict[str, tuple[str, str | None, bool, bool]] = {
    # neutrals - dark to light
    "Black":             ("black",  "#1A1A1A", True,  False),
    "Charcoal":          ("grey",   "#36454F", True,  False),
    "Grey":              ("grey",   "#808080", True,  False),
    "Grey Melange":      ("grey",   "#9A9A9A", True,  False),
    "Steel":             ("grey",   "#7A8B8B", True,  False),
    "White":             ("white",  "#FFFFFF", True,  False),
    "Off White":         ("white",  "#F5F2EA", True,  False),
    "Cream":             ("beige",  "#F1E4C3", True,  False),
    # skin / sand neutrals - the family beauty products lean on
    "Beige":             ("beige",  "#E8D9B0", True,  False),
    "Skin":              ("beige",  "#E8C39E", True,  False),
    "Nude":              ("beige",  "#E3BC9A", True,  False),
    "Taupe":             ("beige",  "#8B8589", True,  False),
    "Khaki":             ("beige",  "#C3B091", True,  False),
    # browns
    "Tan":               ("brown",  "#D2B48C", True,  False),
    "Mushroom Brown":    ("brown",  "#A38068", True,  False),
    "Brown":             ("brown",  "#7B4B27", False, False),
    "Coffee Brown":      ("brown",  "#4B3621", False, False),
    # reds
    "Red":               ("red",    "#D0021B", False, False),
    "Maroon":            ("red",    "#800000", False, False),
    "Burgundy":          ("red",    "#6E1220", False, False),
    # pinks
    "Pink":              ("pink",   "#FF6FA8", False, False),
    "Rose":              ("pink",   "#E37383", False, False),
    "Magenta":           ("pink",   "#C2185B", False, False),
    # purples
    "Purple":            ("purple", "#6B3FA0", False, False),
    "Lavender":          ("purple", "#C4A7E7", False, False),
    "Mauve":             ("purple", "#B784A7", False, False),
    # blues
    "Blue":              ("blue",   "#1F6FEB", False, False),
    "Navy Blue":         ("blue",   "#001F5B", False, False),
    "Turquoise Blue":    ("blue",   "#30D5C8", False, False),
    "Teal":              ("blue",   "#008080", False, False),
    # greens
    "Green":             ("green",  "#2E7D32", False, False),
    "Olive":             ("green",  "#708238", False, False),
    "Sea Green":         ("green",  "#2E8B57", False, False),
    "Lime Green":        ("green",  "#BFFF00", False, False),
    "Fluorescent Green": ("green",  "#39FF14", False, False),
    # yellows / oranges
    "Yellow":            ("yellow", "#F8E71C", False, False),
    "Mustard":           ("yellow", "#E1AD01", False, False),
    "Orange":            ("orange", "#F5811F", False, False),
    "Peach":             ("orange", "#FFCBA4", False, False),
    "Rust":              ("orange", "#B7410E", False, False),
    # metallics - flagged separately because metal consistency is its own rule
    "Gold":              ("gold",   "#D4AF37", False, True),
    "Bronze":            ("gold",   "#CD7F32", False, True),
    "Copper":            ("gold",   "#B87333", False, True),
    "Silver":            ("silver", "#C0C0C0", True,  True),
    "Metallic":          ("silver", "#B8B8B8", True,  True),
    # unresolvable
    "Multi":             ("multi",  None,      False, False),
}

COLOUR_FAMILIES = sorted({v[0] for v in COLOUR_MAP.values()})

# --------------------------------------------------------------------------
# Domain
# --------------------------------------------------------------------------

DOMAIN_MAP: dict[str, str] = {
    "Apparel":        "apparel",
    "Accessories":    "accessory",
    "Footwear":       "footwear",
    "Personal Care":  "beauty",
    "Free Items":     "excluded",
    "Sporting Goods": "excluded",
    "Home":           "excluded",
}

# --------------------------------------------------------------------------
# Category groups
# --------------------------------------------------------------------------
# Keyed by raw articleType. These are *product categories*, deliberately not
# wardrobe slots - this system recommends complementary categories, it does not
# assemble an outfit from positional slots.

CATEGORY_GROUP_MAP: dict[str, str] = {
    # ---- beauty: colour cosmetics -------------------------------------
    "Lipstick": "beauty_lip", "Lip Gloss": "beauty_lip", "Lip Liner": "beauty_lip",
    "Lip Care": "beauty_lip", "Lip Plumper": "beauty_lip",
    "Kajal and Eyeliner": "beauty_eye", "Eyeshadow": "beauty_eye",
    "Mascara": "beauty_eye", "Eye Cream": "beauty_eye",
    "Foundation and Primer": "beauty_face", "Compact": "beauty_face",
    "Highlighter and Blush": "beauty_face", "Concealer": "beauty_face",
    "Nail Polish": "beauty_nails", "Nail Essentials": "beauty_nails",
    # ---- beauty: non-colour -------------------------------------------
    "Face Moisturisers": "beauty_skincare", "Face Wash and Cleanser": "beauty_skincare",
    "Sunscreen": "beauty_skincare", "Mask and Peel": "beauty_skincare",
    "Face Scrub and Exfoliator": "beauty_skincare", "Face Serum and Gel": "beauty_skincare",
    "Toner": "beauty_skincare", "Body Lotion": "beauty_skincare",
    "Body Wash and Scrub": "beauty_skincare", "Makeup Remover": "beauty_skincare",
    "Perfume and Body Mist": "fragrance", "Deodorant": "fragrance",
    "Fragrance Gift Set": "fragrance",
    "Hair Colour": "beauty_hair",
    "Beauty Accessory": "beauty_tools", "Mens Grooming Kit": "beauty_tools",
    # ---- accessories ---------------------------------------------------
    "Earrings": "jewellery", "Pendant": "jewellery", "Necklace and Chains": "jewellery",
    "Ring": "jewellery", "Bangle": "jewellery", "Bracelet": "jewellery",
    "Jewellery Set": "jewellery",
    "Handbags": "bag", "Clutches": "bag", "Backpacks": "bag", "Duffel Bag": "bag",
    "Laptop Bag": "bag", "Messenger Bag": "bag", "Mobile Pouch": "bag",
    "Rucksacks": "bag", "Trolley Bag": "bag", "Waist Pouch": "bag",
    "Tablet Sleeve": "bag",
    "Wallets": "wallet",
    "Watches": "watch",
    "Sunglasses": "eyewear",
    "Belts": "belt",
    "Caps": "headwear", "Hat": "headwear", "Headband": "headwear",
    "Hair Accessory": "headwear",
    "Scarves": "neckwear", "Stoles": "neckwear", "Mufflers": "neckwear",
    "Dupatta": "neckwear", "Ties": "neckwear",
    "Cufflinks": "accessory_other", "Ties and Cufflinks": "accessory_other",
    "Accessory Gift Set": "accessory_other", "Suspenders": "accessory_other",
    "Gloves": "accessory_other", "Wristbands": "accessory_other",
    "Key chain": "accessory_other", "Travel Accessory": "accessory_other",
    "Umbrellas": "accessory_other", "Water Bottle": "accessory_other",
    "Shoe Accessories": "accessory_other", "Shoe Laces": "accessory_other",
    "Socks": "accessory_other", "Stockings": "accessory_other",
    # ---- footwear -------------------------------------------------------
    "Heels": "footwear_dress", "Booties": "footwear_dress",
    "Flats": "footwear_flat", "Sandals": "footwear_flat",
    "Flip Flops": "footwear_flat", "Sports Sandals": "footwear_flat",
    "Formal Shoes": "footwear_formal",
    "Casual Shoes": "footwear_casual",
    "Sports Shoes": "footwear_sports",
    # ---- apparel: ethnic (the anchor category this product is built around)
    "Sarees": "ethnic_wear", "Kurtas": "ethnic_wear", "Kurtis": "ethnic_wear",
    "Kurta Sets": "ethnic_wear", "Lehenga Choli": "ethnic_wear",
    "Salwar": "ethnic_wear", "Salwar and Dupatta": "ethnic_wear",
    "Churidar": "ethnic_wear", "Patiala": "ethnic_wear", "Tunics": "ethnic_wear",
    "Nehru Jackets": "ethnic_wear",
    # ---- apparel: western ----------------------------------------------
    "Dresses": "dress", "Jumpsuit": "dress", "Rompers": "dress",
    "Tops": "topwear", "Tshirts": "topwear", "Shirts": "topwear",
    "Sweatshirts": "topwear", "Sweaters": "topwear", "Camisoles": "topwear",
    "Shrug": "topwear", "Waistcoat": "topwear", "Blazers": "outerwear",
    "Jackets": "outerwear", "Rain Jacket": "outerwear",
    "Jeans": "bottomwear", "Trousers": "bottomwear", "Shorts": "bottomwear",
    "Track Pants": "bottomwear", "Capris": "bottomwear", "Skirts": "bottomwear",
    "Leggings": "bottomwear", "Jeggings": "bottomwear", "Tights": "bottomwear",
    "Lounge Pants": "loungewear", "Lounge Shorts": "loungewear",
    "Lounge Tshirts": "loungewear", "Nightdress": "loungewear",
    "Night suits": "loungewear", "Baby Dolls": "loungewear",
    "Bath Robe": "loungewear", "Robe": "loungewear",
    "Briefs": "innerwear", "Bra": "innerwear", "Trunk": "innerwear",
    "Boxers": "innerwear", "Innerwear Vests": "innerwear",
    "Shapewear": "innerwear", "Swimwear": "innerwear",
    "Apparel Set": "apparel_set", "Clothing Set": "apparel_set",
    "Tracksuits": "apparel_set",
    # ---- not products ---------------------------------------------------
    "Free Gifts": "excluded", "Vouchers": "excluded", "Basketballs": "excluded",
    "Footballs": "excluded", "Sports Equipment": "excluded",
    "Cushion Covers": "excluded", "Home Furnishing": "excluded", "Ipad": "excluded",
}

# Groups that can be the *anchor* - the garment a user says they are wearing.
ANCHOR_GROUPS = {"ethnic_wear", "dress", "topwear", "bottomwear", "outerwear", "apparel_set"}

# Groups that can be *recommended as a complement* to an anchor.
COMPLEMENT_GROUPS = {
    "beauty_lip", "beauty_eye", "beauty_face", "beauty_nails",
    "fragrance", "jewellery", "bag", "footwear_dress", "footwear_flat",
    "footwear_formal", "footwear_casual", "watch", "eyewear", "belt",
    "headwear", "neckwear", "wallet",
}

# What a product's colour actually *means*. Not every baseColour is a style
# choice, and treating them alike would let the engine "match" a foundation
# shade to a saree, which is nonsense - foundation matches a face, not an outfit.
#
#   style       the colour is a look decision      (lipstick, saree, handbag)
#   skin_match  the colour is the wearer's skin    (foundation, concealer, compact)
#   packaging   the colour describes the container (perfume bottle, face wash)

SKIN_MATCH_TYPES = {
    "Foundation and Primer", "Compact", "Concealer",
}

PACKAGING_COLOUR_GROUPS = {
    "fragrance", "beauty_skincare", "beauty_hair", "beauty_tools",
}


def colour_role(article_type: str, category_group: str) -> str:
    if article_type in SKIN_MATCH_TYPES:
        return "skin_match"
    if category_group in PACKAGING_COLOUR_GROUPS:
        return "packaging"
    if category_group in COMPLEMENT_GROUPS or category_group in ANCHOR_GROUPS:
        return "style"
    return "packaging"

# --------------------------------------------------------------------------
# Occasion
# --------------------------------------------------------------------------
# Source column is `usage`. Reliable on apparel; NOT reliable on beauty, where
# 2,136 of 2,139 rows are labelled "Casual" regardless of the actual product.

OCCASION_MAP: dict[str, str] = {
    "Casual": "casual",
    "Ethnic": "ethnic",
    "Formal": "formal",
    "Sports": "sports",
    "Party": "party",
    "Smart Casual": "smart_casual",
    "Travel": "travel",
    "Home": "home",
}

# --------------------------------------------------------------------------
# Audience
# --------------------------------------------------------------------------

GENDER_MAP: dict[str, tuple[str, str]] = {
    # raw -> (gender, age_group)
    "Men":    ("men",    "adult"),
    "Women":  ("women",  "adult"),
    "Unisex": ("unisex", "adult"),
    "Boys":   ("men",    "kids"),
    "Girls":  ("women",  "kids"),
}
