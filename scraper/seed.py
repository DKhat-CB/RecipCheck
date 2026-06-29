"""Phase-1 seed institutions for the Bay Area and NYC metros.

This is the crawl frontier, NOT truth: the pipeline determines current program
membership, pricing, and whether each site still operates. Coordinates are hand-verified
(small, well-known set) so the pipeline does not depend on a live geocoder.

`believed_programs` is a Tier-1 hint only. The authoritative per-tier program mapping is
produced by Tier-2 extraction (scraper/extract.py) and cross-checked in scraper/validate.py.

`reciprocity_overrides` carries per-institution resolved reciprocity_type for `varies`
programs (mainly AZA zoos/aquariums, which are frequently 50%-off rather than free).
"""
from __future__ import annotations

# Each entry: id, name, metro, address, lat, lng, membership_url, believed_programs,
# optional flags, optional reciprocity_overrides {program: type}.
SEED_INSTITUTIONS = [
    # ---------------------------------------------------------------- Bay Area
    {
        "id": "sf-exploratorium", "name": "Exploratorium", "metro": "bay_area",
        "address": "Pier 15, San Francisco, CA 94111", "lat": 37.8017, "lng": -122.3973,
        "membership_url": "https://www.exploratorium.edu/visit/membership",
        "believed_programs": ["ASTC"],
        "flags": ["non_participating"],
        "notes": "Spec edge case: historically has not honored reciprocal admission; verify and treat on own economics.",
    },
    {
        "id": "sf-cal-academy", "name": "California Academy of Sciences", "metro": "bay_area",
        "address": "55 Music Concourse Dr, San Francisco, CA 94118", "lat": 37.7699, "lng": -122.4661,
        "membership_url": "https://www.calacademy.org/membership",
        "believed_programs": ["ASTC"],
        "flags": ["non_participating"],
        "notes": "Spec edge case: historically has not honored reciprocal admission; verify and treat on own economics.",
    },
    {
        "id": "sf-famsf", "name": "Fine Arts Museums of San Francisco (de Young + Legion of Honor)",
        "metro": "bay_area", "address": "50 Hagiwara Tea Garden Dr, San Francisco, CA 94118",
        "lat": 37.7715, "lng": -122.4687,
        "membership_url": "https://www.famsf.org/join",
        "believed_programs": ["NARM"],
    },
    {
        "id": "sf-sfmoma", "name": "SFMOMA", "metro": "bay_area",
        "address": "151 Third St, San Francisco, CA 94103", "lat": 37.7857, "lng": -122.4011,
        "membership_url": "https://www.sfmoma.org/join-give/membership/",
        "believed_programs": ["MARP"],
        "notes": "Spec: reciprocity runs through MARP (in phase-1 scope); should resolve as covered.",
    },
    {
        "id": "sj-sjma", "name": "San Jose Museum of Art", "metro": "bay_area",
        "address": "110 S Market St, San Jose, CA 95113", "lat": 37.3327, "lng": -121.8901,
        "membership_url": "https://sjmusart.org/membership",
        "believed_programs": ["NARM"],
    },
    {
        "id": "oak-omca", "name": "Oakland Museum of California", "metro": "bay_area",
        "address": "1000 Oak St, Oakland, CA 94607", "lat": 37.7975, "lng": -122.2637,
        "membership_url": "https://museumca.org/membership/",
        "believed_programs": ["NARM"],
    },
    {
        "id": "sj-tech", "name": "The Tech Interactive", "metro": "bay_area",
        "address": "201 S Market St, San Jose, CA 95113", "lat": 37.3318, "lng": -121.8901,
        "membership_url": "https://www.thetech.org/membership/",
        "believed_programs": ["ASTC"],
    },
    {
        "id": "sj-cdm", "name": "Children's Discovery Museum of San Jose", "metro": "bay_area",
        "address": "180 Woz Way, San Jose, CA 95110", "lat": 37.3297, "lng": -121.8907,
        "membership_url": "https://www.cdm.org/membership/",
        "believed_programs": ["ACM", "ASTC"],
    },
    {
        "id": "sau-badm", "name": "Bay Area Discovery Museum", "metro": "bay_area",
        "address": "557 McReynolds Rd, Sausalito, CA 94965", "lat": 37.8327, "lng": -122.4793,
        "membership_url": "https://bayareadiscoverymuseum.org/membership",
        "believed_programs": ["ACM"],
    },
    {
        "id": "oak-chabot", "name": "Chabot Space & Science Center", "metro": "bay_area",
        "address": "10000 Skyline Blvd, Oakland, CA 94619", "lat": 37.8186, "lng": -122.1817,
        "membership_url": "https://chabotspace.org/membership/",
        "believed_programs": ["ASTC"],
    },
    {
        "id": "berk-lhs", "name": "Lawrence Hall of Science", "metro": "bay_area",
        "address": "1 Centennial Dr, Berkeley, CA 94720", "lat": 37.8791, "lng": -122.2459,
        "membership_url": "https://www.lawrencehallofscience.org/visit/membership",
        "believed_programs": ["ASTC"],
    },
    {
        "id": "berk-ucbg", "name": "UC Berkeley Botanical Garden", "metro": "bay_area",
        "address": "200 Centennial Dr, Berkeley, CA 94720", "lat": 37.8757, "lng": -122.2385,
        "membership_url": "https://botanicalgarden.berkeley.edu/membership",
        "believed_programs": ["AHS"],
    },
    {
        "id": "sf-asian", "name": "Asian Art Museum", "metro": "bay_area",
        "address": "200 Larkin St, San Francisco, CA 94102", "lat": 37.7801, "lng": -122.4163,
        "membership_url": "https://asianart.org/membership/",
        "believed_programs": ["NARM"],
    },
    {
        "id": "oak-zoo", "name": "Oakland Zoo", "metro": "bay_area",
        "address": "9777 Golf Links Rd, Oakland, CA 94605", "lat": 37.7510, "lng": -122.1467,
        "membership_url": "https://www.oaklandzoo.org/membership",
        "believed_programs": ["AZA"],
        "reciprocity_overrides": {"AZA": "fifty_percent"},
    },
    {
        "id": "sf-zoo", "name": "San Francisco Zoo & Gardens", "metro": "bay_area",
        "address": "Sloat Blvd & Great Hwy, San Francisco, CA 94132", "lat": 37.7325, "lng": -122.5025,
        "membership_url": "https://www.sfzoo.org/membership/",
        "believed_programs": ["AZA"],
        "reciprocity_overrides": {"AZA": "fifty_percent"},
    },
    {
        "id": "mont-mba", "name": "Monterey Bay Aquarium", "metro": "bay_area",
        "address": "886 Cannery Row, Monterey, CA 93940", "lat": 36.6182, "lng": -121.9018,
        "membership_url": "https://www.montereybayaquarium.org/membership",
        "believed_programs": ["AZA"],
        "reciprocity_overrides": {"AZA": "fifty_percent"},
        "notes": "~75mi from SF, inside the 80mi frontier. Reciprocity via AZA is typically 50%, not free.",
    },
    {
        "id": "wood-filoli", "name": "Filoli", "metro": "bay_area",
        "address": "86 Canada Rd, Woodside, CA 94062", "lat": 37.4699, "lng": -122.3186,
        "membership_url": "https://filoli.org/membership/",
        "believed_programs": ["AHS", "NARM"],
    },

    # ---------------------------------------------------------------- NYC
    {
        "id": "ny-met", "name": "The Metropolitan Museum of Art", "metro": "nyc",
        "address": "1000 5th Ave, New York, NY 10028", "lat": 40.7794, "lng": -73.9632,
        "membership_url": "https://www.metmuseum.org/join-and-give/membership",
        "believed_programs": [],
        "notes": "Historically not part of NARM/reciprocal networks; verify, likely join-direct only.",
    },
    {
        "id": "ny-moma", "name": "Museum of Modern Art", "metro": "nyc",
        "address": "11 W 53rd St, New York, NY 10019", "lat": 40.7614, "lng": -73.9776,
        "membership_url": "https://www.moma.org/membership/",
        "believed_programs": [],
        "notes": "Historically not in reciprocal networks; verify.",
    },
    {
        "id": "ny-whitney", "name": "Whitney Museum of American Art", "metro": "nyc",
        "address": "99 Gansevoort St, New York, NY 10014", "lat": 40.7396, "lng": -74.0089,
        "membership_url": "https://whitney.org/membership",
        "believed_programs": [],
        "notes": "Verify reciprocal participation.",
    },
    {
        "id": "ny-guggenheim", "name": "Solomon R. Guggenheim Museum", "metro": "nyc",
        "address": "1071 5th Ave, New York, NY 10128", "lat": 40.7830, "lng": -73.9590,
        "membership_url": "https://www.guggenheim.org/membership",
        "believed_programs": ["NARM"],
    },
    {
        "id": "ny-amnh", "name": "American Museum of Natural History", "metro": "nyc",
        "address": "200 Central Park West, New York, NY 10024", "lat": 40.7813, "lng": -73.9740,
        "membership_url": "https://www.amnh.org/join-support/membership",
        "believed_programs": ["ASTC"],
        "notes": "Verify ASTC participation.",
    },
    {
        "id": "ny-brooklyn-museum", "name": "Brooklyn Museum", "metro": "nyc",
        "address": "200 Eastern Pkwy, Brooklyn, NY 11238", "lat": 40.6712, "lng": -73.9636,
        "membership_url": "https://www.brooklynmuseum.org/support/membership",
        "believed_programs": ["NARM"],
    },
    {
        "id": "ny-nyhs", "name": "New-York Historical Society", "metro": "nyc",
        "address": "170 Central Park West, New York, NY 10024", "lat": 40.7794, "lng": -73.9740,
        "membership_url": "https://www.nyhistory.org/membership",
        "believed_programs": ["NARM", "TIME_TRAVELERS"],
    },
    {
        "id": "ny-intrepid", "name": "Intrepid Museum", "metro": "nyc",
        "address": "Pier 86, W 46th St, New York, NY 10036", "lat": 40.7647, "lng": -74.0019,
        "membership_url": "https://www.intrepidmuseum.org/membership",
        "believed_programs": ["ASTC"],
        "notes": "Verify ASTC participation.",
    },
    {
        "id": "ny-bronx-zoo", "name": "Bronx Zoo (WCS)", "metro": "nyc",
        "address": "2300 Southern Blvd, Bronx, NY 10460", "lat": 40.8506, "lng": -73.8769,
        "membership_url": "https://bronxzoo.com/membership",
        "believed_programs": ["AZA"],
        "reciprocity_overrides": {"AZA": "fifty_percent"},
    },
    {
        "id": "ny-aquarium", "name": "New York Aquarium (WCS)", "metro": "nyc",
        "address": "602 Surf Ave, Brooklyn, NY 11224", "lat": 40.5755, "lng": -73.9707,
        "membership_url": "https://nyaquarium.com/membership",
        "believed_programs": ["AZA"],
        "reciprocity_overrides": {"AZA": "fifty_percent"},
    },
    {
        "id": "ny-nybg", "name": "New York Botanical Garden", "metro": "nyc",
        "address": "2900 Southern Blvd, Bronx, NY 10458", "lat": 40.8623, "lng": -73.8770,
        "membership_url": "https://www.nybg.org/membership/",
        "believed_programs": ["AHS"],
    },
    {
        "id": "ny-bbg", "name": "Brooklyn Botanic Garden", "metro": "nyc",
        "address": "990 Washington Ave, Brooklyn, NY 11225", "lat": 40.6694, "lng": -73.9626,
        "membership_url": "https://www.bbg.org/support/membership",
        "believed_programs": ["AHS"],
    },
    {
        "id": "ny-cmom", "name": "Children's Museum of Manhattan", "metro": "nyc",
        "address": "212 W 83rd St, New York, NY 10024", "lat": 40.7853, "lng": -73.9772,
        "membership_url": "https://cmom.org/membership/",
        "believed_programs": ["ACM"],
    },
    {
        "id": "ny-bcm", "name": "Brooklyn Children's Museum", "metro": "nyc",
        "address": "145 Brooklyn Ave, Brooklyn, NY 11213", "lat": 40.6743, "lng": -73.9436,
        "membership_url": "https://www.brooklynkids.org/membership/",
        "believed_programs": ["ACM"],
    },
    {
        "id": "ny-nysci", "name": "New York Hall of Science", "metro": "nyc",
        "address": "47-01 111th St, Corona, NY 11368", "lat": 40.7376, "lng": -73.8517,
        "membership_url": "https://nysci.org/membership/",
        "believed_programs": ["ASTC"],
    },
    {
        "id": "ny-cooper-hewitt", "name": "Cooper Hewitt, Smithsonian Design Museum", "metro": "nyc",
        "address": "2 E 91st St, New York, NY 10128", "lat": 40.7846, "lng": -73.9576,
        "membership_url": "https://www.cooperhewitt.org/membership/",
        "believed_programs": [],
        "notes": "Smithsonian; verify reciprocal participation.",
    },
    {
        "id": "ny-mcny", "name": "Museum of the City of New York", "metro": "nyc",
        "address": "1220 5th Ave, New York, NY 10029", "lat": 40.7926, "lng": -73.9518,
        "membership_url": "https://www.mcny.org/membership",
        "believed_programs": ["NARM"],
    },
    {
        "id": "ny-qbg", "name": "Queens Botanical Garden", "metro": "nyc",
        "address": "43-50 Main St, Flushing, NY 11355", "lat": 40.7512, "lng": -73.8267,
        "membership_url": "https://queensbotanical.org/membership/",
        "believed_programs": ["AHS"],
    },
    {
        "id": "ny-wave-hill", "name": "Wave Hill", "metro": "nyc",
        "address": "W 249th St & Independence Ave, Bronx, NY 10471", "lat": 40.8976, "lng": -73.9116,
        "membership_url": "https://www.wavehill.org/membership/",
        "believed_programs": ["AHS", "NARM"],
    },
]
