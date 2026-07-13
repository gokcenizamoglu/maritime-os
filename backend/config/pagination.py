"""
Shared pagination config for list endpoints — one place so every
paginated endpoint returns the identical `{count, next, previous,
results}` envelope, rather than each viewset inventing its own paging
convention.

WHY NOT `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]` IN SETTINGS: that
would apply to every ModelViewSet/ReadOnlyModelViewSet in the project,
including `checklist-items` and `workflow-steps` — both already consumed
by the frontend as plain arrays (they're always small, filtered-by-one-
service-request result sets; see the Operations detail page). Silently
wrapping those in a paginated envelope would be an undocumented breaking
change outside this sprint's scope (ServiceRequest + Document only).
Applying `pagination_class` explicitly, per-viewset, keeps the blast
radius to exactly the two endpoints this sprint is about.
"""
from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
    """
    Page size chosen for a dense operations table (see
    docs/DESIGN_SYSTEM.md — 13px dense table rows): 25 rows is enough to
    fill a typical desktop viewport without scrolling on load, without
    being so large that a slow tenant with thousands of cases pays for
    an oversized default response.

    Client-provided page size is bounded, not unlimited — `max_page_size`
    exists specifically so `?page_size=100000` can't be used to bypass
    pagination entirely and pull an unbounded result set in one request.
    """
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
