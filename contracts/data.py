"""Static datasets used by the contracts application."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5


def _generate_uuid(slug: str) -> UUID:
    """Return a stable UUID for the given slug value."""

    return uuid5(NAMESPACE_URL, f"sponsorsclub:contracts:{slug}")


CLAUSE_TEMPLATE_FIXTURES = [
    {
        "slug": "clause-identification",
        "category": "administratives",
        "title": "Identification des parties",
        "content": (
            "Le présent contrat est conclu entre {{organisation_name}}, dont le siège est situé à {{organisation_address}}, "
            "représentée par {{organisation_representative}}, ci-après dénommée 'le Sponsor', et {{athlete_name}}, né(e) le "
            "{{athlete_birthdate}}, domicilié(e) à {{athlete_address}}, ci-après dénommé(e) 'l'Athlète'."
        ),
        "placeholders": [
            "organisation_name",
            "organisation_address",
            "organisation_representative",
            "athlete_name",
            "athlete_birthdate",
            "athlete_address",
        ],
        "is_mandatory": True,
    },
    {
        "slug": "clause-objet",
        "category": "administratives",
        "title": "Objet du contrat",
        "content": (
            "Le présent contrat a pour objet de définir les conditions dans lesquelles l'Athlète {{athlete_name}} s'engage à "
            "promouvoir la marque {{organisation_name}} dans le cadre de ses activités sportives, médiatiques et promotionnelles."
        ),
        "placeholders": ["athlete_name", "organisation_name"],
        "is_mandatory": True,
    },
    {
        "slug": "clause-duree",
        "category": "administratives",
        "title": "Durée",
        "content": (
            "Le présent contrat prend effet à compter du {{start_date}} et expirera le {{end_date}}, sauf renouvellement "
            "expressément convenu par les parties ou résiliation anticipée conformément aux dispositions prévues."
        ),
        "placeholders": ["start_date", "end_date"],
        "is_mandatory": True,
    },
    {
        "slug": "clause-athlete-events",
        "category": "obligations",
        "title": "Présence aux événements",
        "content": (
            "L’athlète {{athlete_name}} s’engage à participer personnellement aux événements organisés par {{organisation_name}}, "
            "dans la limite de {{number_of_events}} événements maximum par période contractuelle. Ces événements peuvent inclure, "
            "à titre d’exemple et sans limitation : conférences de presse, séances de dédicaces, présentations de produits, actions "
            "caritatives, salons ou compétitions. L’organisation devra notifier l’athlète au minimum {{notice_period_days}} jours avant "
            "la date prévue. Les frais de déplacement, d’hébergement et de restauration liés à ces participations seront "
            "intégralement pris en charge par {{organisation_name}}. En cas d’indisponibilité justifiée (blessure, force majeure), "
            "l’athlète devra en informer immédiatement l’organisation, qui pourra convenir d’un report ou d’une prestation "
            "équivalente (ex: intervention vidéo)."
        ),
        "placeholders": [
            "athlete_name",
            "organisation_name",
            "number_of_events",
            "notice_period_days",
        ],
        "is_mandatory": False,
    },
    {
        "slug": "clause-athlete-social",
        "category": "obligations",
        "title": "Publications sur réseaux sociaux",
        "content": (
            "L’athlète {{athlete_name}} s’engage à publier au minimum {{posts_per_month}} publications et {{stories_per_month}} stories "
            "par mois sur ses réseaux sociaux (Instagram, TikTok, Facebook, YouTube) en mentionnant et en mettant en valeur "
            "{{organisation_name}} selon les directives fournies."
        ),
        "placeholders": [
            "athlete_name",
            "organisation_name",
            "posts_per_month",
            "stories_per_month",
        ],
        "is_mandatory": False,
    },
    {
        "slug": "clause-athlete-exclusivity",
        "category": "obligations",
        "title": "Exclusivité sectorielle",
        "content": (
            "Pendant la durée du présent contrat, l’athlète {{athlete_name}} s’interdit de signer tout autre contrat de sponsoring ou "
            "de représentation avec une marque concurrente de {{organisation_name}} dans le secteur {{sector}}."
        ),
        "placeholders": ["athlete_name", "organisation_name", "sector"],
        "is_mandatory": False,
    },
    {
        "slug": "clause-orga-payment",
        "category": "finance",
        "title": "Paiement de la rémunération",
        "content": (
            "Le Sponsor {{organisation_name}} s’engage à verser à l’Athlète {{athlete_name}} une rémunération totale de {{amount}} {{currency}}, "
            "selon l’échéancier suivant : {{payment_schedule}}."
        ),
        "placeholders": [
            "organisation_name",
            "athlete_name",
            "amount",
            "currency",
            "payment_schedule",
        ],
        "is_mandatory": True,
    },
    {
        "slug": "clause-orga-logistics",
        "category": "obligations",
        "title": "Prise en charge logistique",
        "content": (
            "Le Sponsor {{organisation_name}} prendra à sa charge l’ensemble des frais liés aux déplacements, hébergements et repas de "
            "l’Athlète {{athlete_name}} lors des événements prévus dans le cadre du présent contrat."
        ),
        "placeholders": ["organisation_name", "athlete_name"],
        "is_mandatory": False,
    },
    {
        "slug": "clause-finance-bonus",
        "category": "finance",
        "title": "Bonus de performance",
        "content": (
            "L’Athlète {{athlete_name}} percevra un bonus de {{bonus_amount}} {{currency}} en cas d’atteinte des objectifs suivants : {{performance_goals}}."
        ),
        "placeholders": [
            "athlete_name",
            "bonus_amount",
            "currency",
            "performance_goals",
        ],
        "is_mandatory": False,
    },
    {
        "slug": "clause-ip-image",
        "category": "ip",
        "title": "Droit à l’image",
        "content": (
            "L’Athlète {{athlete_name}} autorise le Sponsor {{organisation_name}} à utiliser son nom, son image, sa voix et ses performances sportives "
            "dans le cadre de campagnes publicitaires, promotions et communications internes ou externes, sur tout support (print, digital, audiovisuel), "
            "et pour une durée limitée à {{duration_years}} ans dans le territoire {{territory}}."
        ),
        "placeholders": [
            "athlete_name",
            "organisation_name",
            "duration_years",
            "territory",
        ],
        "is_mandatory": True,
    },
    {
        "slug": "clause-ethics-morality",
        "category": "ethics",
        "title": "Clause de moralité",
        "content": (
            "En cas de comportement de l’Athlète {{athlete_name}} susceptible de porter atteinte à l’image du Sponsor {{organisation_name}}, notamment en cas de propos "
            "discriminatoires, dopage, condamnation judiciaire, ou tout autre événement médiatique négatif, le Sponsor pourra résilier le contrat de plein droit et sans indemnité."
        ),
        "placeholders": ["athlete_name", "organisation_name"],
        "is_mandatory": False,
    },
    {
        "slug": "clause-confidentiality",
        "category": "confidentiality",
        "title": "Confidentialité des termes",
        "content": (
            "Les parties s’engagent à garder strictement confidentiels les termes du présent contrat, ainsi que toute information commerciale, stratégique ou financière échangée dans le cadre de son exécution."
        ),
        "placeholders": [],
        "is_mandatory": True,
    },
    {
        "slug": "clause-termination",
        "category": "termination",
        "title": "Résiliation anticipée",
        "content": (
            "Chaque partie pourra résilier le présent contrat en cas de manquement grave par l’autre partie à l’une de ses obligations contractuelles, sous réserve d’un préavis de {{notice_days}} jours notifié par écrit. "
            "La résiliation pourra intervenir de plein droit si le manquement n’est pas corrigé dans ce délai."
        ),
        "placeholders": ["notice_days"],
        "is_mandatory": True,
    },
    {
        "slug": "clause-law",
        "category": "administratives",
        "title": "Loi applicable et juridiction",
        "content": (
            "Le présent contrat est régi par le droit {{jurisdiction_country}}. Tout litige relatif à son interprétation ou son exécution sera porté devant le tribunal compétent de {{jurisdiction_city}}."
        ),
        "placeholders": ["jurisdiction_country", "jurisdiction_city"],
        "is_mandatory": True,
    },
]

for fixture in CLAUSE_TEMPLATE_FIXTURES:
    fixture["uuid"] = _generate_uuid(fixture["slug"])
    fixture.setdefault("version", 1)
