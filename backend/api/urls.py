from django.urls import path

from . import views

urlpatterns = [
    path("analyses", views.analysis_create),
    path("analyses/<uuid:pk>", views.AnalysisDetail.as_view()),
    path("analyses/<uuid:pk>/events", views.analysis_events),
    path("ads", views.AdList.as_view()),
    path("ads/<int:pk>", views.AdDetail.as_view()),
    path("ads/<int:pk>/edges", views.AdEdges.as_view()),
    path("ads/<int:pk>/recluster", views.ad_recluster),
    path("edges/<int:pk>", views.EdgeDetail.as_view()),
    path("edges/<int:pk>/verdict", views.edge_verdict),
    path("campaigns", views.CampaignList.as_view()),
    path("campaigns/<int:pk>", views.campaign_detail),
    path("graph", views.graph),
    path("kinds", views.kinds),
    path("artifacts/<str:sha256>", views.artifact),
]
