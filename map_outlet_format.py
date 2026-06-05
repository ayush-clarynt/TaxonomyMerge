#!/usr/bin/env python3
"""
Map each `place_type` in mumbai_type_dictionary.csv to an `outlet_format` code
from taxonomy_proposal.json (CRMC taxonomy) -- BUT ONLY for place types that are
a POINT OF SALE (a place where consumer goods are actually sold over the
counter). Anything that is not a point of sale (healthcare services,
professional/financial services, transport, civic, worship, education, leisure
venues, residential/lodging, manufacturing, offices, agencies, etc.) is left
BLANK in the outlet_format column.

outlet_format column semantics in the output:
    ""  (blank) -> NOT a point of sale
    OTH         -> IS a point of sale, but not one of the named retail formats
                   (e.g. clothing / electronics / jewellery / hardware stores)
    KIR/COS/...  -> point of sale of that specific format

Tiers (recorded per row in mapping_method):
  exact     - place_type is a direct synonym of a format.
  rule      - explicit token rule -> a named retail format (point of sale).
  non_pos   - explicit token rule -> blank (not a point of sale).
  rule(OTH) - explicit "is a goods store but unnamed format" -> OTH.
  embedding - residual/fuzzy value: real all-MiniLM-L6-v2 cosine similarity to
              the retail-format anchors; assign the nearest format if confident,
              else leave blank (treated as non-PoS).

Embedding tier uses sentence-transformers/all-MiniLM-L6-v2 when loadable (a
machine with HuggingFace access). Offline it falls back to a scikit-learn
char-n-gram TF-IDF vectoriser; mapping_method records which embedder ran.

Output columns added: outlet_format, mapping_method, mapping_reason, mapping_score
"""

import csv
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_IN  = os.environ.get("CSV_IN",  os.path.join(HERE, "mumbai_type_dictionary.csv"))
JSON_IN = os.environ.get("JSON_IN", os.path.join(HERE, "taxonomy_proposal_v5.json"))
CSV_OUT = os.environ.get("CSV_OUT", os.path.join(HERE, "mumbai_type_dictionary_mapped_v4.csv"))

EMB_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMB_THRESHOLD  = 0.30


def words(pt):
    return pt.replace("_", " ").strip().lower()


def _has(*toks):
    pats = []
    for t in toks:
        if t.endswith("*"):
            pats.append(re.compile(r"\b" + re.escape(t[:-1])))
        else:
            pats.append(re.compile(r"\b" + re.escape(t) + r"\b"))
    return lambda p: any(pat.search(p) for pat in pats)


def build_rules():
    # exact synonyms -> named formats (all are points of sale)
    exact = {
        "general_store": ("KIR", "exact: general store = Kirana/General/Provision (KIR)"),
        "grocery_store": ("KIR", "exact: grocery store = Kirana/provision retail (KIR)"),
        "food_store":    ("OTH", "exact: food_store = broad/ambiguous Google parent (grocery + prepared-food); Other (OTH)"),
        "supermarket":          ("SUP", "exact: supermarket (SUP)"),
        "discount_supermarket": ("SUP", "exact: discount supermarket (SUP)"),
        "hypermarket":          ("HYP", "exact: hypermarket (HYP)"),
        "convenience_store": ("CON", "exact: convenience store (CON)"),
        "department_store":  ("DEP", "exact: departmental store (DEP)"),
        "cosmetics_store":   ("COS", "exact: cosmetics store (COS)"),
        "beauty_salon":      ("SAL", "exact: beauty salon (SAL)"),
        "pharmacy":  ("CHE", "exact: pharmacy = Chemist/Pharmacy store (CHE)"),
        "drugstore": ("CHE", "exact: drugstore = Chemist/Pharmacy store (CHE)"),
        "book_store": ("STN", "exact: book store = Stationery & Books (STN)"),
        "ice_cream_shop": ("ICR", "exact: ice cream parlour (ICR)"),
        "spa":         ("SAL", "exact: spa (SAL)"),
        "hair_salon":  ("SAL", "exact: hair salon (SAL)"),
        "nail_salon":  ("SAL", "exact: nail salon (SAL)"),
        "barber_shop": ("SAL", "exact: barber shop = salon (SAL)"),
        # PoS that is a goods store but no named format -> OTH
        "garden_center": ("GRD", "exact: garden centre & nursery (GRD)"),
        "store":         ("OTH", "exact: generic store = unspecified goods, Other (OTH)"),
    }

    # forced non-PoS for tricky tokens that would otherwise be miscaught
    force_blank = {
        "internet_cafe": "non-PoS: internet/cyber cafe is a service, not a retail outlet",
        "cyber_cafe":    "non-PoS: cyber cafe is a service, not a retail outlet",
        "food_court":    None,  # placeholder (kept PoS) -- not used; see EAT
    }
    force_blank.pop("food_court")

    # ordered pipeline. code "" means "blank / not a point of sale".
    rules = [
        # ---- named retail formats (points of sale) ----
        ("ICR", "rule", "ice-cream / dessert parlour -> ICR",
         _has("ice cream", "gelato", "kulfi")),

        ("SAL", "rule", "salon / spa / grooming outlet -> SAL",
         _has("salon", "spa", "barber", "beauty", "nail", "hair care",
              "makeup artist", "beautician", "sauna", "tanning", "massage",
              "body art", "tattoo")),

        ("COS", "rule", "cosmetics / beauty retail -> COS",
         _has("cosmetic", "perfume", "fragrance")),

        # CHEMIST = chemist/pharmacy STORE only (NOT clinics/hospitals/doctors)
        ("CHE", "rule", "chemist / pharmacy store -> CHE",
         _has("pharmac*", "drugstore", "chemist", "medical store",
              "medical supply", "surgical store")),

        ("STN", "rule", "stationery / book store -> STN",
         _has("stationery", "book store", "bookstore", "office supply")),

        ("EAT", "rule", "eatery / restaurant / cafe / food-service outlet -> EAT",
         _has("restaurant", "cafe", "café", "coffee", "tea house", "tea room",
              "tea stall", "bakery", "bakeries", "bistro", "diner", "eatery",
              "eateries", "food court", "snack", "deli", "pub", "bar", "brewpub",
              "brewery", "gastropub", "pizzeria", "pizza", "burger", "hamburger",
              "noodle", "ramen", "sushi", "kebab", "shawarma", "falafel",
              "sandwich", "donut", "doughnut", "pastry", "cake shop", "dessert",
              "confectionery", "candy", "chocolate shop", "juice", "lounge",
              "steak", "buffet", "cafeteria", "canteen", "meal takeaway",
              "meal delivery", "food delivery", "catering", "tapas", "dim sum",
              "dumpling", "soup", "salad shop", "hot dog", "burrito", "taco",
              "fish and chips", "wings", "barbecue", "bar and grill",
              "coffee roastery", "coffee stand", "coffee shop", "winery",
              "wine bar", "cocktail", "hookah")),

        # ---- consumer-goods retail verticals (points of sale) ----
        ("FAS", "rule", "fashion / apparel store -> FAS",
         _has("clothing", "apparel", "garment", "fashion", "menswear",
              "womens wear", "kids wear", "sportswear", "lingerie", "saree",
              "boutique")),
        ("FTW", "rule", "footwear store -> FTW",
         _has("shoe", "footwear", "sneaker")),
        ("JWL", "rule", "jewellery & accessories store -> JWL",
         _has("jewelry", "jewellery", "jeweler", "jeweller")),
        ("ELC", "rule", "electronics & appliances store -> ELC",
         _has("electronics", "appliance", "computer store", "camera store")),
        ("MOB", "rule", "mobile & telecom retail -> MOB",
         _has("cell phone", "mobile phone", "mobile store", "phone store")),
        ("FUR", "rule", "furniture & furnishings store -> FUR",
         _has("furniture", "home goods", "furnishing", "mattress",
              "home decor", "home furnishing")),
        ("HDW", "rule", "hardware / building / home-improvement store -> HDW",
         _has("hardware", "building material*", "home improvement", "paint store",
              "tiles", "sanitary", "plywood")),
        ("AUT", "rule", "automotive dealer / parts / tyres -> AUT",
         _has("auto parts", "car dealer", "truck dealer", "tire", "tyre",
              "car accessories", "automobile", "motorcycle dealer")),
        ("SPG", "rule", "sports & outdoor goods store -> SPG",
         _has("sporting goods", "sports goods", "bicycle", "cycle store",
              "fitness equipment", "outdoor gear")),
        ("PET", "rule", "pet supplies store -> PET",
         _has("pet store", "pet shop", "pet supply")),
        ("TOY", "rule", "toys / games / hobby store -> TOY",
         _has("toy", "game store", "hobby shop")),
        ("GFT", "rule", "gifts / florist / cards -> GFT",
         _has("gift", "florist", "flower shop", "greeting card", "souvenir")),
        ("LIQ", "rule", "liquor / off-trade beverages -> LIQ",
         _has("liquor", "wine shop", "wine store", "beer", "alcohol", "spirits")),
        ("GRD", "rule", "garden centre & nursery -> GRD",
         _has("garden center", "garden centre", "nursery", "plant nursery")),

        ("HYP", "rule", "hypermarket -> HYP", _has("hypermarket")),
        ("SUP", "rule", "supermarket -> SUP", _has("supermarket")),
        ("CON", "rule", "convenience store -> CON", _has("convenience")),
        ("DEP", "rule", "department / mall retail -> DEP",
         _has("department store", "shopping mall", "warehouse store",
              "discount store", "thrift store", "flea market")),
        ("KIR", "rule", "grocery / provision / general-store retail -> KIR",
         _has("grocery", "general store", "provision", "food store",
              "butcher", "farmers market", "market")),
        ("FCY", "rule", "fancy / gift / variety store -> FCY",
         _has("fancy", "card shop", "novelty")),

        # ---- NON point-of-sale -> BLANK ----
        ("", "non_pos", "not a point of sale (service / institution / venue)",
         _has(
            # healthcare services
            "doctor", "dentist", "dental", "hospital", "clinic", "medical",
            "physio*", "chiro*", "veterinary", "foot care", "wellness",
            "diagnostic", "pathology", "nursing", "maternity", "optometr*",
            "rehabilitation", "blood bank",
            # professional / financial / business services
            "consultant", "consulting", "lawyer", "legal", "attorney",
            "advocate", "accounting", "accountant", "finance", "financial",
            "bank", "atm", "insurance", "real estate", "notary", "agency",
            "marketing", "employment", "recruit", "auditor", "service",
            # trades / home / auto services
            "contractor", "electrician", "plumber", "painter", "roofing",
            "carpenter", "locksmith", "moving company", "mover", "courier",
            "shipping", "logistics", "telecommunications", "car repair",
            "auto repair", "car wash", "rental", "repair", "chauffeur",
            "taxi", "parking", "laundry", "dry clean", "tailor", "storage",
            "pest control",
            # manufacturing / supply / office
            "manufacturer", "factory", "mill", "wholesaler", "wholesale",
            "supplier", "distributor", "warehouse", "corporate office",
            "office", "coworking", "business center", "industrial",
            # pet / child services
            "pet care", "pet boarding", "pet grooming", "child care",
            "day care",
            # travel / misc services
            "travel agency", "tour", "astrologer", "psychic", "photo",
            "printing",
            # residential / lodging
            "apartment", "housing", "condominium", "residential", "complex",
            "guest house", "guest room", "lodging", "hotel", "motel", "inn",
            "hostel", "resort", "cottage", "cabin", "bed and breakfast",
            "farmstay", "villa", "dormitory",
            # transport / civic / public
            "transit", "bus stop", "bus station", "train", "subway", "metro",
            "railway", "station", "depot", "airport", "heliport", "ferry",
            "marina", "park and ride", "toll", "rest stop", "charging station",
            "gas station", "fuel", "petrol", "shuttle", "aircraft",
            "government", "municipal", "police", "fire station", "embassy",
            "consulate", "courthouse", "city hall", "town hall", "post office",
            "library", "community center", "public bath", "bathroom",
            "restroom", "toilet",
            # worship / cultural / leisure venues
            "place of worship", "temple", "mosque", "church", "shrine",
            "synagogue", "gurudwara", "chapel", "cemetery", "graveyard",
            "funeral", "crematorium", "museum", "gallery", "theater",
            "theatre", "cinema", "auditorium", "concert", "stadium", "arena",
            "amphitheatre", "convention", "exhibition", "landmark", "monument",
            "memorial", "attraction", "tourist", "scenic", "visitor",
            "planetarium", "observatory", "zoo", "aquarium", "amusement",
            "water park", "arcade", "bowling", "golf", "go karting",
            "race course", "casino", "night club", "nightclub", "comedy",
            "performing arts", "studio", "television", "dance hall",
            "live music", "wedding venue", "banquet", "event venue",
            "summer camp", "childrens camp", "camp", "playground", "picnic",
            "plaza", "bridge", "sculpture", "fountain", "historical",
            "heritage", "cultural", "karaoke",
            # education / research
            "school", "preschool", "pre school", "university", "college",
            "institute", "academy", "academic", "tuition", "coaching",
            "education", "educational", "kindergarten", "training", "research",
            # sports / nature / outdoors
            "gym", "fitness", "yoga", "pilates", "crossfit", "martial arts",
            "swimming", "sports", "athletic", "tennis", "skating", "farm",
            "ranch", "stable", "vineyard", "nature", "preserve", "park",
            "forest", "hiking", "adventure", "off roading", "fishing",
            "campground", "camping", "cycling",
            # generic non-PoS catch
            "establishment", "point of interest", "association",
            "organization", "non profit", "ngo", "society", "club", "union",
            "federation")),

        # ---- IS a goods store but unnamed format -> OTH (point of sale) ----
        ("OTH", "rule", "goods store, unspecified vertical -> OTH (Other point of sale)",
         _has("store", "shop", "showroom", "dealer", "emporium", "mart",
              "bazaar", "bazar")),
    ]
    return exact, force_blank, rules


def classify(pt, exact, force_blank, rules):
    key = pt.strip().lower()
    if key in force_blank:
        return "", "non_pos", force_blank[key], ""
    if key in exact:
        code, reason = exact[key]
        return code, "exact", reason, ""
    phrase = words(pt)
    for code, method, reason, pred in rules:
        if pred(phrase):
            return code, method, reason, ""
    return None  # residual -> embedding


# ---------------- embedding tier ----------------
def load_embedder():
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMB_MODEL_NAME)

        def enc(texts):
            v = model.encode(list(texts), normalize_embeddings=True)
            return np.asarray(v, dtype=np.float32)
        return enc, "embed:%s" % EMB_MODEL_NAME
    except Exception as e:
        sys.stderr.write("[warn] %s unavailable (%s); using TF-IDF char n-gram "
                         "fallback.\n" % (EMB_MODEL_NAME, type(e).__name__))
        from sklearn.feature_extraction.text import TfidfVectorizer

        class _T:
            def __init__(self):
                self.v = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            def fit(self, c):
                self.v.fit(c)
            def encode(self, texts):
                m = self.v.transform(list(texts)).toarray().astype(np.float32)
                n = np.linalg.norm(m, axis=1, keepdims=True)
                n[n == 0] = 1.0
                return m / n
        return _T(), "embed:tfidf-char-ngram(offline-fallback)"


def format_anchors():
    return {
        "KIR": "kirana general provision grocery store food staples daily needs",
        "COS": "cosmetics beauty makeup skincare perfume fragrance retail store",
        "CHE": "chemist pharmacy drugstore medicine retail store",
        "STN": "stationery books pens paper office school supplies store",
        "SUP": "supermarket self service grocery retail chain",
        "HYP": "hypermarket very large supermarket big box retail",
        "DEP": "departmental store multi department apparel home shopping mall",
        "CON": "convenience store small quick neighbourhood shop",
        "FCY": "fancy store gifts toys decor novelty variety small items",
        "EAT": "eatery restaurant cafe coffee tea stall food bar diner",
        "ICR": "ice cream parlour gelato frozen dessert shop",
        "SAL": "salon spa hair beauty grooming massage outlet",
    }


def embedding_layer(residual_phrases, embedder, ename):
    threshold = 0.45 if "tfidf" in ename else EMB_THRESHOLD
    anchors = format_anchors()
    codes = list(anchors)
    texts = list(anchors.values())
    if hasattr(embedder, "fit"):
        embedder.fit(texts + list(residual_phrases))
        enc = embedder.encode
    else:
        enc = embedder
    cv = enc(texts)
    rv = enc(list(residual_phrases))
    sims = rv @ cv.T
    out = []
    for i in range(len(residual_phrases)):
        j = int(np.argmax(sims[i]))
        s = float(sims[i][j])
        if s < threshold:
            out.append(("", round(s, 3),
                        "%s: nearest='%s' cosine=%.3f < %.2f -> no PoS signal, "
                        "left blank" % (ename, codes[j], s, threshold)))
        else:
            out.append((codes[j], round(s, 3),
                        "%s: nearest format '%s' cosine=%.3f" % (ename, codes[j], s)))
    return out


def main():
    with open(JSON_IN, encoding="utf-8") as f:
        json.load(f)  # validate taxonomy is present/parseable

    with open(CSV_IN, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    exact, force_blank, rules = build_rules()
    results, residual = {}, []
    for r in rows:
        pt = r["place_type"]
        res = classify(pt, exact, force_blank, rules)
        if res is None:
            residual.append(pt)
        else:
            code, method, reason, score = res
            results[pt] = (code, method, reason, score)

    if residual:
        embedder, ename = load_embedder()
        for pt, (code, score, reason) in zip(
                residual, embedding_layer([words(p) for p in residual], embedder, ename)):
            results[pt] = (code, "embedding", reason, score)

    out_fields = fieldnames + ["outlet_format", "mapping_method",
                               "mapping_reason", "mapping_score"]
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r in rows:
            code, method, reason, score = results[r["place_type"]]
            r = dict(r)
            r.update(outlet_format=code, mapping_method=method,
                     mapping_reason=reason, mapping_score=score)
            w.writerow(r)

    from collections import Counter
    pos = sum(1 for v in results.values() if v[0] != "")
    blank = sum(1 for v in results.values() if v[0] == "")
    by_fmt = Counter(v[0] if v[0] else "(blank)" for v in results.values())
    by_method = Counter(v[1] for v in results.values())
    sys.stderr.write("\n=== summary ===\n")
    sys.stderr.write("rows: %d | point-of-sale: %d | blank(non-PoS): %d | residual: %d\n"
                     % (len(rows), pos, blank, len(residual)))
    sys.stderr.write("by method: %s\n" % _d(by_method))
    sys.stderr.write("by format: %s\n" % _d(by_fmt))
    sys.stderr.write("written -> %s\n" % CSV_OUT)


def _d(c):
    return ", ".join("%s=%s" % (k, v) for k, v in sorted(c.items(), key=lambda x: -x[1]))


if __name__ == "__main__":
    main()
