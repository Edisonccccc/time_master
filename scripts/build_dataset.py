#!/usr/bin/env python3
"""
build_dataset.py — generate data/nyc_venues.json (the seed dataset).

WHY a generator: 100 venues hand-written as JSON drift in schema and tag scale.
Here, each venue is a compact record; tags come from an ARCHETYPE base profile
plus per-venue overrides. This keeps the rubric axes on a consistent 0–1 scale
and makes the dataset easy to extend.

DATA STATUS (read data/DATA_NOTES.md): venue facts (Michelin status, booking
platform, lat/lng) are from general knowledge and are a SEED for local dev
(milestones M1–M3). They must be verified before live availability / launch (M4).

Run:  python3 scripts/build_dataset.py
Out:  data/nyc_venues.json   (array of Venue objects, schema in docs/DESIGN.md §4)
"""

import json
import os

# --- Archetype base tag profiles -------------------------------------------
# Axes (see docs/DESIGN.md §3). All 0–1 except duration_min (minutes) and the
# two booleans (seating_counter, fixed_menu). Per-venue overrides applied later.
A = {
    "fine_dining_temple": dict(  # EMP, Per Se, Le Bernardin, Daniel...
        noise=0.15, conversation=0.70, intimacy=0.70, ambiance=0.95, formality=0.90,
        special_factor=0.98, duration_min=180, seating_counter=False, fixed_menu=True,
        privacy=0.70, staff_coordination=0.92, central_transit=0.60, view=0.20),
    "omakase_counter": dict(  # Nakazawa, Noz, Ichimura, Onodera...
        noise=0.20, conversation=0.55, intimacy=0.75, ambiance=0.78, formality=0.78,
        special_factor=0.95, duration_min=120, seating_counter=True, fixed_menu=True,
        privacy=0.45, staff_coordination=0.82, central_transit=0.60, view=0.10),
    "modern_tasting": dict(  # Atomix, Atera, Aska, Saga...
        noise=0.25, conversation=0.60, intimacy=0.75, ambiance=0.90, formality=0.78,
        special_factor=0.94, duration_min=150, seating_counter=True, fixed_menu=True,
        privacy=0.55, staff_coordination=0.85, central_transit=0.55, view=0.25),
    "romantic_special": dict(  # One if by Land, River Cafe, Gramercy Tavern...
        noise=0.30, conversation=0.78, intimacy=0.85, ambiance=0.90, formality=0.65,
        special_factor=0.85, duration_min=130, seating_counter=False, fixed_menu=False,
        privacy=0.75, staff_coordination=0.85, central_transit=0.55, view=0.45),
    "date_night_notable": dict(  # Cosme, Estela, Crown Shy, Frenchette, Le Coucou...
        noise=0.45, conversation=0.68, intimacy=0.62, ambiance=0.82, formality=0.45,
        special_factor=0.80, duration_min=105, seating_counter=False, fixed_menu=False,
        privacy=0.45, staff_coordination=0.70, central_transit=0.70, view=0.15),
    "lively_bistro": dict(  # Via Carota, L'Artusi, Raoul's, Balthazar...
        noise=0.58, conversation=0.62, intimacy=0.52, ambiance=0.72, formality=0.30,
        special_factor=0.55, duration_min=90, seating_counter=False, fixed_menu=False,
        privacy=0.30, staff_coordination=0.55, central_transit=0.78, view=0.10),
    "casual_cool": dict(  # Rubirosa, Emily, Tacombi, Mogador...
        noise=0.58, conversation=0.70, intimacy=0.42, ambiance=0.55, formality=0.18,
        special_factor=0.42, duration_min=80, seating_counter=False, fixed_menu=False,
        privacy=0.25, staff_coordination=0.45, central_transit=0.78, view=0.05),
    # --- drinks ---
    "cocktail_bar_intimate": dict(
        noise=0.50, conversation=0.62, intimacy=0.82, ambiance=0.85, formality=0.35,
        special_factor=0.65, duration_min=60, seating_counter=True, fixed_menu=False,
        privacy=0.55, staff_coordination=0.50, central_transit=0.70, view=0.10),
    "wine_bar": dict(
        noise=0.48, conversation=0.75, intimacy=0.70, ambiance=0.72, formality=0.30,
        special_factor=0.55, duration_min=60, seating_counter=True, fixed_menu=False,
        privacy=0.45, staff_coordination=0.50, central_transit=0.72, view=0.05),
    "hotel_bar_view": dict(
        noise=0.55, conversation=0.55, intimacy=0.55, ambiance=0.90, formality=0.50,
        special_factor=0.85, duration_min=60, seating_counter=True, fixed_menu=False,
        privacy=0.35, staff_coordination=0.55, central_transit=0.65, view=0.95),
    # --- dessert / walk ---
    "dessert": dict(
        noise=0.45, conversation=0.70, intimacy=0.45, ambiance=0.55, formality=0.15,
        special_factor=0.55, duration_min=40, seating_counter=False, fixed_menu=False,
        privacy=0.25, staff_coordination=0.30, central_transit=0.75, view=0.05),
    "walk": dict(
        noise=0.15, conversation=0.85, intimacy=0.70, ambiance=0.80, formality=0.05,
        special_factor=0.65, duration_min=30, seating_counter=False, fixed_menu=False,
        privacy=0.55, staff_coordination=0.10, central_transit=0.60, view=0.85),
}

ROLE_BY_ARCHETYPE = {
    "fine_dining_temple": ["dinner"], "omakase_counter": ["dinner"],
    "modern_tasting": ["dinner"], "romantic_special": ["dinner"],
    "date_night_notable": ["dinner"], "lively_bistro": ["dinner"],
    "casual_cool": ["dinner"], "cocktail_bar_intimate": ["drinks"],
    "wine_bar": ["drinks"], "hotel_bar_view": ["drinks"],
    "dessert": ["dessert"], "walk": ["walk"],
}

# Tuple fields: name, hood, lat, lng, archetype, price_tier, michelin,
#               platform, cuisine(list), good_for(list), notes, overrides(dict)
# michelin: None | "bib_gourmand" | "1_star" | "2_star" | "3_star"
# platform: resy | opentable | tock | phone_only | walk_in
V = [
    # ===================== TRIBECA / SOHO / NOLITA =====================
    ("Atera", "Tribeca", 40.7176, -74.0050, "modern_tasting", 4, "2_star", "tock",
     ["tasting", "american"], ["anniversary"], "Counter tasting menu; deposit via Tock.", {}),
    ("Frenchette", "Tribeca", 40.7193, -74.0089, "date_night_notable", 3, None, "resy",
     ["french"], ["second_date", "anniversary"], "Buzzy French; great room.", {}),
    ("L'Appartement 4F", "Brooklyn Heights", 40.6957, -73.9931, "dessert", 2, None, "walk_in",
     ["bakery", "dessert"], ["first_date"], "Croissants/pastries; cozy.", {}),
    ("Le Coucou", "Soho", 40.7195, -73.9986, "date_night_notable", 4, None, "resy",
     ["french"], ["anniversary", "second_date"], "Gorgeous room; special-feeling.",
     {"ambiance": 0.92, "special_factor": 0.88, "intimacy": 0.72}),
    ("Rubirosa", "Nolita", 40.7222, -73.9961, "casual_cool", 2, None, "resy",
     ["italian", "pizza"], ["first_date"], "Vodka pizza; easy and warm.", {}),
    ("Estela", "Nolita", 40.7240, -73.9949, "date_night_notable", 3, None, "resy",
     ["mediterranean", "small_plates"], ["first_date", "second_date"],
     "Small plates, wine-forward; lively but intimate.", {"intimacy": 0.7}),
    ("The Musket Room", "Nolita", 40.7224, -73.9955, "modern_tasting", 4, "1_star", "resy",
     ["modern", "tasting"], ["anniversary"], "Tasting + a la carte; garden.", {}),
    ("Balthazar", "Soho", 40.7227, -73.9985, "lively_bistro", 3, None, "opentable",
     ["french", "brasserie"], ["first_date"], "Iconic brasserie; loud and fun.",
     {"noise": 0.7, "ambiance": 0.78}),
    ("Raoul's", "Soho", 40.7259, -74.0009, "lively_bistro", 3, None, "resy",
     ["french", "bistro"], ["second_date"], "Steak au poivre; classic NY date spot.", {}),
    ("Tacombi", "Nolita", 40.7227, -73.9947, "casual_cool", 1, None, "walk_in",
     ["mexican", "tacos"], ["first_date"], "Casual tacos; low pressure.", {}),
    ("Pebble Bar", "Tribeca", 40.7155, -74.0098, "cocktail_bar_intimate", 3, None, "resy",
     ["cocktails"], ["first_date", "second_date"], "Multi-floor cocktail bar.", {}),
    ("Brandy Library", "Tribeca", 40.7188, -74.0095, "cocktail_bar_intimate", 3, None, "resy",
     ["cocktails", "whiskey"], ["second_date"], "Hushed, leather-bound; great for talking.",
     {"noise": 0.3, "intimacy": 0.85, "conversation": 0.8}),

    # ===================== WEST VILLAGE / GREENWICH =====================
    ("Via Carota", "West Village", 40.7338, -74.0027, "lively_bistro", 3, None, "walk_in",
     ["italian"], ["first_date", "second_date"], "No-res Italian; charming, walk-in.",
     {"ambiance": 0.82, "special_factor": 0.65}),
    ("I Sodi", "West Village", 40.7339, -74.0048, "date_night_notable", 3, None, "resy",
     ["italian", "tuscan"], ["second_date", "anniversary"], "Intimate Tuscan; hard res.",
     {"intimacy": 0.78}),
    ("L'Artusi", "West Village", 40.7345, -74.0066, "date_night_notable", 3, None, "resy",
     ["italian"], ["first_date", "second_date"], "Lively modern Italian; counter seats.",
     {"seating_counter": True}),
    ("Buvette", "West Village", 40.7338, -74.0030, "lively_bistro", 2, None, "walk_in",
     ["french", "cafe"], ["first_date"], "Tiny French cafe; cozy, walk-in.",
     {"intimacy": 0.7, "noise": 0.5}),
    ("One if by Land, Two if by Sea", "West Village", 40.7320, -74.0030, "romantic_special", 4, None, "opentable",
     ["american", "french"], ["anniversary", "proposal"], "Classic proposal spot; fireplaces.",
     {"privacy": 0.85, "special_factor": 0.92, "staff_coordination": 0.9}),
    ("Don Angie", "West Village", 40.7390, -74.0048, "date_night_notable", 3, None, "resy",
     ["italian"], ["second_date", "anniversary"], "Italian-American; chrysanthemum salad.", {}),
    ("Anton's", "West Village", 40.7349, -74.0066, "lively_bistro", 3, None, "resy",
     ["american", "bistro"], ["second_date"], "Warm neighborhood bistro.", {}),
    ("4 Charles Prime Rib", "West Village", 40.7351, -74.0021, "date_night_notable", 4, None, "resy",
     ["steakhouse"], ["second_date"], "Tiny clubby steakhouse; very hard res.",
     {"intimacy": 0.75, "noise": 0.55}),
    ("Blue Hill", "Greenwich Village", 40.7320, -73.9990, "modern_tasting", 4, "1_star", "resy",
     ["american", "farm"], ["anniversary"], "Farm-to-table tasting.", {}),
    ("Katana Kitten", "West Village", 40.7349, -74.0066, "cocktail_bar_intimate", 2, None, "walk_in",
     ["cocktails", "japanese"], ["first_date"], "Japanese-American cocktails; fun.", {}),
    ("Employees Only", "West Village", 40.7339, -74.0060, "cocktail_bar_intimate", 3, None, "resy",
     ["cocktails"], ["second_date"], "Speakeasy-style; lively late.", {"noise": 0.6}),
    ("The Ten Bells", "Lower East Side", 40.7180, -73.9905, "wine_bar", 2, None, "walk_in",
     ["wine", "tapas"], ["first_date", "second_date"], "Candle-lit natural wine bar.",
     {"intimacy": 0.8, "noise": 0.45}),
    ("Hudson River Greenway", "West Village", 40.7300, -74.0110, "walk", 1, None, "walk_in",
     ["walk", "waterfront"], ["first_date", "anniversary"], "Riverside walk at sunset.", {}),
    ("Washington Square Park", "Greenwich Village", 40.7308, -73.9973, "walk", 1, None, "walk_in",
     ["walk", "park"], ["first_date"], "Iconic arch; people-watching.", {}),

    # ===================== EAST VILLAGE / LES =====================
    ("Cosme", "Flatiron", 40.7397, -73.9897, "date_night_notable", 4, None, "resy",
     ["mexican", "modern"], ["second_date", "anniversary"], "Modern Mexican; husk meringue.", {}),
    ("Cafe Mogador", "East Village", 40.7263, -73.9849, "casual_cool", 2, None, "walk_in",
     ["moroccan", "mediterranean"], ["first_date"], "Long-running, easy, lively.", {}),
    ("Lavender Lake", "Gowanus", 40.6760, -73.9920, "casual_cool", 2, None, "walk_in",
     ["american", "bar"], ["first_date"], "Relaxed bar w/ backyard.", {}),
    ("Wayla", "Lower East Side", 40.7170, -73.9905, "date_night_notable", 3, None, "resy",
     ["thai"], ["first_date", "second_date"], "Vibrant Thai; good for sharing.", {}),
    ("Kru", "Williamsburg", 40.7140, -73.9530, "modern_tasting", 4, "1_star", "resy",
     ["thai", "tasting"], ["anniversary"], "Refined Thai tasting.", {}),
    ("Contra", "Lower East Side", 40.7195, -73.9905, "modern_tasting", 3, None, "resy",
     ["modern", "tasting"], ["second_date", "anniversary"], "Creative tasting; wine.", {}),
    ("Dirt Candy", "Lower East Side", 40.7185, -73.9905, "date_night_notable", 3, None, "resy",
     ["vegetarian"], ["second_date"], "Inventive vegetarian.",
     {"_dietary": {"vegetarian": True, "vegan": True, "gluten_free": True}}),
    ("Avant Garden", "East Village", 40.7263, -73.9839, "date_night_notable", 3, None, "resy",
     ["vegan", "vegetarian"], ["second_date", "first_date"], "Elegant vegan small plates.",
     {"_dietary": {"vegetarian": True, "vegan": True, "gluten_free": True}, "intimacy": 0.7}),
    ("Attaboy", "Lower East Side", 40.7185, -73.9912, "cocktail_bar_intimate", 3, None, "walk_in",
     ["cocktails"], ["first_date", "second_date"], "No menu, bartender's choice; intimate.",
     {"intimacy": 0.85}),
    ("Please Don't Tell", "East Village", 40.7265, -73.9839, "cocktail_bar_intimate", 3, None, "phone_only",
     ["cocktails"], ["second_date"], "Phone-booth entry speakeasy.", {}),
    ("Angel's Share", "East Village", 40.7290, -73.9890, "cocktail_bar_intimate", 3, None, "walk_in",
     ["cocktails", "japanese"], ["first_date"], "Hidden Japanese cocktail bar.", {}),
    ("Veniero's", "East Village", 40.7283, -73.9836, "dessert", 1, None, "walk_in",
     ["dessert", "italian"], ["first_date"], "Historic pastry shop; cannoli.", {}),
    ("Chikalicious Dessert Bar", "East Village", 40.7298, -73.9876, "dessert", 2, None, "walk_in",
     ["dessert"], ["first_date", "second_date"], "Dessert tasting at a counter.",
     {"seating_counter": True, "special_factor": 0.65}),

    # ===================== FLATIRON / GRAMERCY / NOMAD / UNION SQ =====================
    ("Eleven Madison Park", "Flatiron", 40.7416, -73.9872, "fine_dining_temple", 4, "3_star", "resy",
     ["plant_based", "tasting"], ["anniversary", "proposal"], "Plant-based 3-star tasting.",
     {"_dietary": {"vegetarian": True, "vegan": True, "gluten_free": True}, "view": 0.3}),
    ("Gramercy Tavern", "Flatiron", 40.7385, -73.9882, "romantic_special", 4, "1_star", "resy",
     ["american"], ["anniversary", "business"], "Warm icon; tavern + dining room.",
     {"special_factor": 0.85}),
    ("Cote", "Flatiron", 40.7400, -73.9905, "date_night_notable", 4, "1_star", "resy",
     ["korean", "steakhouse"], ["second_date", "anniversary"], "Korean steakhouse; lively.",
     {"noise": 0.55}),
    ("Gabriel Kreuther", "Midtown", 40.7540, -73.9840, "fine_dining_temple", 4, "2_star", "resy",
     ["french", "alsatian"], ["anniversary"], "Elegant Alsatian; refined.", {}),
    ("The Clocktower", "Flatiron", 40.7415, -73.9885, "romantic_special", 4, None, "opentable",
     ["british", "american"], ["anniversary", "business"], "Handsome dining rooms.", {}),
    ("Atomix", "NoMad", 40.7440, -73.9840, "modern_tasting", 4, "2_star", "tock",
     ["korean", "tasting"], ["anniversary"], "Counter Korean tasting; cards explain courses.", {}),
    ("Atoboy", "NoMad", 40.7445, -73.9850, "date_night_notable", 3, None, "resy",
     ["korean"], ["first_date", "second_date"], "Casual sibling of Atomix; prix fixe.", {}),
    ("Casa Mono", "Gramercy", 40.7370, -73.9870, "date_night_notable", 3, "1_star", "resy",
     ["spanish", "tapas"], ["first_date", "second_date"], "Cozy Spanish tapas; counter.",
     {"seating_counter": True, "intimacy": 0.7}),
    ("Eleven Madison Bar", "Flatiron", 40.7416, -73.9872, "cocktail_bar_intimate", 4, None, "resy",
     ["cocktails"], ["anniversary"], "Bar room at EMP; refined.", {}),
    ("Raines Law Room", "Chelsea", 40.7400, -73.9960, "cocktail_bar_intimate", 3, None, "walk_in",
     ["cocktails"], ["first_date", "second_date"], "Plush hidden lounge; intimate.",
     {"intimacy": 0.85, "noise": 0.35}),
    ("Madison Square Park", "Flatiron", 40.7424, -73.9880, "walk", 1, None, "walk_in",
     ["walk", "park"], ["first_date"], "Leafy park; Shake Shack nearby.", {}),
    ("Eataly Lavazza Cafe", "Flatiron", 40.7421, -73.9897, "dessert", 2, None, "walk_in",
     ["dessert", "coffee", "gelato"], ["first_date"], "Gelato/coffee; casual.", {}),

    # ===================== MIDTOWN =====================
    ("Le Bernardin", "Midtown", 40.7615, -73.9818, "fine_dining_temple", 4, "3_star", "opentable",
     ["seafood", "french"], ["anniversary", "business", "proposal"], "Pinnacle seafood 3-star.",
     {"staff_coordination": 0.95}),
    ("Per Se", "Columbus Circle", 40.7681, -73.9830, "fine_dining_temple", 4, "3_star", "tock",
     ["american", "french"], ["anniversary", "proposal"], "Keller's 3-star; Central Park views.",
     {"view": 0.8, "special_factor": 0.99}),
    ("The Modern", "Midtown", 40.7615, -73.9776, "romantic_special", 4, "2_star", "resy",
     ["american", "french"], ["anniversary", "business"], "MoMA views; bar room + dining room.",
     {"view": 0.6, "special_factor": 0.9}),
    ("Aquavit", "Midtown", 40.7587, -73.9720, "fine_dining_temple", 4, "2_star", "resy",
     ["scandinavian"], ["anniversary", "business"], "Refined Nordic.", {}),
    ("Masa", "Columbus Circle", 40.7685, -73.9830, "omakase_counter", 4, "3_star", "resy",
     ["sushi", "omakase"], ["anniversary", "proposal"], "Ultra-premium sushi counter.",
     {"special_factor": 0.99, "price_tier_note": "highest"}),
    ("Sushi Ginza Onodera", "Midtown", 40.7610, -73.9740, "omakase_counter", 4, "1_star", "resy",
     ["sushi", "omakase"], ["anniversary"], "Edomae omakase counter.", {}),
    ("Jean-Georges", "Columbus Circle", 40.7690, -73.9817, "fine_dining_temple", 4, "2_star", "resy",
     ["french"], ["anniversary", "business", "proposal"], "Park-view fine dining.",
     {"view": 0.55}),
    ("Aska_placeholder_skip", "Midtown", 40.7600, -73.9800, "casual_cool", 2, None, "walk_in",
     ["american"], ["first_date"], "REMOVE", {"_skip": True}),
    ("Keens Steakhouse", "Midtown", 40.7505, -73.9870, "romantic_special", 4, None, "opentable",
     ["steakhouse"], ["business", "anniversary"], "Historic clubby steakhouse.",
     {"special_factor": 0.8, "intimacy": 0.6}),
    ("The Grill", "Midtown", 40.7585, -73.9720, "romantic_special", 4, None, "resy",
     ["american", "steakhouse"], ["business", "anniversary"], "Iconic power-dining room.",
     {"special_factor": 0.88, "ambiance": 0.95}),
    ("Bar SixtyFive", "Midtown", 40.7592, -73.9794, "hotel_bar_view", 4, None, "resy",
     ["cocktails"], ["anniversary", "proposal"], "Rainbow Room bar; skyline views.", {}),
    ("The Campbell", "Midtown", 40.7527, -73.9772, "cocktail_bar_intimate", 3, None, "walk_in",
     ["cocktails"], ["second_date", "business"], "Grand Central jewel-box bar.",
     {"ambiance": 0.9}),
    ("The Crown", "Midtown East", 40.7570, -73.9690, "hotel_bar_view", 4, None, "resy",
     ["cocktails"], ["anniversary"], "Rooftop views.", {}),
    ("Lady M", "Midtown East", 40.7610, -73.9690, "dessert", 3, None, "walk_in",
     ["dessert", "cake"], ["second_date"], "Mille crepe cakes; elegant.", {}),
    ("Central Park (Bethesda Terrace)", "Central Park", 40.7740, -73.9710, "walk", 1, None, "walk_in",
     ["walk", "park"], ["first_date", "anniversary", "proposal"], "Romantic terrace + fountain.",
     {"special_factor": 0.8}),

    # ===================== UPPER EAST / WEST =====================
    ("Daniel", "Upper East Side", 40.7645, -73.9670, "fine_dining_temple", 4, "2_star", "resy",
     ["french"], ["anniversary", "proposal", "business"], "Boulud flagship; jacket suggested.",
     {"formality": 0.92}),
    ("Cafe Boulud", "Upper East Side", 40.7710, -73.9640, "romantic_special", 4, None, "resy",
     ["french"], ["anniversary"], "Refined, quieter Boulud.", {}),
    ("Bemelmans Bar", "Upper East Side", 40.7762, -73.9640, "cocktail_bar_intimate", 4, None, "walk_in",
     ["cocktails"], ["second_date", "anniversary"], "Carlyle classic; live piano, murals.",
     {"ambiance": 0.95, "special_factor": 0.85, "intimacy": 0.75}),
    ("Tanoshi Sushi", "Upper East Side", 40.7700, -73.9510, "omakase_counter", 3, None, "resy",
     ["sushi", "omakase"], ["first_date", "second_date"], "Tiny BYOB omakase counter.",
     {"intimacy": 0.8, "price_tier": 3}),
    ("The Loeb Boathouse area", "Central Park", 40.7757, -73.9690, "walk", 1, None, "walk_in",
     ["walk", "park"], ["anniversary"], "Lakeside stroll.", {}),

    # ===================== BROOKLYN: WILLIAMSBURG / DUMBO / FT GREENE =====================
    ("Lilia", "Williamsburg", 40.7180, -73.9520, "date_night_notable", 3, None, "resy",
     ["italian"], ["second_date", "anniversary"], "Missy Robbins pasta; very hard res.",
     {"special_factor": 0.82}),
    ("Misi", "Williamsburg", 40.7220, -73.9650, "date_night_notable", 3, None, "resy",
     ["italian", "pasta"], ["first_date", "second_date"], "Pasta + veg; airy room.", {}),
    ("Aska", "Williamsburg", 40.7110, -73.9660, "modern_tasting", 4, "2_star", "tock",
     ["scandinavian", "tasting"], ["anniversary"], "Nordic tasting in a townhouse.", {}),
    ("Francie", "Williamsburg", 40.7140, -73.9610, "modern_tasting", 4, "1_star", "resy",
     ["american", "european"], ["anniversary", "second_date"], "Elegant; duck for two.", {}),
    ("Oxomoco", "Greenpoint", 40.7300, -73.9540, "date_night_notable", 3, "1_star", "resy",
     ["mexican"], ["first_date", "second_date"], "Wood-fired Mexican; garden vibe.", {}),
    ("Roman's", "Fort Greene", 40.6880, -73.9660, "lively_bistro", 3, None, "resy",
     ["italian"], ["first_date"], "Daily-changing Italian; warm.", {}),
    ("Olmsted", "Prospect Heights", 40.6770, -73.9700, "date_night_notable", 3, None, "resy",
     ["american"], ["first_date", "second_date"], "Backyard garden; playful.", {}),
    ("The River Café", "Dumbo", 40.7038, -73.9960, "romantic_special", 4, None, "opentable",
     ["american"], ["anniversary", "proposal"], "Waterfront under Brooklyn Bridge; jacket.",
     {"view": 0.95, "special_factor": 0.95, "formality": 0.85, "staff_coordination": 0.9}),
    ("Cecconi's Dumbo", "Dumbo", 40.7028, -73.9905, "date_night_notable", 3, None, "resy",
     ["italian"], ["second_date"], "Bridge views; buzzy Italian.", {"view": 0.5}),
    ("Sushi Katsuei", "Park Slope", 40.6700, -73.9810, "omakase_counter", 3, None, "resy",
     ["sushi", "omakase"], ["first_date", "second_date"], "Approachable omakase.",
     {"price_tier": 3}),
    ("Maison Premiere", "Williamsburg", 40.7155, -73.9620, "cocktail_bar_intimate", 3, None, "walk_in",
     ["cocktails", "oysters"], ["first_date", "second_date"], "Absinthe + oysters; gorgeous.",
     {"ambiance": 0.88, "special_factor": 0.7}),
    ("The Ides Bar", "Williamsburg", 40.7220, -73.9580, "hotel_bar_view", 3, None, "walk_in",
     ["cocktails"], ["first_date", "anniversary"], "Wythe Hotel rooftop; Manhattan skyline.", {}),
    ("Westlight", "Williamsburg", 40.7220, -73.9575, "hotel_bar_view", 3, None, "walk_in",
     ["cocktails"], ["second_date", "anniversary"], "22nd-floor skyline views.", {}),
    ("Van Leeuwen Ice Cream", "Williamsburg", 40.7140, -73.9610, "dessert", 1, None, "walk_in",
     ["dessert", "ice_cream"], ["first_date"], "Ice cream; easy stroll stop.", {}),
    ("Brooklyn Bridge Park Promenade", "Dumbo", 40.7020, -73.9960, "walk", 1, None, "walk_in",
     ["walk", "waterfront"], ["first_date", "anniversary", "proposal"],
     "Skyline views; Jane's Carousel.", {"special_factor": 0.85}),
    ("Williamsburg Waterfront (Domino Park)", "Williamsburg", 40.7140, -73.9680, "walk", 1, None, "walk_in",
     ["walk", "waterfront"], ["first_date"], "Riverside park; sunset over Manhattan.", {}),

    # ===================== MORE DINNERS (fill tiers) =====================
    ("Crown Shy", "FiDi", 40.7065, -74.0080, "date_night_notable", 3, "1_star", "resy",
     ["american"], ["first_date", "second_date", "business"], "Approachable in a landmark building.", {}),
    ("SAGA", "FiDi", 40.7065, -74.0078, "modern_tasting", 4, "2_star", "tock",
     ["american", "tasting"], ["anniversary"], "Top-floor tasting; city views.", {"view": 0.7}),
    ("Manhatta", "FiDi", 40.7075, -74.0090, "romantic_special", 4, None, "resy",
     ["american"], ["anniversary", "proposal", "business"], "60th-floor sweeping views.",
     {"view": 0.9, "special_factor": 0.88}),
    ("Sushi Nakazawa", "West Village", 40.7330, -74.0040, "omakase_counter", 4, None, "resy",
     ["sushi", "omakase"], ["anniversary", "second_date"], "Famed omakase counter.",
     {"special_factor": 0.9}),
    ("Sushi Noz", "Upper East Side", 40.7720, -73.9560, "omakase_counter", 4, "1_star", "tock",
     ["sushi", "omakase"], ["anniversary"], "Hinoki counter; Edomae.", {}),
    ("Torien", "East Village", 40.7270, -73.9840, "omakase_counter", 4, "1_star", "tock",
     ["yakitori", "tasting"], ["second_date", "anniversary"], "Yakitori omakase counter.",
     {"cuisine_note": "yakitori"}),
    ("Shion 69 Leonard Street", "Tribeca", 40.7170, -74.0040, "omakase_counter", 4, "1_star", "tock",
     ["sushi", "omakase"], ["anniversary"], "Premium sushi counter.", {}),
    ("Noz 17", "Chelsea", 40.7430, -74.0050, "omakase_counter", 4, None, "tock",
     ["sushi", "seafood"], ["anniversary"], "Seafood-forward counter.", {}),
    ("Tatiana", "Lincoln Center", 40.7720, -73.9830, "date_night_notable", 4, "1_star", "resy",
     ["caribbean", "american"], ["second_date", "anniversary"], "Kwame Onwuachi; very hard res.",
     {"special_factor": 0.85, "noise": 0.55}),
    ("Rezdôra", "Flatiron", 40.7380, -73.9890, "date_night_notable", 3, "1_star", "resy",
     ["italian", "pasta"], ["first_date", "second_date"], "Emilia-Romagna pasta tasting.", {}),
    ("Hav & Mar", "Chelsea", 40.7470, -74.0050, "date_night_notable", 3, None, "resy",
     ["seafood", "scandinavian"], ["second_date"], "Marcus Samuelsson seafood.", {}),
    ("Cull & Pistol", "Chelsea", 40.7425, -74.0060, "casual_cool", 2, None, "resy",
     ["seafood"], ["first_date"], "Chelsea Market seafood; casual.", {}),
    ("Sip & Guzzle", "Greenwich Village", 40.7330, -74.0010, "cocktail_bar_intimate", 3, None, "walk_in",
     ["cocktails"], ["first_date", "second_date"], "Two-floor cocktail bar.", {}),
    ("Dante", "Greenwich Village", 40.7295, -74.0010, "cocktail_bar_intimate", 3, None, "resy",
     ["cocktails", "italian"], ["first_date", "second_date"], "Negronis; World's Best Bar alum.",
     {"special_factor": 0.7}),
    ("Levain Bakery", "Upper West Side", 40.7790, -73.9800, "dessert", 1, None, "walk_in",
     ["dessert", "cookies"], ["first_date"], "Famous cookies; grab-and-walk.", {}),
    ("Dominique Ansel Bakery", "Soho", 40.7255, -74.0030, "dessert", 2, None, "walk_in",
     ["dessert", "bakery"], ["first_date"], "Cronut creator; treats.", {}),
    ("The High Line", "Chelsea", 40.7480, -74.0048, "walk", 1, None, "walk_in",
     ["walk", "park"], ["first_date", "second_date"], "Elevated garden walk.", {}),
    ("Pier i / Riverside", "Upper West Side", 40.7790, -73.9880, "walk", 1, None, "walk_in",
     ["walk", "waterfront"], ["first_date"], "Hudson sunset walk.", {}),
]


def expand(rec):
    (name, hood, lat, lng, arch, price, mich, plat, cuisine, good_for, notes, ov) = rec
    if ov.get("_skip"):
        return None
    base = dict(A[arch])
    dietary = ov.pop("_dietary", {"vegetarian": False, "vegan": False, "gluten_free": False})
    # apply tag overrides
    for k, v in ov.items():
        if k in base:
            base[k] = v
    if "price_tier" in ov:
        price = ov["price_tier"]
    tags = {
        "noise": base["noise"], "conversation": base["conversation"],
        "intimacy": base["intimacy"], "ambiance": base["ambiance"],
        "formality": base["formality"], "special_factor": base["special_factor"],
        "duration_min": base["duration_min"], "seating_counter": base["seating_counter"],
        "fixed_menu": base["fixed_menu"], "privacy": base["privacy"],
        "staff_coordination": base["staff_coordination"],
        "central_transit": base["central_transit"], "view": base["view"],
    }
    return {
        "name": name, "city": "NYC", "neighborhood": hood,
        "lat": lat, "lng": lng, "cuisine": cuisine,
        "price_tier": price, "michelin": mich,
        "role": ROLE_BY_ARCHETYPE[arch], "archetype": arch,
        "booking": {"platform": plat, "url_template": None,
                    "requires_deposit": plat == "tock"},
        "tags": tags, "good_for": good_for, "dietary": dietary,
        "notes": notes, "sources": ["knowledge_seed"], "verified": False,
        # filled by scripts/fetch_photos.py (Google Places); null until then.
        "photo_url": None, "photo_credit": None,
    }


def main():
    venues, seen = [], set()
    for i, rec in enumerate(V):
        v = expand(rec)
        if v is None:
            continue
        key = v["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        v["id"] = f"venue_{len(venues)+1:03d}"
        # reorder id first
        venues.append({"id": v.pop("id"), **v})
    out = os.path.join(os.path.dirname(__file__), "..", "data", "nyc_venues.json")
    out = os.path.abspath(out)
    with open(out, "w") as f:
        json.dump(venues, f, indent=2, ensure_ascii=False)
    # --- summary ---
    from collections import Counter
    roles = Counter(r for v in venues for r in v["role"])
    hoods = Counter(v["neighborhood"] for v in venues)
    tiers = Counter(v["price_tier"] for v in venues)
    mich = Counter(v["michelin"] for v in venues if v["michelin"])
    print(f"wrote {len(venues)} venues -> {out}")
    print("roles:", dict(roles))
    print("price_tier:", dict(sorted(tiers.items())))
    print("michelin:", dict(mich))
    print("neighborhoods:", len(hoods))


if __name__ == "__main__":
    main()
