"""Seed the database with deterministic demo data for local development.

The command purposefully mirrors production relationships—agents own athletes,
organisations collaborate, and analytics contain recent daily stats—so developers
can interact with the project end-to-end. Inline comments describe why certain
choices are made (such as how followers counts are generated), while Google
style docstrings document arguments and return values for each helper.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

try:
    from faker import Faker
except ImportError as exc:  # pragma: no cover - import error is handled explicitly
    raise CommandError(
        "Faker is required to run this command. Install it with `pip install Faker`."
    ) from exc

from analytics.models import AthleteSocialAccount, DailyStats, SocialPlatform
from athletes.models import Athlete, Sport, SportDiscipline
from organisations.models import Collaborator, Organisation
from users.models import AgentProfile, User


DEFAULT_PASSWORD = "Passw0rd!"


class Command(BaseCommand):
    """Seed the database with deterministic yet realistic looking data.

    Attributes:
        help: Short description surfaced by Django's ``manage.py help`` output.
    """

    help = (
        "Populate the database with demo data covering users, organisations, sports, "
        "athletes and basic analytics."
    )

    def add_arguments(self, parser):
        """Configure CLI arguments for the seed command.

        Args:
            parser: The argument parser provided by Django.
        """
        parser.add_argument(
            "--agents",
            type=int,
            default=5,
            help="Number of agent users to create.",
        )
        parser.add_argument(
            "--organisations",
            type=int,
            default=5,
            help="Number of organisations to create.",
        )
        parser.add_argument(
            "--sports",
            type=int,
            default=6,
            help="Number of sports to create.",
        )
        parser.add_argument(
            "--athletes",
            type=int,
            default=15,
            help="Number of athletes to create.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional Faker seed for reproducibility.",
        )

    def handle(self, *args, **options):
        """Execute the seed process using the provided options.

        Args:
            *args: Positional arguments required by Django's command contract.
            **options: Parsed command line options controlling record counts.
        """
        faker = Faker()
        if options["seed"] is not None:
            Faker.seed(options["seed"])
            random.seed(options["seed"])

        agents = options["agents"]
        organisations = options["organisations"]
        sports = options["sports"]
        athletes = options["athletes"]

        with transaction.atomic():
            # Each helper returns the objects it created so downstream steps can
            # wire relationships together without additional queries.
            agent_profiles = self._create_agents(faker, agents)
            sports_created = self._create_sports(faker, sports)
            organisations_created = self._create_organisations(
                faker,
                organisations,
            )
            athletes_created = self._create_athletes(
                faker,
                athletes,
                agent_profiles,
                sports_created,
            )
            self._create_athlete_stats(faker, athletes_created)

        message = (
            f"Seed completed: {len(agent_profiles)} agents, "
            f"{len(organisations_created)} organisations, "
            f"{len(sports_created)} sports, {len(athletes_created)} athletes."
        )
        self.stdout.write(self.style.SUCCESS(message))

    # ------------------------------------------------------------------
    # Creation helpers
    # ------------------------------------------------------------------

    def _create_agents(self, faker: Faker, count: int) -> list[AgentProfile]:
        """Create agent users with associated profiles.

        Args:
            faker: Shared Faker instance for deterministic fake data.
            count: Number of agents to create.

        Returns:
            list[AgentProfile]: Persisted agent profiles linked to new users.
        """
        profiles: list[AgentProfile] = []
        for _ in range(count):
            email = faker.unique.email()
            full_name = faker.name()
            first_name, _, last_name = full_name.partition(" ")
            user = User.objects.create_user(
                email=email,
                password=DEFAULT_PASSWORD,
                first_name=first_name,
                last_name=last_name,
            )
            AgentProfile.objects.create(
                user=user,
                bio=faker.paragraph(nb_sentences=3),
            )
            # Re-accessing ``user.agent_profile`` ensures the relation is loaded
            # with the correct default values before appending to the list.
            profiles.append(user.agent_profile)
        return profiles

    def _create_sports(self, faker: Faker, count: int) -> list[Sport]:
        """Create a set of sports with unique names.

        Args:
            faker: Shared Faker instance for deterministic fake data.
            count: Number of sports to generate.

        Returns:
            list[Sport]: Newly created sports ready to be linked to athletes.
        """
        sports: list[Sport] = []
        categories = [choice[0] for choice in Sport.Category.choices]
        for _ in range(count):
            sport = Sport.objects.create(
                name=faker.unique.catch_phrase(),
                emoji=faker.random_element(["🏀", "⚽", "🏈", "🎾", "🥊", "🏐", "🚴"]),
                category=random.choice(categories),
            )
            SportDiscipline.objects.create(
                sport=sport,
                name=faker.word().title(),
                description=faker.sentence(nb_words=6),
                is_olympic=faker.pybool(),
            )
            sports.append(sport)
        return sports

    def _create_organisations(
        self,
        faker: Faker,
        count: int,
    ) -> list[Organisation]:
        """Create organisations with dedicated collaborator owners.

        Args:
            faker: Shared Faker instance for deterministic fake data.
            count: Number of organisations to generate.

        Returns:
            list[Organisation]: Persisted organisations with owner records.
        """
        organisations: list[Organisation] = []
        if count <= 0:
            return organisations

        for _ in range(count):
            email = faker.unique.email()
            full_name = faker.name()
            first_name, _, last_name = full_name.partition(" ")

            owner = User.objects.create_user(
                email=email,
                password=DEFAULT_PASSWORD,
                first_name=first_name,
                last_name=last_name,
                account_type=User.AccountType.COLLABORATOR,
            )
            industry = faker.job().title()
            social_links = {
                "linkedin": faker.url(),
                "instagram": faker.url(),
                "x": faker.url(),
                "facebook": faker.url(),
                "tiktok": faker.url(),
                "youtube": faker.url(),
            }
            organisation = Organisation.objects.create(
                owner=owner,
                name=faker.unique.company(),
                type=random.choice([choice[0] for choice in Organisation.Type.choices]),
                industry=industry,
                description=faker.paragraph(nb_sentences=4),
                website_url=faker.url(),
                email_contact=faker.company_email(),
                phone_contact=faker.phone_number(),
                address_city=faker.city(),
                address_country=faker.country_code(representation="alpha-2"),
                address_postal_code=faker.postcode(),
                social_links=social_links,
                founded_year=random.randint(1970, date.today().year - 1),
                employees_count=random.choice([1, 3, 10, 50, 100, 250]),
                budget_range=random.choice(["<10k", "10k-100k", ">100k"]),
                sponsoring_focus=[faker.word(), faker.word(), faker.word()],
            )
            Collaborator.objects.create(
                user=owner,
                organisation=organisation,
                role=Collaborator.Role.OWNER,
                job_title=faker.job().title(),
            )
            organisations.append(organisation)
        return organisations

    def _create_athletes(
        self,
        faker: Faker,
        count: int,
        agent_profiles: list[AgentProfile],
        sports: list[Sport],
    ) -> list[Athlete]:
        """Create athletes linked to sports and agents.

        Args:
            faker: Shared Faker instance for deterministic fake data.
            count: Number of athletes to create.
            agent_profiles: Pool of agents available for assignment.
            sports: Sports created earlier in the seed run.

        Returns:
            list[Athlete]: Persisted athletes containing base profile data.
        """
        athletes_created: list[Athlete] = []
        if not agent_profiles or not sports:
            return athletes_created

        for _ in range(count):
            sport = random.choice(sports)
            agent = random.choice(agent_profiles)
            birth_years = random.randint(18, 35)
            athlete = Athlete.objects.create(
                sport=sport,
                agent=agent,
                full_name=faker.name(),
                birth_date=date.today() - timedelta(days=birth_years * 365),
                nationality=faker.country_code(representation="alpha-2"),
                country=faker.country(),
                city=faker.city(),
                bio=faker.paragraph(nb_sentences=3),
                social_links={
                    "instagram": faker.user_name(),
                    "twitter": faker.user_name(),
                },
                followers_count_cached=faker.random_int(min=5_000, max=200_000),
                engagement_rate_cached=round(random.uniform(0.5, 10.0), 2),
            )
            disciplines = list(sport.disciplines.all())
            if disciplines:
                max_sample = max(1, len(disciplines))
                count = min(len(disciplines), random.randint(1, max_sample))
                athlete.disciplines.set(random.sample(disciplines, count))
            # Storing the object in a list allows the analytics seeding step to
            # build social accounts for the same set of athletes.
            athletes_created.append(athlete)
        return athletes_created

    def _create_athlete_stats(self, faker: Faker, athletes: list[Athlete]) -> None:
        """Create demo social accounts and populate daily stats.

        Args:
            faker: Shared Faker instance for deterministic fake data.
            athletes: List of athletes needing social analytics.

        Returns:
            None
        """

        if not athletes:
            return

        platforms = {
            choice: SocialPlatform.objects.get_or_create(name=choice)[0]
            for choice, _ in SocialPlatform.Platform.choices
        }

        for athlete in athletes:
            platform_choice = faker.random_element(list(platforms.keys()))
            account = AthleteSocialAccount.objects.create(
                athlete=athlete,
                platform=platforms[platform_choice],
                username=faker.user_name(),
                external_id=faker.uuid4(),
                is_active=True,
            )
            for offset in range(5):
                stat_date = date.today() - timedelta(days=offset)
                followers = faker.random_int(min=5_000, max=250_000)
                DailyStats.objects.create(
                    account=account,
                    date=stat_date,
                    followers=followers,
                    following=faker.random_int(min=100, max=10_000),
                    posts_count=faker.random_int(min=0, max=5),
                    likes=faker.random_int(min=0, max=20_000),
                    comments=faker.random_int(min=0, max=3_000),
                    shares=faker.random_int(min=0, max=5_000),
                    views=faker.random_int(min=0, max=200_000),
                    watch_time=round(random.uniform(10.0, 800.0), 2),
                    top_post={
                        "post_id": faker.uuid4(),
                        "likes": faker.random_int(min=0, max=10_000),
                        "comments": faker.random_int(min=0, max=1_000),
                        "engagement_rate": round(random.uniform(0.5, 15.0), 2),
                    },
                )
