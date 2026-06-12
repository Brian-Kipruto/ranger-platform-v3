# ─── RANGER V3 START: data explorer pagination ───
"""
Custom pagination for the Data Explorer list endpoint.

V2 parity (V2 docs §3.1.4): default page_size 25, client-tunable via the
`limit` query param up to a hard ceiling of 1000. Only the list endpoint
uses this — export, chart-data, and map-data are deliberately unpaginated
(they return full filtered sets, point-capped where needed).
"""
from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "limit"
    max_page_size = 1000
# ─── RANGER V3 END: data explorer pagination ───