from django.urls import re_path

from . import views

app_name = 'osf'

urlpatterns = [
    re_path(r'^$', views.PreprintList.as_view(), name=views.PreprintList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/$', views.PreprintDetail.as_view(), name=views.PreprintDetail.view_name),
    re_path(r'^(?P<preprint_id>\w+)/bibliographic_contributors/$', views.PreprintBibliographicContributorsList.as_view(), name=views.PreprintBibliographicContributorsList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/citation/$', views.PreprintCitationDetail.as_view(), name=views.PreprintCitationDetail.view_name),
    re_path(r'^(?P<preprint_id>\w+)/citation/(?P<style_id>[-\w]+)/$', views.PreprintCitationStyleDetail.as_view(), name=views.PreprintCitationStyleDetail.view_name),
    re_path(r'^(?P<preprint_id>\w+)/contributors/$', views.PreprintContributorsList.as_view(), name=views.PreprintContributorsList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/contributors/(?P<user_id>\w+)/$', views.PreprintContributorDetail.as_view(), name=views.PreprintContributorDetail.view_name),
    re_path(r'^(?P<preprint_id>\w+)/files/$', views.PreprintStorageProvidersList.as_view(), name=views.PreprintStorageProvidersList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/files/osfstorage/$', views.PreprintFilesList.as_view(), name=views.PreprintFilesList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/identifiers/$', views.PreprintIdentifierList.as_view(), name=views.PreprintIdentifierList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/institutions/$', views.PreprintInstitutionsList.as_view(), name=views.PreprintInstitutionsList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/relationships/institutions/$', views.PreprintInstitutionsRelationship.as_view(), name=views.PreprintInstitutionsRelationship.view_name),
    re_path(r'^(?P<preprint_id>\w+)/relationships/node/$', views.PreprintNodeRelationship.as_view(), name=views.PreprintNodeRelationship.view_name),
    re_path(r'^(?P<preprint_id>\w+)/relationships/subjects/$', views.PreprintSubjectsRelationship.as_view(), name=views.PreprintSubjectsRelationship.view_name),
    re_path(r'^(?P<preprint_id>\w+)/review_actions/$', views.PreprintActionList.as_view(), name=views.PreprintActionList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/requests/$', views.PreprintRequestListCreate.as_view(), name=views.PreprintRequestListCreate.view_name),
    re_path(r'^(?P<preprint_id>\w+)/subjects/$', views.PreprintSubjectsList.as_view(), name=views.PreprintSubjectsList.view_name),
    re_path(r'^(?P<preprint_id>\w+)/versions/$', views.PreprintVersionsList.as_view(), name=views.PreprintVersionsList.view_name),
]
