from django.urls import path

from . import views

app_name = "domain_kit"

urlpatterns = [
    path("persons/", views.persons_page_view, name="persons"),
    path("persons/<int:pk>/photo/", views.person_photo_view, name="person_photo"),
    path("assets/", views.assets_page_view, name="assets"),
    path("documents/", views.documents_page_view, name="documents"),
    path("documents/<int:pk>/view/", views.view_document_view, name="document_view"),
    path("documents/<int:pk>/download/", views.download_document_view, name="document_download"),
    path("search/", views.global_search_view, name="search"),
    path("settings/", views.settings_page_view, name="settings"),
]
