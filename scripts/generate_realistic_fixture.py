import os
import sys
import uuid
import json
from datetime import datetime, timedelta

BASE_DT = datetime(2025, 1, 15, 10, 0, 0)

COUNTRY_CODES = ["+34", "+32", "+41", "+352", "+39"]


def cycle_country_code(idx: int) -> str:
    return COUNTRY_CODES[idx % len(COUNTRY_CODES)]


def ten_digit_number(base: int, offset: int) -> str:
    return f"{base + offset:010d}"


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def add(objects: list, model: str, fields: dict, pk: str | None = None) -> str:
    if pk is None:
        pk = str(uuid.uuid4())
    obj = {"model": model, "pk": pk, "fields": fields}
    objects.append(obj)
    return pk


def build_fixture() -> list[dict]:
    objects: list[dict] = []
    password_hash = "pbkdf2_sha256$600000$Nf1JSucDbGkFARSXcttRQD$N/J0GcH+3KSNcfsYbFAPOYHiphFBCpzC0eBVRYmllCA="

    # Subscription plans
    plans = [
        {
            "code": "agent-free",
            "name": "Agent Free",
            "price": "0.00",
            "currency": "EUR",
            "max_athletes": 1,
            "max_collaborators": 0,
            "features": {
                "tier": "agent",
                "messaging_tier": "none",
                "max_messages_per_month": 0,
                "search_visibility_pct": 50,
                "stats_tier": "basic",
                "comparative_stats": False,
                "agent_subscription_management": True,
                "contract_tools": "disabled",
                "notification_center": False,
            },
        },
        {
            "code": "agent-pro",
            "name": "Agent Pro",
            "price": "50.00",
            "currency": "EUR",
            "max_athletes": 5,
            "max_collaborators": 0,
            "features": {
                "tier": "agent",
                "messaging_tier": "limited",
                "max_messages_per_month": 200,
                "search_visibility_pct": 100,
                "stats_tier": "advanced",
                "comparative_stats": False,
                "agent_subscription_management": True,
                "contract_tools": "enabled",
                "notification_center": True,
            },
        },
        {
            "code": "agent-agency",
            "name": "Agent Agency",
            "price": "149.99",
            "currency": "EUR",
            "max_athletes": 20,
            "max_collaborators": 0,
            "features": {
                "tier": "agent",
                "messaging_tier": "pro_plus",
                "max_messages_per_month": None,
                "search_visibility_pct": 130,
                "stats_tier": "premium",
                "comparative_stats": True,
                "agent_subscription_management": True,
                "contract_tools": "enabled",
                "notification_center": True,
            },
        },
        {
            "code": "org-starter",
            "name": "Organisation Starter",
            "price": "149.00",
            "currency": "EUR",
            "max_athletes": 0,
            "max_collaborators": 3,
            "features": {
                "tier": "organisation",
                "max_follows": 10,
                "collaborator_invites": True,
                "organisation_subscription_management": True,
                "athlete_stats_scope": "engagement",
                "data_access": ["follows", "engagement"],
                "contract_tools": "disabled",
                "notification_center": True,
            },
        },
        {
            "code": "org-pro",
            "name": "Organisation Pro",
            "price": "399.00",
            "currency": "EUR",
            "max_athletes": 0,
            "max_collaborators": 10,
            "features": {
                "tier": "organisation",
                "max_follows": 10,
                "collaborator_invites": True,
                "organisation_subscription_management": True,
                "athlete_stats_scope": "all",
                "data_access": ["follows", "engagement", "demographic"],
                "contract_tools": "enabled",
                "notification_center": True,
            },
        },
        {
            "code": "org-enterprise",
            "name": "Organisation Enterprise",
            "price": "999.00",
            "currency": "EUR",
            "max_athletes": 0,
            "max_collaborators": 0,
            "features": {
                "tier": "organisation",
                "max_follows": 10,
                "collaborator_invites": True,
                "organisation_subscription_management": True,
                "athlete_stats_scope": "all",
                "data_access": ["follows", "engagement", "demographic", "api"],
                "contract_tools": "enabled",
                "notification_center": True,
            },
        },
    ]

    # Plans are seeded via migrations; capture their natural keys for FK references.
    plan_ids: dict[str, list[str]] = {}
    for plan in plans:
        plan_ids[plan["code"]] = [plan["code"]]

    # Sports and disciplines
    sports_data = [
        {
            "name": "Athletics",
            "slug": "athletics",
            "emoji": "\U0001F3C3",
            "category": "INDIVIDUAL",
            "disciplines": [
                ("100m Sprint", "100m-sprint", "High intensity sprint over 100 meters.", True),
                ("Marathon", "marathon", "Long distance road running event.", True),
                ("Long Jump", "long-jump", "Field event measuring horizontal distance.", True),
            ],
        },
        {
            "name": "Football",
            "slug": "football",
            "emoji": "\u26BD",
            "category": "TEAM",
            "disciplines": [
                ("Ligue 1", "ligue-1", "Top French professional league.", False),
                ("UEFA Champions League", "uefa-champions-league", "Elite European club competition.", False),
                ("FIFA World Cup", "fifa-world-cup", "Global national team tournament.", True),
            ],
        },
        {
            "name": "Basketball",
            "slug": "basketball",
            "emoji": "\U0001F3C0",
            "category": "TEAM",
            "disciplines": [
                ("EuroLeague", "euroleague", "Premier European club competition.", False),
                ("NBA", "nba", "North American professional league.", False),
                ("FIBA World Cup", "fiba-world-cup", "International national team competition.", True),
            ],
        },
        {
            "name": "Swimming",
            "slug": "swimming",
            "emoji": "\U0001F3CA",
            "category": "INDIVIDUAL",
            "disciplines": [
                ("100m Freestyle", "100m-freestyle", "Sprint freestyle event.", True),
                ("200m Butterfly", "200m-butterfly", "Challenging butterfly distance.", True),
                ("Open Water 10km", "open-water-10km", "Endurance race in open water.", True),
            ],
        },
        {
            "name": "Cycling",
            "slug": "cycling",
            "emoji": "\U0001F6B4",
            "category": "MIXED",
            "disciplines": [
                ("Tour de France", "tour-de-france", "Grand Tour stage race.", True),
                ("Track Sprint", "track-sprint", "Velodrome sprint event.", True),
                ("Mountain Biking XCO", "mountain-biking-xco", "Cross-country Olympic format.", True),
            ],
        },
        {
            "name": "Tennis",
            "slug": "tennis",
            "emoji": "\U0001F3BE",
            "category": "INDIVIDUAL",
            "disciplines": [
                ("Roland-Garros", "roland-garros", "Clay Grand Slam tournament.", False),
                ("Wimbledon", "wimbledon", "Grass Grand Slam tournament.", False),
                ("ATP Finals", "atp-finals", "Season-ending championship.", False),
            ],
        },
        {
            "name": "Gymnastics",
            "slug": "gymnastics",
            "emoji": "\U0001F938",
            "category": "INDIVIDUAL",
            "disciplines": [
                ("Artistic All-Around", "artistic-all-around", "Combined apparatus competition.", True),
                ("Rhythmic Ribbon", "rhythmic-ribbon", "Graceful ribbon routine.", True),
                ("Trampoline", "trampoline", "Acrobatic trampoline event.", True),
            ],
        },
        {
            "name": "Rugby",
            "slug": "rugby",
            "emoji": "\U0001F3C9",
            "category": "TEAM",
            "disciplines": [
                ("Top 14", "top-14", "French professional rugby league.", False),
                ("Six Nations", "six-nations", "Annual European championship.", False),
                ("Rugby World Cup", "rugby-world-cup", "Global rugby union tournament.", True),
            ],
        },
        {
            "name": "Esports",
            "slug": "esports",
            "emoji": "\U0001F3AE",
            "category": "MIXED",
            "disciplines": [
                ("League of Legends", "league-of-legends", "International MOBA circuit.", False),
                ("Valorant Champions", "valorant-champions", "Global FPS circuit.", False),
                ("Rocket League Major", "rocket-league-major", "Hybrid motorsports esports event.", False),
            ],
        },
        {
            "name": "Surfing",
            "slug": "surfing",
            "emoji": "\U0001F3C4",
            "category": "INDIVIDUAL",
            "disciplines": [
                ("WSL Championship Tour", "wsl-championship-tour", "Elite professional tour.", False),
                ("Big Wave Invitational", "big-wave-invitational", "Invite-only big wave event.", False),
                ("Olympic Shortboard", "olympic-shortboard", "Olympic surfing competition.", True),
            ],
        },
    ]

    sport_ids: dict[str, str] = {}
    discipline_ids: dict[tuple[str, str], str] = {}

    for idx, sport in enumerate(sports_data):
        sport_id = add(
            objects,
            "athletes.sport",
            {
                "name": sport["name"],
                "slug": sport["slug"],
                "emoji": sport["emoji"],
                "category": sport["category"],
                "created_at": iso(BASE_DT + timedelta(minutes=10 + idx)),
                "updated_at": iso(BASE_DT + timedelta(minutes=10 + idx)),
            },
        )
        sport_ids[sport["name"]] = sport_id
        for d_idx, (name, slug, description, is_olympic) in enumerate(sport["disciplines"]):
            disc_id = add(
                objects,
                "athletes.sportdiscipline",
                {
                    "sport": sport_id,
                    "name": name,
                    "slug": slug,
                    "description": description,
                    "is_olympic": is_olympic,
                    "created_at": iso(BASE_DT + timedelta(minutes=10 + idx, seconds=30 * d_idx)),
                    "updated_at": iso(BASE_DT + timedelta(minutes=10 + idx, seconds=30 * d_idx)),
                },
            )
            discipline_ids[(sport["name"], name)] = disc_id

    # Users - Agents
    agent_infos = [
        ("Alice", "Dupont", "alice.dupont"),
        ("Bruno", "Martin", "bruno.martin"),
        ("Chloé", "Laurent", "chloe.laurent"),
        ("David", "Bernard", "david.bernard"),
        ("Emma", "Girard", "emma.girard"),
        ("Fabien", "Moreau", "fabien.moreau"),
        ("Gaëlle", "Robert", "gaelle.robert"),
        ("Hugo", "Petit", "hugo.petit"),
        ("Isabelle", "Lefevre", "isabelle.lefevre"),
        ("Julien", "Caron", "julien.caron"),
        ("Karim", "Leroy", "karim.leroy"),
        ("Laura", "Fontaine", "laura.fontaine"),
        ("Mathieu", "Perrin", "mathieu.perrin"),
        ("Nadia", "Roche", "nadia.roche"),
        ("Olivier", "Lemaitre", "olivier.lemaitre"),
        ("Pauline", "Marchand", "pauline.marchand"),
        ("Quentin", "Blanchard", "quentin.blanchard"),
        ("Romain", "Allard", "romain.allard"),
        ("Sophie", "Garnier", "sophie.garnier"),
        ("Thomas", "Barbier", "thomas.barbier"),
    ]

    agent_plan_map = [
        "agent-free", "agent-free", "agent-free", "agent-free", "agent-free", "agent-free", "agent-free",
        "agent-free", "agent-free", "agent-free", "agent-free", "agent-free",
        "agent-pro", "agent-pro", "agent-pro",
        "agent-agency",
        "agent-pro", "agent-pro",
        "agent-free", "agent-free",
    ]

    self_represented = {i for i in range(7)}

    agent_ids: list[str] = []
    agent_profile_ids: list[str] = []

    for idx, (first, last, username) in enumerate(agent_infos):
        email = f"{username}@example.com"
        user_id = add(
            objects,
            "users.user",
            {
                "email": email,
                "first_name": first,
                "last_name": last,
                "phone_country_code": cycle_country_code(idx),
                "phone_number": ten_digit_number(6000000000, idx),
                "date_of_birth": "1985-05-15",
                "email_verified": True,
                "password": password_hash,
                "password_hash": password_hash,
                "is_active": True,
                "is_staff": False,
                "account_type": "AGENT",
                "last_login": None,
                "created_at": iso(BASE_DT + timedelta(hours=idx)),
                "updated_at": iso(BASE_DT + timedelta(hours=idx)),
            },
        )
        agent_ids.append(user_id)
        profile_id = add(
            objects,
            "users.agentprofile",
            {
                "user": user_id,
                "display_name": f"{first} {last}",
                "bio": "Agent sportif expérimenté accompagnant des talents européens.",
                "is_self_represented": idx in self_represented,
                "created_at": iso(BASE_DT + timedelta(hours=idx, minutes=15)),
                "updated_at": iso(BASE_DT + timedelta(hours=idx, minutes=15)),
            },
        )
        agent_profile_ids.append(profile_id)

    # Users - Collaborators
    collaborator_infos = [
        ("Amélie", "Boucher", "amelie.boucher"),
        ("Bastien", "Renard", "bastien.renard"),
        ("Camille", "Lopez", "camille.lopez"),
        ("Damien", "Giraud", "damien.giraud"),
        ("Elise", "Morel", "elise.morel"),
        ("Florian", "Rousseau", "florian.rousseau"),
        ("Géraldine", "Fabre", "geraldine.fabre"),
        ("Hélène", "Marchal", "helene.marchal"),
        ("Inès", "Baron", "ines.baron"),
        ("Jules", "Dupuis", "jules.dupuis"),
        ("Katia", "Jourdan", "katia.jourdan"),
        ("Louis", "Marin", "louis.marin"),
        ("Mélanie", "Charbonnier", "melanie.charbonnier"),
        ("Noé", "Poulain", "noe.poulain"),
        ("Ophélie", "Descamps", "ophelie.descamps"),
        ("Pierre", "Delorme", "pierre.delorme"),
        ("Quitterie", "Renaud", "quitterie.renaud"),
        ("Raphaël", "Leclerc", "raphael.leclerc"),
        ("Salomé", "Bertin", "salome.bertin"),
        ("Tristan", "Hubert", "tristan.hubert"),
        ("Ulysse", "Gosselin", "ulysse.gosselin"),
        ("Valérie", "Chartier", "valerie.chartier"),
        ("William", "Vaillant", "william.vaillant"),
        ("Xavier", "Garnier", "xavier.garnier"),
        ("Yasmine", "Fernand", "yasmine.fernand"),
        ("Zoé", "Lambert", "zoe.lambert"),
        ("Adrien", "Payet", "adrien.payet"),
        ("Bérénice", "Verdier", "berenice.verdier"),
        ("Cyril", "Gallet", "cyril.gallet"),
        ("Daphné", "Picard", "daphne.picard"),
    ]

    collaborator_user_ids: list[str] = []
    collaborator_user_lookup: dict[str, str] = {}
    for idx, (first, last, username) in enumerate(collaborator_infos):
        user_id = add(
            objects,
            "users.user",
            {
                "email": f"{username}@brands.example.com",
                "first_name": first,
                "last_name": last,
                "phone_country_code": cycle_country_code(idx + len(agent_infos)),
                "phone_number": ten_digit_number(7000000000, idx),
                "date_of_birth": "1990-04-20",
                "email_verified": True,
                "password": password_hash,
                "password_hash": password_hash,
                "is_active": True,
                "is_staff": False,
                "account_type": "COLLABORATOR",
                "last_login": None,
                "created_at": iso(BASE_DT + timedelta(hours=idx + 30)),
                "updated_at": iso(BASE_DT + timedelta(hours=idx + 30)),
            },
        )
        collaborator_user_ids.append(user_id)

    # Organisations and collaborators distribution
    organisation_ids: list[str] = []

    enterprise_org = {
        "name": "Global Sports Partners",
        "slug": "global-sports-partners",
        "type": "AGENCY",
        "industry": "Marketing sportif",
        "description": "Agence internationale spécialisée dans les activations multicanales.",
        "address_city": "Paris",
        "address_country": "France",
        "address_postal_code": "75008",
        "website_url": "https://global-sports.example.com",
    }

    collaborator_idx = 0
    enterprise_owner_user = collaborator_user_ids[collaborator_idx]
    collaborator_idx += 1
    enterprise_org_id = add(
        objects,
        "organisations.organisation",
        {
            "name": enterprise_org["name"],
            "slug": enterprise_org["slug"],
            "owner": enterprise_owner_user,
            "type": enterprise_org["type"],
            "industry": enterprise_org["industry"],
            "logo": "",
            "banner_image": "",
            "description": enterprise_org["description"],
            "website_url": enterprise_org["website_url"],
            "email_contact": "contact@global-sports.example.com",
            "phone_contact": f"{cycle_country_code(0)}{ten_digit_number(8100000000, 0)}",
            "address_city": enterprise_org["address_city"],
            "address_country": enterprise_org["address_country"],
            "address_postal_code": enterprise_org["address_postal_code"],
            "social_links": {"linkedin": "https://www.linkedin.com/company/global-sports"},
            "founded_year": 2010,
            "employees_count": 120,
            "budget_range": "500k-1M€",
            "sponsoring_focus": ["Activation digitale", "Hospitalités premium"],
            "created_at": iso(BASE_DT + timedelta(days=1)),
            "updated_at": iso(BASE_DT + timedelta(days=1)),
        },
    )
    organisation_ids.append(enterprise_org_id)

    enterprise_collaborator_ids: list[str] = []
    owner_collab_id = add(
        objects,
        "organisations.collaborator",
        {
            "user": enterprise_owner_user,
            "organisation": enterprise_org_id,
            "role": "OWNER",
            "job_title": "Directrice des partenariats",
            "created_at": iso(BASE_DT + timedelta(days=1, minutes=5)),
            "updated_at": iso(BASE_DT + timedelta(days=1, minutes=5)),
        },
    )
    enterprise_collaborator_ids.append(owner_collab_id)
    collaborator_user_lookup[owner_collab_id] = enterprise_owner_user

    job_titles = [
        "Responsable activation",
        "Chef de projet sponsoring",
        "Analyste data sports",
        "Chargée des relations publiques",
        "Coordinateur événementiel",
        "Juriste contrats",
        "Manager CRM",
        "Designer créatif",
        "Spécialiste réseaux sociaux",
    ]

    for extra in range(9):
        user = collaborator_user_ids[collaborator_idx]
        collaborator_idx += 1
        collab_id = add(
            objects,
            "organisations.collaborator",
            {
                "user": user,
                "organisation": enterprise_org_id,
                "role": "MEMBER",
                "job_title": job_titles[extra],
                "created_at": iso(BASE_DT + timedelta(days=1, minutes=10 + extra)),
                "updated_at": iso(BASE_DT + timedelta(days=1, minutes=10 + extra)),
            },
        )
        enterprise_collaborator_ids.append(collab_id)
        collaborator_user_lookup[collab_id] = user

    organisation_subscriptions: list[tuple[str, list[str]]] = [
        (enterprise_org_id, plan_ids["org-enterprise"])
    ]

    pro_orgs = [
        ("HexaTech", "hexatech", "STARTUP"),
        ("LuxeMode", "luxemode", "BRAND"),
        ("GreenEnergy", "greenenergy", "SME"),
        ("Alpes Aventures", "alpes-aventures", "ASSOCIATION"),
        ("Digital Fans", "digital-fans", "STARTUP"),
    ]

    pro_org_collaborators: list[list[str]] = []
    for idx, (name, slug, org_type) in enumerate(pro_orgs):
        owner_user = collaborator_user_ids[collaborator_idx]
        collaborator_idx += 1
        org_id = add(
            objects,
            "organisations.organisation",
            {
                "name": name,
                "slug": slug,
                "owner": owner_user,
                "type": org_type,
                "industry": "Communication",
                "logo": "",
                "banner_image": "",
                "description": f"{name} recherche des opportunités de sponsoring ciblées.",
                "website_url": f"https://{slug}.example.com",
                "email_contact": f"hello@{slug}.example.com",
                "phone_contact": f"{cycle_country_code(idx + 1)}{ten_digit_number(8200000000, idx)}",
                "address_city": "Lyon",
                "address_country": "France",
                "address_postal_code": "69002",
                "social_links": {"linkedin": f"https://www.linkedin.com/company/{slug}"},
                "founded_year": 2018,
                "employees_count": 25,
                "budget_range": "150k-300k€",
                "sponsoring_focus": ["Brand awareness", "Lancement produit"],
                "created_at": iso(BASE_DT + timedelta(days=2, minutes=len(organisation_ids) * 3)),
                "updated_at": iso(BASE_DT + timedelta(days=2, minutes=len(organisation_ids) * 3)),
            },
        )
        organisation_ids.append(org_id)
        owner_collab_id = add(
            objects,
            "organisations.collaborator",
            {
                "user": owner_user,
                "organisation": org_id,
                "role": "OWNER",
                "job_title": "Responsable sponsoring",
                "created_at": iso(BASE_DT + timedelta(days=2, minutes=len(pro_org_collaborators) * 5)),
                "updated_at": iso(BASE_DT + timedelta(days=2, minutes=len(pro_org_collaborators) * 5)),
            },
        )
        member_ids = [owner_collab_id]
        collaborator_user_lookup[owner_collab_id] = owner_user
        for m in range(2):
            user = collaborator_user_ids[collaborator_idx]
            collaborator_idx += 1
            collab_id = add(
                objects,
                "organisations.collaborator",
                {
                    "user": user,
                    "organisation": org_id,
                    "role": "MEMBER",
                    "job_title": ["Chef de projet", "Analyste insights"][m],
                    "created_at": iso(BASE_DT + timedelta(days=2, minutes=len(pro_org_collaborators) * 5 + m + 1)),
                    "updated_at": iso(BASE_DT + timedelta(days=2, minutes=len(pro_org_collaborators) * 5 + m + 1)),
                },
            )
            member_ids.append(collab_id)
            collaborator_user_lookup[collab_id] = user
        pro_org_collaborators.append(member_ids)
        organisation_subscriptions.append((org_id, plan_ids["org-pro"]))

    free_orgs = [
        ("Atelier Gourmand", "atelier-gourmand", "SME"),
        ("Studio Nova", "studio-nova", "STARTUP"),
        ("Club Urbain", "club-urbain", "ASSOCIATION"),
        ("Maison Riviera", "maison-riviera", "BRAND"),
        ("MediaPulse", "mediapulse", "OTHER"),
    ]

    free_org_collaborators: list[list[str]] = []
    for idx, (name, slug, org_type) in enumerate(free_orgs):
        owner_user = collaborator_user_ids[collaborator_idx]
        collaborator_idx += 1
        org_id = add(
            objects,
            "organisations.organisation",
            {
                "name": name,
                "slug": slug,
                "owner": owner_user,
                "type": org_type,
                "industry": "Artisanat",
                "logo": "",
                "banner_image": "",
                "description": f"{name} explore les partenariats locaux.",
                "website_url": f"https://{slug}.example.com",
                "email_contact": f"contact@{slug}.example.com",
                "phone_contact": f"{cycle_country_code(idx + 1 + len(pro_orgs))}{ten_digit_number(8300000000, idx)}",
                "address_city": "Bordeaux",
                "address_country": "France",
                "address_postal_code": "33000",
                "social_links": {},
                "founded_year": 2020,
                "employees_count": 6,
                "budget_range": "20k-50k€",
                "sponsoring_focus": ["Visibilité locale"],
                "created_at": iso(BASE_DT + timedelta(days=3, minutes=len(organisation_ids) * 4)),
                "updated_at": iso(BASE_DT + timedelta(days=3, minutes=len(organisation_ids) * 4)),
            },
        )
        organisation_ids.append(org_id)
        owner_collab_id = add(
            objects,
            "organisations.collaborator",
            {
                "user": owner_user,
                "organisation": org_id,
                "role": "OWNER",
                "job_title": "Gérant",
                "created_at": iso(BASE_DT + timedelta(days=3, minutes=len(free_org_collaborators) * 6)),
                "updated_at": iso(BASE_DT + timedelta(days=3, minutes=len(free_org_collaborators) * 6)),
            },
        )
        free_org_collaborators.append([owner_collab_id])
        collaborator_user_lookup[owner_collab_id] = owner_user

    assert collaborator_idx == len(collaborator_user_ids), (
        collaborator_idx,
        len(collaborator_user_ids),
    )

    # Organisation subscriptions entries
    for org_id, plan_id in organisation_subscriptions:
        add(
            objects,
            "payments.subscription",
            {
                "organisation": org_id,
                "agent": None,
                "plan": plan_id,
                "status": "active",
                "start_at": iso(BASE_DT - timedelta(days=15)),
                "current_period_end": iso(BASE_DT + timedelta(days=15)),
                "stripe_customer_id": f"cus_{org_id[:8]}",
                "stripe_subscription_id": f"sub_{org_id[:8]}",
                "created_at": iso(BASE_DT - timedelta(days=15, minutes=5)),
                "updated_at": iso(BASE_DT + timedelta(days=1)),
            },
        )

    # Agent subscriptions
    for idx, profile_id in enumerate(agent_profile_ids):
        plan_code = agent_plan_map[idx]
        add(
            objects,
            "payments.subscription",
            {
                "organisation": None,
                "agent": profile_id,
                "plan": plan_ids[plan_code],
                "status": "active",
                "start_at": iso(BASE_DT - timedelta(days=10 + idx)),
                "current_period_end": iso(BASE_DT + timedelta(days=20 - idx)),
                "stripe_customer_id": f"cus_agent_{idx:02d}",
                "stripe_subscription_id": f"sub_agent_{idx:02d}",
                "created_at": iso(BASE_DT - timedelta(days=10 + idx, minutes=30)),
                "updated_at": iso(BASE_DT + timedelta(days=5, minutes=idx)),
            },
        )

    # Athletes assignments
    athlete_names = [
        "Alice Dupont", "Bruno Martin", "Chloé Laurent", "David Bernard", "Emma Girard", "Fabien Moreau", "Gaëlle Robert",
        "Milan Ortega", "Yara Benali", "Theo Ricard", "Selena Kone", "Jonas Kramer",
        "Ingrid Meyer", "Lucas Vidal", "Maya Sato", "Noah Fischer", "Clara Jensen",
        "Rafael Costa", "Lucie Moretti", "Amira Idrissi", "Victor Da Silva", "Elena Popov", "Jules Lambert", "Sofia Romano",
        "Tobias Keller", "Hanna Schultz", "Ivy McKenna", "Leo Andersson", "Aisha Diallo", "Jonah Clarke", "Mira Novak",
        "Pavel Horvat", "Sara Nordin", "Elodie Marchal", "Kenji Watanabe", "Camila Torres", "Nikolai Petrov",
    ]

    athlete_assignments: list[tuple[str, str]] = []
    for i in range(7):
        athlete_assignments.append((athlete_names[i], agent_profile_ids[i]))
    for i in range(5):
        athlete_assignments.append((athlete_names[7 + i], agent_profile_ids[7 + i]))

    pro_agent_indices = [12, 13, 14]
    athlete_idx = 12
    for agent_idx in pro_agent_indices:
        for _ in range(5):
            athlete_assignments.append((athlete_names[athlete_idx], agent_profile_ids[agent_idx]))
            athlete_idx += 1

    for _ in range(10):
        athlete_assignments.append((athlete_names[athlete_idx], agent_profile_ids[15]))
        athlete_idx += 1

    remaining = athlete_names[athlete_idx:]
    agent_cycle = agent_profile_ids[16:]
    for idx, name in enumerate(remaining):
        athlete_assignments.append((name, agent_cycle[idx % len(agent_cycle)]))

    assert len(athlete_assignments) == 37

    athlete_ids: list[str] = []
    athlete_discipline_entries: list[tuple[str, str]] = []
    sport_cycle = list(sport_ids.values())
    discipline_list = list(discipline_ids.values())

    for idx, (full_name, agent_profile_id) in enumerate(athlete_assignments):
        sport_id = sport_cycle[idx % len(sport_cycle)]
        birth_year = 1990 + (idx % 10)
        fields = {
            "sport": sport_id,
            "agent": agent_profile_id,
            "full_name": full_name,
            "slug": full_name.lower().replace(" ", "-") + f"-{idx}",
            "birth_date": f"{birth_year}-0{(idx % 9) + 1}-15",
            "nationality": ["France", "Belgique", "Suisse", "Espagne", "Italie", "Allemagne"][idx % 6],
            "country": ["France", "Belgique", "Suisse", "Espagne", "Italie", "Allemagne"][idx % 6],
            "city": ["Paris", "Lyon", "Nice", "Toulouse", "Bordeaux", "Marseille"][idx % 6],
            "bio": "Athlète professionnel(le) avec un palmarès reconnu sur la scène internationale.",
            "social_links": {
                "instagram": f"https://instagram.com/{full_name.lower().replace(' ', '')}",
                "twitter": f"https://twitter.com/{full_name.lower().split()[0]}",
            },
            "followers_count_cached": 15000 + idx * 1200,
            "engagement_rate_cached": f"3.{idx % 50:02d}",
            "avatar": "",
            "created_at": iso(BASE_DT + timedelta(days=5, minutes=idx)),
            "updated_at": iso(BASE_DT + timedelta(days=5, minutes=idx)),
        }
        athlete_id = add(objects, "athletes.athlete", fields)
        athlete_ids.append(athlete_id)
        primary_disc = discipline_list[idx % len(discipline_list)]
        secondary_disc = discipline_list[(idx * 3) % len(discipline_list)]
        athlete_discipline_entries.append((athlete_id, primary_disc))
        if secondary_disc != primary_disc:
            athlete_discipline_entries.append((athlete_id, secondary_disc))

    for idx, (athlete_id, discipline_id) in enumerate(athlete_discipline_entries):
        add(
            objects,
            "athletes.athletediscipline",
            {
                "athlete": athlete_id,
                "discipline": discipline_id,
                "created_at": iso(BASE_DT + timedelta(days=5, minutes=idx, seconds=10)),
                "updated_at": iso(BASE_DT + timedelta(days=5, minutes=idx, seconds=10)),
            },
        )

    for idx, athlete_id in enumerate(athlete_ids[:5]):
        add(
            objects,
            "athletes.athletephoto",
            {
                "athlete": athlete_id,
                "image": f"athlete_gallery/{athlete_id[:8]}_training.jpg",
                "caption": "Séance d'entraînement",
                "created_at": iso(BASE_DT + timedelta(days=6, minutes=idx)),
                "updated_at": iso(BASE_DT + timedelta(days=6, minutes=idx)),
            },
        )

    follow_pairs: list[tuple[str, str]] = []
    for collab_id in enterprise_collaborator_ids[:5]:
        for athlete_id in athlete_ids[:3]:
            follow_pairs.append((collab_id, athlete_id))
    for member_ids in pro_org_collaborators:
        for athlete_id in athlete_ids[5:10]:
            follow_pairs.append((member_ids[0], athlete_id))

    for idx, (collab_id, athlete_id) in enumerate(follow_pairs):
        add(
            objects,
            "follows.follow",
            {
                "collaborator": collab_id,
                "athlete": athlete_id,
                "notify_news": True,
                "notify_stats": idx % 2 == 0,
                "notify_contracts": True,
                "created_at": iso(BASE_DT + timedelta(days=7, minutes=idx)),
                "updated_at": iso(BASE_DT + timedelta(days=7, minutes=idx)),
            },
        )

    clause_templates = [
        (
            "financial-compensation",
            "Compensation financière",
            "financial",
            "L'organisation versera {{amount}} EUR à l'athlète en {{installments}} versements.",
            ["amount", "installments"],
            True,
        ),
        (
            "image-rights",
            "Droits à l'image",
            "intellectual_property",
            "L'athlète cède les droits d'utilisation de son image pour {{campaign_duration}}.",
            ["campaign_duration"],
            False,
        ),
        (
            "event-participation",
            "Participation événementielle",
            "logistics",
            "L'athlète participera à {{event_count}} événements promotionnels par an.",
            ["event_count"],
            True,
        ),
        (
            "performance-metrics",
            "Objectifs de performance",
            "performance",
            "L'athlète s'engage à maintenir un taux d'engagement moyen de {{engagement_target}}%.",
            ["engagement_target"],
            False,
        ),
    ]

    clause_template_ids: list[str] = []
    for idx, (_, title, category, content, placeholders, mandatory) in enumerate(clause_templates):
        template_id = add(
            objects,
            "contracts.clausetemplate",
            {
                "category": category,
                "title": title,
                "content": content,
                "placeholders": placeholders,
                "is_mandatory": mandatory,
                "version": 1,
                "created_at": iso(BASE_DT - timedelta(days=20, minutes=idx)),
                "updated_at": iso(BASE_DT - timedelta(days=20, minutes=idx)),
            },
        )
        clause_template_ids.append(template_id)

    contract_statuses = [
        ("draft", "Activation printemps 2025"),
        ("negotiation", "Tournée estivale Europe"),
        ("legal_review", "Campagne digitale Q3"),
        ("signing", "Programme fidélité premium"),
        ("active", "Série web immersive"),
    ]

    contract_orgs = [
        enterprise_org_id,
        organisation_ids[1],
        organisation_ids[2],
        organisation_ids[-1],
        organisation_ids[0],
    ]
    initiator_collaborators = [
        enterprise_collaborator_ids[0],
        pro_org_collaborators[0][0],
        pro_org_collaborators[1][0],
        free_org_collaborators[0][0],
        enterprise_collaborator_ids[1],
    ]
    initiator_users = [collaborator_user_lookup[collab_id] for collab_id in initiator_collaborators]
    contract_agents = [
        agent_profile_ids[12],
        agent_profile_ids[13],
        agent_profile_ids[15],
        agent_profile_ids[14],
        agent_profile_ids[7],
    ]

    contract_ids: list[str] = []
    contract_version_ids: list[str] = []
    contract_clause_ids: list[str] = []

    for idx, (status, title) in enumerate(contract_statuses):
        contract_id = add(
            objects,
            "contracts.contract",
            {
                "organisation": contract_orgs[idx],
                "agent": contract_agents[idx],
                "initiated_by": initiator_collaborators[idx],
                "status": status,
                "title": title,
                "effective_date": "2025-03-01" if status in {"signing", "active"} else None,
                "expiration_date": "2026-02-28" if status in {"signing", "active"} else None,
                "owner_agreed_at": iso(BASE_DT + timedelta(days=idx)) if status in {"legal_review", "signing", "active"} else None,
                "agent_agreed_at": iso(BASE_DT + timedelta(days=idx, hours=2)) if status in {"signing", "active"} else None,
                "current_version_number": 1,
                "created_at": iso(BASE_DT + timedelta(days=idx * 2)),
                "updated_at": iso(BASE_DT + timedelta(days=idx * 2, hours=1)),
            },
        )
        contract_ids.append(contract_id)
        version_id = add(
            objects,
            "contracts.contractversion",
            {
                "contract": contract_id,
                "number": 1,
                "created_by": initiator_users[idx],
                "source_revision": None,
                "notes": "Version initiale générée automatiquement.",
                "created_at": iso(BASE_DT + timedelta(days=idx * 2, minutes=30)),
                "updated_at": iso(BASE_DT + timedelta(days=idx * 2, minutes=30)),
            },
        )
        contract_version_ids.append(version_id)
        for tpl_idx, template_id in enumerate(clause_template_ids[:3]):
            clause_id = add(
                objects,
                "contracts.contractclause",
                {
                    "contract": contract_id,
                    "template": template_id,
                    "title": clause_templates[tpl_idx][1],
                    "content": clause_templates[tpl_idx][3].replace("{{", "").replace("}}", ""),
                    "is_mandatory": clause_templates[tpl_idx][5],
                    "is_modified": tpl_idx == 2,
                    "created_at": iso(BASE_DT + timedelta(days=idx * 2, minutes=45 + tpl_idx)),
                    "updated_at": iso(BASE_DT + timedelta(days=idx * 2, minutes=45 + tpl_idx)),
                },
            )
            contract_clause_ids.append(clause_id)
        if status in {"negotiation", "legal_review"}:
            add(
                objects,
                "contracts.contractrevision",
                {
                    "contract": contract_id,
                    "proposed_by": agent_ids[agent_profile_ids.index(contract_agents[idx])],
                    "comment": "Proposition d'ajuster le périmètre des contenus.",
                    "accepted": None,
                    "created_at": iso(BASE_DT + timedelta(days=idx * 2, hours=3)),
                    "updated_at": iso(BASE_DT + timedelta(days=idx * 2, hours=3)),
                },
            )

    for idx, version_id in enumerate(contract_version_ids):
        add(
            objects,
            "contracts.contractcomment",
            {
                "contract": contract_ids[idx],
                "version": version_id,
                "clause": contract_clause_ids[idx * 3],
                "author": initiator_users[idx],
                "body": "Annotation interne pour préciser les conditions.",
                "created_at": iso(BASE_DT + timedelta(days=idx * 2, hours=4)),
                "updated_at": iso(BASE_DT + timedelta(days=idx * 2, hours=4)),
            },
        )

    return objects


def main() -> None:
    fixture = build_fixture()
    output_path = os.path.join("fixtures", "realistic_environment.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(fixture, fp, ensure_ascii=False, indent=2)
    print(f"Wrote {len(fixture)} records to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
