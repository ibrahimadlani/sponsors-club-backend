import pytest

from athletes.models import Athlete, AthleteDiscipline, Sport, SportDiscipline
from users.models import AgentProfile


@pytest.mark.django_db
def test_sport_slug_deduplicates():
    first = Sport.objects.create(name="A B", emoji="🎯")
    second = Sport.objects.create(name="A-B", emoji="🎯")
    assert first.slug == "a-b"
    assert second.slug.startswith("a-b-")


@pytest.mark.django_db
def test_sport_discipline_slug_deduplicates():
    sport = Sport.objects.create(name="Cycling")
    first = SportDiscipline.objects.create(sport=sport, name="Time Trial")
    second = SportDiscipline.objects.create(sport=sport, name="Time-Trial")
    assert first.slug == "time-trial"
    assert second.slug.startswith("time-trial-")


@pytest.mark.django_db
def test_athlete_slug_deduplicates(agent_user):
    sport = Sport.objects.create(name="Boxing")
    agent = AgentProfile.objects.get(user=agent_user)

    first = Athlete.objects.create(
        sport=sport,
        agent=agent,
        full_name="Jane Doe",
        birth_date="1998-05-05",
        nationality="GB",
    )
    second = Athlete.objects.create(
        sport=sport,
        agent=agent,
        full_name="Jane-Doe",
        birth_date="1998-05-05",
        nationality="GB",
    )

    assert first.slug == "jane-doe"
    assert second.slug.startswith("jane-doe-")


@pytest.mark.django_db
def test_athlete_discipline_clean_valid(agent_user):
    sport = Sport.objects.create(name="Swimming")
    discipline = SportDiscipline.objects.create(sport=sport, name="200m Freestyle")
    athlete = Athlete.objects.create(
        sport=sport,
        agent=AgentProfile.objects.get(user=agent_user),
        full_name="Test Swimmer",
        birth_date="2000-01-01",
        nationality="FR",
    )
    link = AthleteDiscipline(athlete=athlete, discipline=discipline)
    # Should not raise validation errors
    link.save()
    assert athlete.disciplines.count() == 1


@pytest.mark.django_db
def test_athlete_discipline_clean_invalid(agent_user):
    sport = Sport.objects.create(name="Athletics")
    other_sport = Sport.objects.create(name="Rowing")
    discipline = SportDiscipline.objects.create(sport=other_sport, name="Single Sculls")
    athlete = Athlete.objects.create(
        sport=sport,
        agent=AgentProfile.objects.get(user=agent_user),
        full_name="Runner",
        birth_date="1999-02-02",
        nationality="FR",
    )
    with pytest.raises(Exception):
        AthleteDiscipline.objects.create(athlete=athlete, discipline=discipline)
