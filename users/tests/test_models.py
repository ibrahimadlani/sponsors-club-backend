import pytest
from django.utils import timezone

from users.models import AgentProfile, EmailVerificationToken


@pytest.mark.django_db
def test_user_save_normalises_blank_phone_fields(user_model):
    user = user_model.objects.create_user(
        email="normalize@example.com",
        password="pass1234",
        phone_country_code="",
        phone_number="",
    )

    # Saving should coerce empty strings to ``None`` for nullable columns.
    user.save()
    user.refresh_from_db()

    assert user.phone_country_code is None
    assert user.phone_number is None


@pytest.mark.django_db
def test_agent_profile_str_falls_back_to_user_email(user_model):
    user = user_model.objects.create_user(email="fallback@example.com", password="pass1234")
    profile = AgentProfile.objects.create(user=user)

    assert str(profile) == str(user)
    assert profile.name == str(user)


@pytest.mark.django_db
def test_user_slug_is_generated_from_name(user_model):
    user = user_model.objects.create_user(
        email="named@example.com",
        password="pass1234",
        first_name="Named",
        last_name="User",
    )

    assert user.slug == "named-user"


@pytest.mark.django_db
def test_user_slug_deduplicates(user_model):
    user_model.objects.create_user(
        email="duplicate1@example.com",
        password="pass1234",
        first_name="Same",
        last_name="Name",
    )
    other = user_model.objects.create_user(
        email="duplicate2@example.com",
        password="pass1234",
        first_name="Same",
        last_name="Name",
    )

    assert other.slug.startswith("same-name-")


@pytest.mark.django_db
def test_email_verification_token_verify_rejects_expired_token(user_model):
    user = user_model.objects.create_user(email="expire@example.com", password="pass1234")
    raw_token = EmailVerificationToken.issue_for_user(user)

    token = EmailVerificationToken.objects.get(user=user)
    token.expires_at = timezone.now() - timezone.timedelta(hours=1)
    token.save(update_fields=["expires_at", "updated_at"])

    assert EmailVerificationToken.verify(user, raw_token) is None
