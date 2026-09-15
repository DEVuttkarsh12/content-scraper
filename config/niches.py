"""Pre-configured high-ticket niches with query templates.

Each niche defines the search queries used to discover businesses
and the keywords that mark a site as "in-niche" so we only keep
leads that match the target vertical.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Niche:
    id: str
    label: str
    search_queries: list = field(default_factory=list)
    scope_keywords: list = field(default_factory=list)
    exclusion_keywords: list = field(default_factory=list)


NICHES: dict[str, Niche] = {
    "real_estate": Niche(
        id="real_estate",
        label="Real Estate & Property Development",
        search_queries=[
            '"real estate agency" contact us',
            '"property development" company "contact"',
            '"real estate broker" "let\'s talk" OR "get in touch"',
            '"estate agents" "our offices"',
        ],
        scope_keywords=[
            "real estate", "property", "realtor", "realty",
            "estate agent", "brokerage", "condos", "villas",
        ],
        exclusion_keywords=[
            "for sale by owner", "rental listings aggregator",
            "property tax", "municipal corporation", "ward office",
        ],
    ),
    "finance": Niche(
        id="finance",
        label="Wealth Management & Finance",
        search_queries=[
            '"wealth management" firm "contact"',
            '"financial adviser" "email"',
            '"investment advisory" "office" "contact us"',
            '"private client" "asset management" "get in touch"',
        ],
        scope_keywords=[
            "wealth", "financial", "investment", "asset management",
            "private equity", "hedge fund", "estate planning",
            "financial planning", "advisory",
        ],
        exclusion_keywords=["student loans", "payday"],
    ),
    "healthcare": Niche(
        id="healthcare",
        label="Private Healthcare & Clinics",
        search_queries=[
            '"medical practice" "contact" "appointments"',
            '"cosmetic clinic" "book online"',
            '"dental practice" "contact us"',
            '"private clinic" "our doctors"',
        ],
        scope_keywords=[
            "clinic", "medical", "dentistry", "dental", "dermatology",
            "surgery center", "aesthetic", "med spa", "healthcare",
        ],
        exclusion_keywords=["government", "public hospital"],
    ),
    "legal": Niche(
        id="legal",
        label="Law Firms & Legal Services",
        search_queries=[
            '"law firm" "contact" "attorney"',
            '"corporate law" firms "office"',
            '"business lawyers" "get in touch"',
            '"legal" "firm" "approach us"',
        ],
        scope_keywords=[
            "law firm", "attorney", "lawyers", "legal", "solicitors",
            "barristers", "litigation", "counsel",
        ],
        exclusion_keywords=["legal aid", "pro bono"],
    ),
    "saas": Niche(
        id="saas",
        label="SaaS & Software Companies",
        search_queries=[
            '"software" "company" "contact sales"',
            '"saas" "platform" "talk to sales"',
            '"b2b" "software" "request a demo"',
            '"cloud" "solutions" "our team"',
        ],
        scope_keywords=[
            "software", "saas", "platform", "cloud", "solutions",
            "tech", "app", "api",
        ],
        exclusion_keywords=["freelance", "portfolio"],
    ),
    "ecommerce": Niche(
        id="ecommerce",
        label="E-commerce & D2C Brands",
        search_queries=[
            '"online store" "contact" "brand"',
            '"d2c" "brand" "contact us"',
            '"ecommerce" "shipping" "about us"',
            '"retail" "brand" "support"',
        ],
        scope_keywords=[
            "shop", "store", "brand", "d2c", "retail",
            "merchandise", "boutique",
        ],
        exclusion_keywords=["marketplace", "walmart", "amazon seller"],
    ),
    "coaching": Niche(
        id="coaching",
        label="High-Ticket Coaching & Consulting",
        search_queries=[
            '"business coach" "work with me"',
            '"executive coaching" "contact"',
            '"consulting" "our clients" "contact us"',
            '"mentorship" "program" "apply"',
        ],
        scope_keywords=[
            "coach", "consulting", "consultancy", "mentor",
            "training", "advisory",
        ],
        exclusion_keywords=["diet coach", "fitness coach"],
    ),
    "automotive": Niche(
        id="automotive",
        label="Luxury Automotive & Dealerships",
        search_queries=[
            '"luxury car" "dealership" "contact"',
            '"exotic cars" "inventory"',
            '"dealer" "luxury" "visit us"',
        ],
        scope_keywords=[
            "dealership", "luxury cars", "exotic cars", "auto",
            "motors", "vehicles", "maserati", "porsche", "range rover",
        ],
        exclusion_keywords=["used car auction", "rental cars"],
    ),
    "hospitality": Niche(
        id="hospitality",
        label="Luxury Hospitality & Hotels",
        search_queries=[
            '"boutique hotel" "contact"',
            '"luxury resort" "reservations"',
            '"five star" "hotel" "contact us"',
            '"fine dining" "restaurant" "book a table"',
        ],
        scope_keywords=[
            "hotel", "resort", "hospitality", "boutique hotel",
            "luxury stays", "restaurant group", "fine dining",
        ],
        exclusion_keywords=["hostel", "bed and breakfast"],
    ),
}


def get_niche(niche_id: str) -> Niche | None:
    return NICHES.get(niche_id)


def all_niche_ids() -> list[str]:
    return list(NICHES.keys())


def load_niches(ids: list[str] | None = None) -> list[Niche]:
    """Return a validated list of niches to scrape."""
    if not ids:
        return list(NICHES.values())
    result = []
    for nid in ids:
        niche = get_niche(nid)
        if niche:
            result.append(niche)
    return result