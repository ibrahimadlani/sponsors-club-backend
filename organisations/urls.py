"""URL routes for the organisations app."""

from rest_framework.routers import DefaultRouter

from .views import OrganisationViewSet

router = DefaultRouter()
router.register(r'organisations', OrganisationViewSet, basename='organisation')

urlpatterns = router.urls
