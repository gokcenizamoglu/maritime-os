from activity.views import ServiceRequestTimelineView
from checklists.views import ChecklistItemViewSet
from documents.views import DocumentViewSet, public_upload_view
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rules.views import RuleViewSet
from service_requests.views import ServiceRequestViewSet
from users.views import CsrfBootstrapView, LoginView, LogoutView, MeView
from workflow.views import WorkflowStepInstanceViewSet

router = DefaultRouter()
router.register("service-requests", ServiceRequestViewSet, basename="service-request")
router.register("documents", DocumentViewSet, basename="document")
router.register("checklist-items", ChecklistItemViewSet, basename="checklist-item")
router.register("workflow-steps", WorkflowStepInstanceViewSet, basename="workflow-step")
router.register("rules", RuleViewSet, basename="rule")

urlpatterns = [
    path("api/", include(router.urls)),
    # Internal staff authentication (Django session, BFF-relayed — see
    # docs/AUTHENTICATION_ARCHITECTURE.md). Kept outside the router:
    # these are four distinct actions, not CRUD over a resource.
    path("api/auth/csrf/", CsrfBootstrapView.as_view(), name="auth-csrf"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("api/auth/me/", MeView.as_view(), name="auth-me"),
    path(
        "api/service-requests/<int:service_request_id>/timeline/",
        ServiceRequestTimelineView.as_view(),
        name="service-request-timeline",
    ),
    # Public, unauthenticated customer upload portal — deliberately kept
    # OUTSIDE the authenticated router above, under its own namespace, so
    # it's immediately obvious in the URLconf which endpoints are exposed
    # to the open internet without auth.
    path("upload/<uuid:token>/", public_upload_view, name="public-upload"),
]
