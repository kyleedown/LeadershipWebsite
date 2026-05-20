from django.urls import path
from . import views

urlpatterns = [
    path("", views.quiz_list, name="quiz_list"),
    path("api/dimension-names/", views.dimension_names_api, name="dimension_names_api"),
    path("<slug:slug>/", views.quiz_detail, name="quiz_detail"),
    path("<slug:slug>/result/<slug:result_slug>/", views.quiz_result, name="quiz_result"),
]
