from django.urls import path

from . import views

app_name = "domain_kit"

urlpatterns = [
    path("persons/", views.persons_page_view, name="persons"),
    path("assets/", views.assets_page_view, name="assets"),
    path("documents/", views.documents_page_view, name="documents"),
    path("search/", views.global_search_view, name="search"),
    path("settings/", views.settings_page_view, name="settings"),
]
