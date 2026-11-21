from django.urls import path

from . import views

urlpatterns = [
    path("analyses", views.analysis_create),
    path("analyses/upload", views.analysis_upload),
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
    path("campaigns/<int:pk>/timeline", views.campaign_timeline),
    path("operators", views.OperatorList.as_view()),
    path("operators/<int:pk>", views.operator_detail),
    path("operators/<int:pk>/timeline", views.operator_timeline),
    path("graph", views.graph),
    path("kinds", views.kinds),
    path("stats", views.stats),
    path("artifacts/<str:sha256>", views.artifact),
    path("artifacts/<str:sha256>/image", views.artifact_image),
]
