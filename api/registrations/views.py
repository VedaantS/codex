from rest_framework import generics, mixins, permissions as drf_permissions, status
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from rest_framework.response import Response
from framework.exceptions import HTTPError
from framework.auth.oauth_scopes import CoreScopes

from addons.base.views import DOWNLOAD_ACTIONS
from website.archiver import signals, ARCHIVER_NETWORK_ERROR, ARCHIVER_SUCCESS, ARCHIVER_FAILURE
from website.project import signals as project_signals

from osf.models import Registration, OSFUser, RegistrationProvider, OutcomeArtifact, CedarMetadataRecord
from osf.utils.permissions import WRITE_NODE
from osf.utils.workflows import ApprovalStates

from api.base import permissions as base_permissions
from api.base import generic_bulk_views as bulk_views
from api.base.exceptions import Gone
from api.base.filters import ListFilterMixin
from api.base.views import (
    JSONAPIBaseView,
    BaseChildrenList,
    BaseContributorDetail,
    BaseContributorList,
    BaseNodeLinksDetail,
    BaseNodeLinksList,
    WaterButlerMixin,
)
from api.base.serializers import HideIfWithdrawal, LinkedRegistrationsRelationshipSerializer
from api.base.serializers import LinkedNodesRelationshipSerializer
from api.base.pagination import NodeContributorPagination
from api.base.exceptions import Conflict
from api.base.parsers import (
    JSONAPIRelationshipParser,
    JSONAPIMultipleRelationshipsParser,
    JSONAPIRelationshipParserForRegularJSON,
    JSONAPIMultipleRelationshipsParserForRegularJSON,
    HMACSignedParser,
)
from api.base.utils import (
    get_user_auth,
    default_node_list_permission_queryset,
    is_bulk_request,
    is_truthy,
)
from api.cedar_metadata_records.serializers import CedarMetadataRecordsListSerializer
from api.cedar_metadata_records.utils import can_view_record
from api.comments.serializers import RegistrationCommentSerializer, CommentCreateSerializer
from api.draft_registrations.views import DraftMixin
from api.identifiers.serializers import RegistrationIdentifierSerializer
from api.nodes.views import NodeIdentifierList, NodeBibliographicContributorsList, NodeSubjectsList, NodeSubjectsRelationship
from api.users.views import UserMixin
from api.users.serializers import UserSerializer

from api.nodes.permissions import (
    ReadOnlyIfRegistration,
    ContributorDetailPermissions,
    ContributorOrPublic,
    ContributorOrPublicForRelationshipPointers,
    AdminOrPublic,
    ExcludeWithdrawals,
    NodeLinksShowIfVersion,
)
from api.registrations.permissions import ContributorOrModerator, ContributorOrModeratorOrPublic
from api.registrations.serializers import (
    RegistrationSerializer,
    RegistrationDetailSerializer,
    RegistrationContributorsSerializer,
    RegistrationContributorsCreateSerializer,
    RegistrationCreateSerializer,
    RegistrationStorageProviderSerializer,
)

from api.nodes.filters import NodesFilterMixin

from api.nodes.views import (
    NodeMixin, NodeRegistrationsList, NodeLogList,
    NodeCommentsList, NodeStorageProvidersList, NodeFilesList, NodeFileDetail,
    NodeInstitutionsList, NodeForksList, NodeWikiList, LinkedNodesList,
    NodeViewOnlyLinksList, NodeViewOnlyLinkDetail, NodeCitationDetail, NodeCitationStyleDetail,
    NodeLinkedRegistrationsList, NodeLinkedByNodesList, NodeLinkedByRegistrationsList, NodeInstitutionsRelationship,
)

from api.registrations.serializers import RegistrationNodeLinksSerializer, RegistrationFileSerializer
from api.wikis.serializers import RegistrationWikiSerializer

from api.base.utils import get_object_or_error
from api.actions.serializers import RegistrationActionSerializer
from api.requests.serializers import RegistrationRequestSerializer
from framework.sentry import log_exception
from osf.utils.permissions import ADMIN
from api.providers.permissions import MustBeModerator
from api.providers.views import ProviderMixin
from api.registrations import annotations

from api.resources import annotations as resource_annotations
from api.resources.permissions import RegistrationResourceListPermission
from api.resources.serializers import ResourceSerializer
from api.schema_responses import annotations as schema_response_annotations
from api.schema_responses.permissions import (
    MODERATOR_VISIBLE_STATES,
    RegistrationSchemaResponseListPermission,
)
from api.schema_responses.serializers import RegistrationSchemaResponseSerializer


class RegistrationMixin(NodeMixin):
    """Mixin with convenience methods for retrieving the current registration based on the
    current URL. By default, fetches the current registration based on the node_id kwarg.
    """

    serializer_class = RegistrationSerializer
    node_lookup_url_kwarg = 'node_id'

    def get_node(self, check_object_permissions=True, **annotations):
        guid = self.kwargs[self.node_lookup_url_kwarg]
        node = Registration.objects.filter(guids___id=guid).annotate(**annotations)

        try:
            node = node.get()
        except Registration.DoesNotExist:
            raise NotFound

        if node.deleted:
            raise Gone(detail='The requested registration is no longer available.')

        if check_object_permissions:
            self.check_object_permissions(self.request, node)

        return node


class RegistrationList(JSONAPIBaseView, generics.ListCreateAPIView, bulk_views.BulkUpdateJSONAPIView, NodesFilterMixin, DraftMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_list).
    """
    permission_classes = (
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
    )

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NODE_REGISTRATIONS_WRITE]

    serializer_class = RegistrationSerializer
    view_category = 'registrations'
    view_name = 'registration-list'

    ordering = ('-modified',)
    model_class = Registration

    parser_classes = (JSONAPIMultipleRelationshipsParser, JSONAPIMultipleRelationshipsParserForRegularJSON)

    # overrides BulkUpdateJSONAPIView
    def get_serializer_class(self):
        """
        Use RegistrationDetailSerializer which requires 'id'
        """
        if self.request.method in ('PUT', 'PATCH'):
            return RegistrationDetailSerializer
        elif self.request.method == 'POST':
            return RegistrationCreateSerializer
        else:
            return RegistrationSerializer

    # overrides NodesFilterMixin
    def get_default_queryset(self):
        return default_node_list_permission_queryset(
            user=self.request.user,
            model_cls=Registration,
            revision_state=annotations.REVISION_STATE,
            **resource_annotations.make_open_practice_badge_annotations(),
        )

    def is_blacklisted(self):
        query_params = self.parse_query_params(self.request.query_params)
        for key, field_names in query_params.items():
            for field_name, data in field_names.items():
                field = self.serializer_class._declared_fields.get(field_name)
                if isinstance(field, HideIfWithdrawal):
                    return True
        return False

    # overrides ListAPIView, ListBulkCreateJSONAPIView
    def get_queryset(self):
        # For bulk requests, queryset is formed from request body.
        if is_bulk_request(self.request):
            auth = get_user_auth(self.request)
            registrations = Registration.objects.filter(guids___id__in=[registration['id'] for registration in self.request.data])

            # If skip_uneditable=True in query_params, skip nodes for which the user
            # does not have EDIT permissions.
            if is_truthy(self.request.query_params.get('skip_uneditable', False)):
                return Registration.objects.get_nodes_for_user(auth.user, WRITE_NODE, registrations)

            for registration in registrations:
                if not registration.can_edit(auth):
                    raise PermissionDenied
            return registrations

        blacklisted = self.is_blacklisted()
        registrations = self.get_queryset_from_request()
        # If attempting to filter on a blacklisted field, exclude withdrawals.
        if blacklisted:
            registrations = registrations.exclude(retraction__isnull=False)

        return registrations.select_related(
            'root',
            'root__embargo',
            'root__embargo_termination_approval',
            'root__retraction',
            'root__registration_approval',
        )

    # overrides ListCreateJSONAPIView
    def perform_create(self, serializer):
        """Create a registration from a draft.
        """
        draft_id = self.request.data.get('draft_registration', None) or self.request.data.get('draft_registration_id', None)
        draft = self.get_draft(draft_id)
        user = get_user_auth(self.request).user

        # A user have admin perms on the draft to register
        if draft.has_permission(user, ADMIN):
            try:
                serializer.save(draft=draft)
            except ValidationError as e:
                log_exception(e)
                raise e
        else:
            raise PermissionDenied(
                'You must be an admin contributor on the draft registration to create a registration.',
            )

    def check_branched_from(self, draft):
        # Overrides DraftMixin - no node_id in kwargs
        return


class RegistrationDetail(JSONAPIBaseView, generics.RetrieveUpdateAPIView, RegistrationMixin, WaterButlerMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_read).
    """
    permission_classes = (
        drf_permissions.IsAuthenticatedOrReadOnly,
        ContributorOrModeratorOrPublic,
        base_permissions.TokenHasScope,
    )

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NODE_REGISTRATIONS_WRITE]

    serializer_class = RegistrationDetailSerializer
    view_category = 'registrations'
    view_name = 'registration-detail'

    parser_classes = (JSONAPIMultipleRelationshipsParser, JSONAPIMultipleRelationshipsParserForRegularJSON)

    # overrides RetrieveAPIView
    def get_object(self):
        registration = self.get_node(
            revision_state=annotations.REVISION_STATE,
            **resource_annotations.make_open_practice_badge_annotations(),
        )
        if not registration.is_registration:
            raise ValidationError('This is not a registration.')

        return registration

    def get_serializer_context(self):
        context = super().get_serializer_context()
        show_counts = is_truthy(self.request.query_params.get('related_counts', False))
        if show_counts:
            registration = self.get_object()
            context['meta'] = {
                'templated_by_count': registration.templated_list.count(),
            }
        return context


class RegistrationContributorsList(BaseContributorList, mixins.CreateModelMixin, RegistrationMixin, UserMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_contributors_list).
    """
    view_category = 'registrations'
    view_name = 'registration-contributors'

    pagination_class = NodeContributorPagination
    serializer_class = RegistrationContributorsSerializer

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NODE_REGISTRATIONS_WRITE]

    ordering = ('_order',)

    permission_classes = (
        ContributorDetailPermissions,
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
    )

    def get_resource(self):
        return self.get_node(check_object_permissions=False)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RegistrationContributorsCreateSerializer

        return self.serializer_class

    def post(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def get_default_queryset(self):
        node = self.get_resource()
        return node.contributor_set.all().prefetch_related('user__guids')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['resource'] = self.get_resource()
        context['default_email'] = 'default'
        return context


class RegistrationContributorDetail(BaseContributorDetail, mixins.UpdateModelMixin, mixins.DestroyModelMixin, RegistrationMixin, UserMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_contributors_read).
    """
    view_category = 'registrations'
    view_name = 'registration-contributor-detail'
    serializer_class = RegistrationContributorsSerializer

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NODE_REGISTRATIONS_WRITE]

    permission_classes = (
        ContributorDetailPermissions,
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
    )

    def get_resource(self):
        return self.get_node()

    def patch(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['resource'] = self.get_resource()
        context['default_email'] = 'default'
        return context

    def perform_destroy(self, instance):
        node = self.get_resource()
        auth = get_user_auth(self.request)
        if node.visible_contributors.count() == 1 and instance.visible:
            raise ValidationError('Must have at least one visible contributor')
        removed = node.remove_contributor(instance, auth)
        if not removed:
            raise ValidationError('Must have at least one registered admin contributor')


class RegistrationBibliographicContributorsList(NodeBibliographicContributorsList, RegistrationMixin):

    pagination_class = NodeContributorPagination
    serializer_class = RegistrationContributorsSerializer

    view_category = 'registrations'
    view_name = 'registration-bibliographic-contributors'


class RegistrationImplicitContributorsList(JSONAPIBaseView, generics.ListAPIView, ListFilterMixin, RegistrationMixin):
    permission_classes = (
        AdminOrPublic,
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
    )

    required_read_scopes = [CoreScopes.NODE_CONTRIBUTORS_READ]
    required_write_scopes = [CoreScopes.NULL]

    model_class = OSFUser

    serializer_class = UserSerializer
    view_category = 'registrations'
    view_name = 'registration-implicit-contributors'
    ordering = ('contributor___order',)  # default ordering

    def get_default_queryset(self):
        node = self.get_node()

        return node.parent_admin_contributors

    def get_queryset(self):
        queryset = self.get_queryset_from_request()
        return queryset


class RegistrationChildrenList(BaseChildrenList, generics.ListAPIView, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_children_list).
    """
    view_category = 'registrations'
    view_name = 'registration-children'
    serializer_class = RegistrationSerializer

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NULL]

    model_class = Registration


class RegistrationCitationDetail(NodeCitationDetail, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_citations_list).
    """
    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]

    view_category = 'registrations'
    view_name = 'registration-citation'


class RegistrationCitationStyleDetail(NodeCitationStyleDetail, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_citation_read).
    """
    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]

    view_category = 'registrations'
    view_name = 'registration-style-citation'


class RegistrationForksList(NodeForksList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_forks_list).
    """
    view_category = 'registrations'
    view_name = 'registration-forks'

class RegistrationCommentsList(NodeCommentsList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_comments_list).
    """
    serializer_class = RegistrationCommentSerializer
    view_category = 'registrations'
    view_name = 'registration-comments'

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CommentCreateSerializer
        else:
            return RegistrationCommentSerializer


class RegistrationLogList(NodeLogList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_logs_list).
    """
    view_category = 'registrations'
    view_name = 'registration-logs'


class RegistrationStorageProvidersList(NodeStorageProvidersList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_providers_list).
    """
    serializer_class = RegistrationStorageProviderSerializer

    view_category = 'registrations'
    view_name = 'registration-storage-providers'


class RegistrationNodeLinksList(BaseNodeLinksList, RegistrationMixin):
    """Node Links to other nodes. *Writeable*.

    Node Links act as pointers to other nodes. Unlike Forks, they are not copies of nodes;
    Node Links are a direct reference to the node that they point to.

    ##Node Link Attributes
    `type` is "node_links"

        None

    ##Links

    See the [JSON-API spec regarding pagination](http://jsonapi.org/format/1.0/#fetching-pagination).

    ##Relationships

    ### Target Node

    This endpoint shows the target node detail and is automatically embedded.

    ##Actions

    ###Adding Node Links
        Method:        POST
        URL:           /links/self
        Query Params:  <none>
        Body (JSON): {
                       "data": {
                          "type": "node_links",                  # required
                          "relationships": {
                            "nodes": {
                              "data": {
                                "type": "nodes",                 # required
                                "id": "{target_node_id}",        # required
                              }
                            }
                          }
                       }
                    }
        Success:       201 CREATED + node link representation

    To add a node link (a pointer to another node), issue a POST request to this endpoint.  This effectively creates a
    relationship between the node and the target node.  The target node must be described as a relationship object with
    a "data" member, containing the nodes `type` and the target node `id`.

    ##Query Params

    + `page=<Int>` -- page number of results to view, default 1

    + `filter[<fieldname>]=<Str>` -- fields and values to filter the search results on.

    #This Request/Response
    """
    view_category = 'registrations'
    view_name = 'registration-pointers'
    serializer_class = RegistrationNodeLinksSerializer
    permission_classes = (
        drf_permissions.IsAuthenticatedOrReadOnly,
        ContributorOrPublic,
        ReadOnlyIfRegistration,
        base_permissions.TokenHasScope,
        ExcludeWithdrawals,
        NodeLinksShowIfVersion,
    )

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NULL]

    # TODO: This class doesn't exist
    # model_class = Pointer


class RegistrationNodeLinksDetail(BaseNodeLinksDetail, RegistrationMixin):
    """Node Link details. *Writeable*.

    Node Links act as pointers to other nodes. Unlike Forks, they are not copies of nodes;
    Node Links are a direct reference to the node that they point to.

    ##Attributes
    `type` is "node_links"

        None

    ##Links

    *None*

    ##Relationships

    ###Target node

    This endpoint shows the target node detail and is automatically embedded.

    ##Actions

    ###Remove Node Link

        Method:        DELETE
        URL:           /links/self
        Query Params:  <none>
        Success:       204 No Content

    To remove a node link from a node, issue a DELETE request to the `self` link.  This request will remove the
    relationship between the node and the target node, not the nodes themselves.

    ##Query Params

    *None*.

    #This Request/Response
    """
    view_category = 'registrations'
    view_name = 'registration-pointer-detail'
    serializer_class = RegistrationNodeLinksSerializer

    permission_classes = (
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
        ExcludeWithdrawals,
        NodeLinksShowIfVersion,
    )
    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NULL]

    # TODO: this class doesn't exist
    # model_class = Pointer

    # overrides RetrieveAPIView
    def get_object(self):
        registration = self.get_node()
        if not registration.is_registration:
            raise ValidationError('This is not a registration.')
        return registration


class RegistrationLinkedByNodesList(NodeLinkedByNodesList, RegistrationMixin):
    view_category = 'registrations'
    view_name = 'registration-linked-by-nodes'


class RegistrationLinkedByRegistrationsList(NodeLinkedByRegistrationsList, RegistrationMixin):
    view_category = 'registrations'
    view_name = 'registration-linked-by-registrations'


class RegistrationRegistrationsList(NodeRegistrationsList, RegistrationMixin):
    """List of registrations of a registration."""
    view_category = 'registrations'
    view_name = 'registration-registrations'


class RegistrationFilesList(NodeFilesList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_files_list).
    """
    view_category = 'registrations'
    view_name = 'registration-files'

    ordering_fields = ['modified', 'name', 'date_modified']
    serializer_class = RegistrationFileSerializer


class RegistrationFileDetail(NodeFileDetail, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_files_read).
    """
    view_category = 'registrations'
    view_name = 'registration-file-detail'
    serializer_class = RegistrationFileSerializer


class RegistrationInstitutionsList(NodeInstitutionsList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_institutions_list).
    """
    view_category = 'registrations'
    view_name = 'registration-institutions'


class RegistrationSubjectsList(NodeSubjectsList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_subjects_list).
    """
    view_category = 'registrations'
    view_name = 'registration-subjects'

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]


class RegistrationSubjectsRelationship(NodeSubjectsRelationship, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_subjects_relationship).
    """

    required_read_scopes = [CoreScopes.NODE_REGISTRATIONS_READ]
    required_write_scopes = [CoreScopes.NODE_REGISTRATIONS_WRITE]

    view_category = 'registrations'
    view_name = 'registration-relationships-subjects'


class RegistrationInstitutionsRelationship(NodeInstitutionsRelationship, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_institutions_relationship).
    """
    view_category = 'registrations'
    view_name = 'registration-relationships-institutions'

    permission_classes = (
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
        AdminOrPublic,
    )


class RegistrationWikiList(NodeWikiList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_wikis_list).
    """
    view_category = 'registrations'
    view_name = 'registration-wikis'

    serializer_class = RegistrationWikiSerializer


class RegistrationLinkedNodesList(LinkedNodesList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_linked_nodes_list).
    """
    view_category = 'registrations'
    view_name = 'linked-nodes'


class RegistrationLinkedNodesRelationship(JSONAPIBaseView, generics.RetrieveAPIView, RegistrationMixin):
    """ Relationship Endpoint for Nodes -> Linked Node relationships

    Used to retrieve the ids of the linked nodes attached to this collection. For each id, there
    exists a node link that contains that node.

    ##Actions

    """
    view_category = 'registrations'
    view_name = 'node-pointer-relationship'

    permission_classes = (
        ContributorOrPublicForRelationshipPointers,
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
        ReadOnlyIfRegistration,
    )

    required_read_scopes = [CoreScopes.NODE_LINKS_READ]
    required_write_scopes = [CoreScopes.NULL]

    serializer_class = LinkedNodesRelationshipSerializer
    parser_classes = (JSONAPIRelationshipParser, JSONAPIRelationshipParserForRegularJSON)

    def get_object(self):
        node = self.get_node(check_object_permissions=False)
        auth = get_user_auth(self.request)
        obj = {
            'data': [
                linked_node for linked_node in
                node.linked_nodes.filter(is_deleted=False).exclude(type='osf.collection').exclude(type='osf.registration')
                if linked_node.can_view(auth)
            ], 'self': node,
        }
        self.check_object_permissions(self.request, obj)
        return obj


class RegistrationLinkedRegistrationsRelationship(JSONAPIBaseView, generics.RetrieveAPIView, RegistrationMixin):
    """Relationship Endpoint for Registration -> Linked Registration relationships. *Read-only*

    Used to retrieve the ids of the linked registrations attached to this collection. For each id, there
    exists a node link that contains that registration.
    """

    view_category = 'registrations'
    view_name = 'node-registration-pointer-relationship'

    permission_classes = (
        ContributorOrPublicForRelationshipPointers,
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
        ReadOnlyIfRegistration,
    )

    required_read_scopes = [CoreScopes.NODE_LINKS_READ]
    required_write_scopes = [CoreScopes.NULL]

    serializer_class = LinkedRegistrationsRelationshipSerializer
    parser_classes = (JSONAPIRelationshipParser, JSONAPIRelationshipParserForRegularJSON)

    def get_object(self):
        node = self.get_node(check_object_permissions=False)
        auth = get_user_auth(self.request)
        obj = {
            'data': [
                linked_registration for linked_registration in
                node.linked_nodes.filter(is_deleted=False, type='osf.registration').exclude(type='osf.collection')
                if linked_registration.can_view(auth)
            ],
            'self': node,
        }
        self.check_object_permissions(self.request, obj)
        return obj


class RegistrationLinkedRegistrationsList(NodeLinkedRegistrationsList, RegistrationMixin):
    """List of registrations linked to this registration. *Read-only*.

    Linked registrations are the registration nodes pointed to by node links.

    <!--- Copied Spiel from RegistrationDetail -->
    Registrations are read-only snapshots of a project. This view shows details about the given registration.

    Each resource contains the full representation of the registration, meaning additional requests to an individual
    registration's detail view are not necessary. A withdrawn registration will display a limited subset of information,
    namely, title, description, created, registration, withdrawn, date_registered, withdrawal_justification, and
    registration supplement. All other fields will be displayed as null. Additionally, the only relationships permitted
    to be accessed for a withdrawn registration are the contributors - other relationships will return a 403.

    ##Linked Registration Attributes

    <!--- Copied Attributes from RegistrationDetail -->

    Registrations have the "registrations" `type`.

        name                            type               description
        =======================================================================================================
        title                           string             title of the registered project or component
        description                     string             description of the registered node
        category                        string             bode category, must be one of the allowed values
        date_created                    iso8601 timestamp  timestamp that the node was created
        date_modified                   iso8601 timestamp  timestamp when the node was last updated
        tags                            array of strings   list of tags that describe the registered node
        current_user_can_comment        boolean            Whether the current user is allowed to post comments
        current_user_permissions        array of strings   list of strings representing the permissions for the current user on this node
        fork                            boolean            is this project a fork?
        registration                    boolean            has this project been registered? (always true - may be deprecated in future versions)
        collection                      boolean            is this registered node a collection? (always false - may be deprecated in future versions)
        node_license                    object             details of the license applied to the node
        year                            string             date range of the license
        copyright_holders               array of strings   holders of the applied license
        public                          boolean            has this registration been made publicly-visible?
        withdrawn                       boolean            has this registration been withdrawn?
        date_registered                 iso8601 timestamp  timestamp that the registration was created
        embargo_end_date                iso8601 timestamp  when the embargo on this registration will be lifted (if applicable)
        withdrawal_justification        string             reasons for withdrawing the registration
        pending_withdrawal              boolean            is this registration pending withdrawal?
        pending_withdrawal_approval     boolean            is this registration pending approval?
        pending_embargo_approval        boolean            is the associated Embargo awaiting approval by project admins?
        registered_meta                 dictionary         registration supplementary information
        registration_supplement         string             registration template

    ##Links

    See the [JSON-API spec regarding pagination](http://jsonapi.org/format/1.0/#fetching-pagination).

    ##Query Params

    + `page=<Int>` -- page number of results to view, default 1

    + `filter[<fieldname>]=<Str>` -- fields and values to filter the search results on.

    Nodes may be filtered by their `title`, `category`, `description`, `public`, `registration`, or `tags`.  `title`,
    `description`, and `category` are string fields and will be filtered using simple substring matching.  `public` and
    `registration` are booleans, and can be filtered using truthy values, such as `true`, `false`, `0`, or `1`.  Note
    that quoting `true` or `false` in the query will cause the match to fail regardless.  `tags` is an array of simple strings.

    #This Request/Response
    """

    serializer_class = RegistrationSerializer
    view_category = 'registrations'
    view_name = 'linked-registrations'


class RegistrationViewOnlyLinksList(NodeViewOnlyLinksList, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_view_only_links_list).
    """
    required_read_scopes = [CoreScopes.REGISTRATION_VIEW_ONLY_LINKS_READ]
    required_write_scopes = [CoreScopes.REGISTRATION_VIEW_ONLY_LINKS_WRITE]

    view_category = 'registrations'
    view_name = 'registration-view-only-links'


class RegistrationViewOnlyLinkDetail(NodeViewOnlyLinkDetail, RegistrationMixin):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_view_only_links_read).
    """
    required_read_scopes = [CoreScopes.REGISTRATION_VIEW_ONLY_LINKS_READ]
    required_write_scopes = [CoreScopes.REGISTRATION_VIEW_ONLY_LINKS_WRITE]

    view_category = 'registrations'
    view_name = 'registration-view-only-link-detail'


class RegistrationIdentifierList(RegistrationMixin, NodeIdentifierList):
    """The documentation for this endpoint can be found [here](https://developer.osf.io/#operation/registrations_identifiers_list).
    """

    serializer_class = RegistrationIdentifierSerializer


class RegistrationActionList(JSONAPIBaseView, ListFilterMixin, generics.ListCreateAPIView, ProviderMixin):
    provider_class = RegistrationProvider

    permission_classes = (
        drf_permissions.IsAuthenticated,
        base_permissions.TokenHasScope,
        ContributorOrModerator,
    )

    parser_classes = (JSONAPIMultipleRelationshipsParser, JSONAPIMultipleRelationshipsParserForRegularJSON)

    required_read_scopes = [CoreScopes.ACTIONS_READ]
    required_write_scopes = [CoreScopes.ACTIONS_WRITE]
    view_category = 'registrations'
    view_name = 'registration-actions-list'

    serializer_class = RegistrationActionSerializer
    ordering = ('-created',)
    node_lookup_url_kwarg = 'node_id'

    def get_registration(self):
        registration = get_object_or_error(
            Registration,
            self.kwargs[self.node_lookup_url_kwarg],
            self.request,
            check_deleted=False,
        )
        # May raise a permission denied
        self.check_object_permissions(self.request, registration)
        return registration

    def get_default_queryset(self):
        return self.get_registration().actions.all()

    def get_queryset(self):
        return self.get_queryset_from_request()

    def perform_create(self, serializer):
        target = serializer.validated_data['target']
        self.check_object_permissions(self.request, target)

        if not target.provider.is_reviewed:
            raise Conflict(f'{target.provider.name} is an umoderated provider. If you believe this is an error, contact OSF Support.')

        serializer.save(user=self.request.user)


class RegistrationRequestList(JSONAPIBaseView, ListFilterMixin, generics.ListCreateAPIView, RegistrationMixin, ProviderMixin):
    provider_class = RegistrationProvider

    required_read_scopes = [CoreScopes.NODE_REQUESTS_READ]
    required_write_scopes = [CoreScopes.NULL]

    permission_classes = (
        drf_permissions.IsAuthenticated,
        base_permissions.TokenHasScope,
        MustBeModerator,
    )

    view_category = 'registrations'
    view_name = 'registration-requests-list'

    serializer_class = RegistrationRequestSerializer

    def get_default_queryset(self):
        return self.get_node().requests.all()

    def get_queryset(self):
        return self.get_queryset_from_request()


class RegistrationSchemaResponseList(JSONAPIBaseView, generics.ListAPIView, ListFilterMixin, RegistrationMixin):
    required_read_scopes = [CoreScopes.READ_SCHEMA_RESPONSES]
    required_write_scopes = [CoreScopes.NULL]

    permission_classes = (
        RegistrationSchemaResponseListPermission,
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
        ExcludeWithdrawals,
    )

    view_category = 'registrations'
    view_name = 'schema-responses-list'

    serializer_class = RegistrationSchemaResponseSerializer

    def get_object(self):
        return self.get_node()

    def get_default_queryset(self):
        '''Return all SchemaResponses on the Registration that should be visible to the user.

        For contributors to the Registration, this should be all of its SchemaResponses.
        For moderators, this should be all PENDING_MODERATION or APPROVED SchemaResponses
        For all others, this should be only the APPROVED responses.
        '''
        user = self.request.user
        registration = self.get_node()

        # Get the SchemaResponses from the root
        all_responses = registration.root.schema_responses.annotate(
            is_pending_current_user_approval=(
                schema_response_annotations.is_pending_current_user_approval(user)
            ),
            is_original_response=schema_response_annotations.IS_ORIGINAL_RESPONSE,
        )

        is_contributor = registration.has_permission(user, 'read') if user else False
        if is_contributor:
            return all_responses

        is_moderator = (
            user and
            registration.is_moderated and
            user.has_perm('view_submissions', registration.provider)
        )
        if is_moderator:
            return all_responses.filter(
                reviews_state__in=[state.db_name for state in MODERATOR_VISIBLE_STATES],
            )
        return all_responses.filter(reviews_state=ApprovalStates.APPROVED.db_name)

    def get_queryset(self):
        return self.get_queryset_from_request()


class RegistrationResourceList(JSONAPIBaseView, generics.ListAPIView, ListFilterMixin, RegistrationMixin):
    permission_classes = (
        RegistrationResourceListPermission,
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
    )

    required_read_scopes = [CoreScopes.READ_REGISTRATION_RESOURCES]
    required_write_scopes = [CoreScopes.WRITE_REGISTRATION_RESOURCES]

    view_category = 'registrations'
    view_name = 'resource-list'

    serializer_class = ResourceSerializer

    parser_classes = (JSONAPIMultipleRelationshipsParser, JSONAPIMultipleRelationshipsParserForRegularJSON)

    def get_node(self):
        return super().get_node(check_object_permissions=False)

    def get_default_queryset(self):
        root_registration = self.get_node()
        return OutcomeArtifact.objects.for_registration(root_registration).filter(
            finalized=True,
            deleted__isnull=True,
        )

    def get_queryset(self):
        return self.get_queryset_from_request()

    def get_permissions_proxy(self):
        return self.get_node()


class RegistrationCedarMetadataRecordsList(JSONAPIBaseView, generics.ListAPIView, ListFilterMixin, RegistrationMixin):

    permission_classes = (
        drf_permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
        ContributorOrModeratorOrPublic,
    )
    required_read_scopes = [CoreScopes.CEDAR_METADATA_RECORD_READ]
    required_write_scopes = [CoreScopes.NULL]

    serializer_class = CedarMetadataRecordsListSerializer

    view_category = 'registrations'
    view_name = 'registration-cedar-metadata-records-list'

    def get_default_queryset(self):
        self.get_node()
        registration_records = CedarMetadataRecord.objects.filter(guid___id=self.kwargs['node_id'])
        user_auth = get_user_auth(self.request)
        record_ids = [record.id for record in registration_records if can_view_record(user_auth, record, guid_type=Registration)]
        return CedarMetadataRecord.objects.filter(pk__in=record_ids)

    def get_queryset(self):
        return self.get_queryset_from_request()


class RegistrationCallbackView(JSONAPIBaseView, generics.UpdateAPIView, RegistrationMixin):
    permission_classes = [drf_permissions.AllowAny]

    view_category = 'registrations'
    view_name = 'registration-callbacks'

    parser_classes = [HMACSignedParser]

    def update(self, request, *args, **kwargs):
        registration = self.get_node()

        try:
            payload = request.data
            if payload.get('action', None) in DOWNLOAD_ACTIONS:
                return Response({'status': 'success'}, status=status.HTTP_200_OK)
            errors = payload.get('errors')
            src_provider = payload['source']['provider']
            if errors:
                registration.archive_job.update_target(
                    src_provider,
                    ARCHIVER_FAILURE,
                    errors=errors,
                )
            else:
                # Dataverse requires two seperate targets, one
                # for draft files and one for published files
                if src_provider == 'dataverse':
                    src_provider += '-' + (payload['destination']['name'].split(' ')[-1].lstrip('(').rstrip(')').strip())
                registration.archive_job.update_target(
                    src_provider,
                    ARCHIVER_SUCCESS,
                )
            project_signals.archive_callback.send(registration)
            return Response(status=status.HTTP_200_OK)
        except HTTPError as e:
            registration.archive_status = ARCHIVER_NETWORK_ERROR
            registration.save()
            signals.archive_fail.send(
                registration,
                errors=[str(e)],
            )
            return Response(status=status.HTTP_200_OK)
