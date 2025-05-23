# Tests ported from tests/test_models.py and tests/test_user.py
import datetime
import os
import json
import datetime as dt
from urllib.parse import urlparse, urljoin, parse_qs

from django.db import connection, transaction
from django.contrib.auth.models import Group
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.conf import settings as django_conf_settings
from unittest import mock
import itsdangerous
import pytest
from importlib import import_module

from framework.auth.exceptions import ExpiredTokenError, InvalidTokenError, ChangePasswordError
from framework.auth.signals import user_account_merged
from framework.analytics import get_total_activity_count
from framework.exceptions import PermissionsError
from website import settings
from website import filters
from website.views import find_bookmark_collection

from codex.models import (
    AbstractNode,
    CODEXUser,
    CODEXGroup,
    Tag,
    Contributor,
    NotableDomain,
    PreprintContributor,
    DraftRegistrationContributor,
    DraftRegistration,
    DraftNode,
    UserSessionMap,
)
from codex.models.institution_affiliation import get_user_by_institution_identity
from addons.github.tests.factories import GitHubAccountFactory
from addons.codexstorage.models import Region
from addons.codexstorage.settings import DEFAULT_REGION_ID
from framework.auth.core import Auth
from codex.utils.names import impute_names_model
from codex.utils import permissions
from codex.exceptions import ValidationError, BlockedEmailError, UserStateError, InstitutionAffiliationStateError

from .utils import capture_signals
from .factories import (
    fake,
    fake_email,
    AuthUserFactory,
    CollectionFactory,
    DraftRegistrationFactory,
    ExternalAccountFactory,
    InstitutionFactory,
    NodeFactory,
    CODEXGroupFactory,
    PreprintProviderFactory,
    ProjectFactory,
    TagFactory,
    UnconfirmedUserFactory,
    UnregUserFactory,
    UserFactory,
    RegistrationFactory,
    PreprintFactory,
    DraftNodeFactory
)
from tests.base import CodexTestCase

SessionStore = import_module(django_conf_settings.SESSION_ENGINE).SessionStore

from codex.external.spam import tasks as spam_tasks


pytestmark = pytest.mark.django_db

def test_factory():
    user = UserFactory.build()
    user.save()

@pytest.fixture()
def user():
    return UserFactory()


@pytest.fixture()
def auth(user):
    return Auth(user)

# Tests copied from tests/test_models.py
@pytest.mark.enable_implicit_clean
class TestCODEXUser:

    def test_create(self):
        name, email = fake.name(), fake_email()
        user = CODEXUser.create(
            username=email, password='foobar', fullname=name
        )
        user.save()
        assert user.check_password('foobar') is True
        assert user._id
        assert user.given_name == impute_names_model(name)['given_name']

    def test_create_unconfirmed(self):
        name, email = fake.name(), fake_email()
        user = CODEXUser.create_unconfirmed(
            username=email, password='foobar', fullname=name
        )
        assert user.is_registered is False
        assert len(user.email_verifications.keys()) == 1
        assert user.emails.count() == 0, 'primary email has not been added to emails list'

    def test_create_unconfirmed_with_campaign(self):
        name, email = fake.name(), fake_email()
        user = CODEXUser.create_unconfirmed(
            username=email, password='foobar', fullname=name,
            campaign='institution'
        )
        assert 'institution_campaign' in user.system_tags

    def test_create_unconfirmed_from_external_service(self):
        name, email = fake.name(), fake_email()
        external_identity = {
            'ORCID': {
                fake.ean(): 'CREATE'
            }
        }
        user = CODEXUser.create_unconfirmed(
            username=email,
            password=str(fake.password()),
            fullname=name,
            external_identity=external_identity,
        )
        user.save()
        assert user.is_registered is False
        assert len(user.email_verifications.keys()) == 1
        assert user.email_verifications.popitem()[1]['external_identity'] == external_identity
        assert user.emails.count() == 0, 'primary email has not been added to emails list'

    def test_create_confirmed(self):
        name, email = fake.name(), fake_email()
        user = CODEXUser.create_confirmed(
            username=email, password='foobar', fullname=name
        )
        user.save()
        assert user.is_registered is True
        assert user.date_registered == user.date_confirmed

    def test_update_guessed_names(self):
        name = fake.name()
        u = CODEXUser(fullname=name)
        u.update_guessed_names()

        parsed = impute_names_model(name)
        assert u.fullname == name
        assert u.given_name == parsed['given_name']
        assert u.middle_names == parsed['middle_names']
        assert u.family_name == parsed['family_name']
        assert u.suffix == parsed['suffix']

    def test_create_unregistered(self):
        name, email = fake.name(), fake_email()
        u = CODEXUser.create_unregistered(email=email,
                                     fullname=name)
        # TODO: Remove post-migration
        u.date_registered = timezone.now()
        u.save()
        assert u.username == email
        assert u.is_registered is False
        assert u.is_invited is True
        assert not u.emails.filter(address=email).exists()
        parsed = impute_names_model(name)
        assert u.given_name == parsed['given_name']

    @mock.patch('codex.models.user.CODEXUser.update_search')
    def test_search_not_updated_for_unreg_users(self, update_search):
        u = CODEXUser.create_unregistered(fullname=fake.name(), email=fake_email())
        # TODO: Remove post-migration
        u.date_registered = timezone.now()
        u.save()
        assert not update_search.called

    @mock.patch('codex.models.CODEXUser.update_search')
    def test_search_updated_for_registered_users(self, update_search):
        UserFactory(is_registered=True)
        assert update_search.called

    def test_create_unregistered_raises_error_if_already_in_db(self):
        u = UnregUserFactory()
        dupe = CODEXUser.create_unregistered(fullname=fake.name(), email=u.username)
        with pytest.raises(ValidationError):
            dupe.save()

    def test_merged_user_is_not_active(self):
        master = UserFactory()
        dupe = UserFactory(merged_by=master)
        assert dupe.is_active is False

    def test_non_registered_user_is_not_active(self):
        u = CODEXUser(username=fake_email(),
                 fullname='Freddie Mercury',
                 is_registered=False)
        u.set_password('killerqueen')
        u.save()
        assert u.is_active is False

    def test_user_with_no_password_is_invalid(self):
        u = CODEXUser(
            username=fake_email(),
            fullname='Freddie Mercury',
            is_registered=True,
        )
        with pytest.raises(ValidationError):
            u.save()

    def test_merged_user_with_two_account_on_same_project_with_different_visibility_and_permissions(self, user):
        user2 = UserFactory.build()
        user2.save()

        project = ProjectFactory(is_public=True)
        # Both the master and dupe are contributors
        project.add_contributor(user2, log=False)
        project.add_contributor(user, log=False)
        project.set_permissions(user=user, permissions=permissions.READ)
        project.set_permissions(user=user2, permissions=permissions.ADMIN)
        project.set_visible(user=user, visible=False)
        project.set_visible(user=user2, visible=True)
        project.save()
        user.merge_user(user2)
        user.save()
        project.reload()

        assert project.has_permission(user, permissions.ADMIN) is True
        assert project.get_visible(user) is True
        assert project.is_contributor(user2) is False

    def test_merged_user_group_member_permissions_are_ignored(self, user):
        user2 = UserFactory.build()
        user2.save()
        group = CODEXGroupFactory(creator=user2)

        project = ProjectFactory(is_public=True)
        project.add_codex_group(group, permissions.ADMIN)
        assert project.has_permission(user2, permissions.ADMIN)
        # Both the master and dupe are contributors
        project.add_contributor(user2, log=False)
        project.add_contributor(user, log=False)
        project.set_permissions(user=user, permissions=permissions.READ)
        project.set_permissions(user=user2, permissions=permissions.WRITE)
        project.save()
        user.merge_user(user2)
        user.save()
        project.reload()

        assert project.has_permission(user, permissions.ADMIN) is True
        assert project.is_admin_contributor(user) is False
        assert project.is_contributor(user2) is False
        assert group.is_member(user) is True
        assert group.is_member(user2) is False

    def test_merge_projects(self):
        user = AuthUserFactory()
        user2 = AuthUserFactory()

        project_one = ProjectFactory(creator=user, title='project_one')

        project_two = ProjectFactory(title='project_two')
        project_two.add_contributor(user2)

        project_three = ProjectFactory(title='project_three', creator=user2)
        project_three.add_contributor(user, visible=False)

        project_four = ProjectFactory(title='project_four')
        project_four.add_contributor(user2, permissions=permissions.READ, visible=False)

        project_five = ProjectFactory(title='project_five')
        project_five.add_contributor(user2, permissions=permissions.READ, visible=False)
        project_five.add_contributor(user, permissions=permissions.WRITE, visible=True)

        # two projects shared b/t user and user2
        assert user.nodes.filter(type='codex.node').count() == 3
        assert user2.nodes.filter(type='codex.node').count() == 4

        user.merge_user(user2)
        project_one.reload()
        project_two.reload()
        project_three.reload()
        project_four.reload()
        project_five.reload()

        assert user.nodes.filter(type='codex.node').count() == 5
        # one group for each node
        assert user.groups.count() == 5
        assert user2.nodes.filter(type='codex.node').count() == 0

        contrib_obj = Contributor.objects.get(user=user, node=project_one)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.ADMIN
        assert project_one.creator == user
        assert not project_one.has_permission(user2, permissions.READ)
        assert not project_one.is_contributor(user2)

        contrib_obj = Contributor.objects.get(user=user, node=project_two)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.WRITE
        assert project_two.creator != user
        assert not project_two.has_permission(user2, permissions.READ)
        assert not project_two.is_contributor(user2)

        contrib_obj = Contributor.objects.get(user=user, node=project_three)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.ADMIN  # of the two users the highest perm wins out.
        assert project_three.creator == user
        assert not project_three.has_permission(user2, permissions.READ)
        assert not project_three.is_contributor(user2)

        contrib_obj = Contributor.objects.get(user=user, node=project_four)
        assert contrib_obj.visible is False
        assert contrib_obj.permission == permissions.READ
        assert project_four.creator != user
        assert not project_four.has_permission(user2, permissions.READ)
        assert not project_four.is_contributor(user2)

        contrib_obj = Contributor.objects.get(user=user, node=project_five)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.WRITE
        assert project_five.creator != user
        assert not project_five.has_permission(user2, permissions.READ)
        assert not project_five.is_contributor(user2)

    def test_merge_preprints(self, user):
        user2 = AuthUserFactory()

        preprint_one = PreprintFactory(creator=user, title='preprint_one')

        preprint_two = PreprintFactory(title='preprint_two')
        preprint_two.add_contributor(user2)

        preprint_three = PreprintFactory(title='preprint_three', creator=user2)
        preprint_three.add_contributor(user, visible=False)

        preprint_four = PreprintFactory(title='preprint_four')
        preprint_four.add_contributor(user2, permissions=permissions.READ, visible=False)

        preprint_five = PreprintFactory(title='preprint_five')
        preprint_five.add_contributor(user2, permissions=permissions.READ, visible=False)
        preprint_five.add_contributor(user, permissions=permissions.WRITE, visible=True)

        # two preprints shared b/t user and user2
        assert user.preprints.count() == 3
        assert user2.preprints.count() == 4

        user.merge_user(user2)
        preprint_one.reload()
        preprint_two.reload()
        preprint_three.reload()
        preprint_four.reload()
        preprint_five.reload()

        assert user.preprints.count() == 5
        # one group for each preprint
        assert user.groups.filter(name__icontains='preprint').count() == 5
        assert user2.preprints.count() == 0
        assert not user2.groups.filter(name__icontains='preprint').all()

        contrib_obj = PreprintContributor.objects.get(user=user, preprint=preprint_one)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.ADMIN
        assert preprint_one.creator == user
        assert not preprint_one.has_permission(user2, permissions.READ)
        assert not preprint_one.is_contributor(user2)

        contrib_obj = PreprintContributor.objects.get(user=user, preprint=preprint_two)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.WRITE
        assert preprint_two.creator != user
        assert not preprint_two.has_permission(user2, permissions.READ)
        assert not preprint_two.is_contributor(user2)

        contrib_obj = PreprintContributor.objects.get(user=user, preprint=preprint_three)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.ADMIN  # of the two users the highest perm wins out.
        assert preprint_three.creator == user
        assert not preprint_three.has_permission(user2, permissions.READ)
        assert not preprint_three.is_contributor(user2)

        contrib_obj = PreprintContributor.objects.get(user=user, preprint=preprint_four)
        assert contrib_obj.visible is False
        assert contrib_obj.permission == permissions.READ
        assert preprint_four.creator != user
        assert not preprint_four.has_permission(user2, permissions.READ)
        assert not preprint_four.is_contributor(user2)

        contrib_obj = PreprintContributor.objects.get(user=user, preprint=preprint_five)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.WRITE
        assert preprint_five.creator != user
        assert not preprint_five.has_permission(user2, permissions.READ)
        assert not preprint_five.is_contributor(user2)

    def test_merge_drafts(self, user):
        user2 = AuthUserFactory()

        draft_one = DraftRegistrationFactory(creator=user, title='draft_one')

        draft_two = DraftRegistrationFactory(title='draft_two')
        draft_two.add_contributor(user2)

        draft_three = DraftRegistrationFactory(title='draft_three', creator=user2)
        draft_three.add_contributor(user, visible=False)

        draft_four = DraftRegistrationFactory(title='draft_four')
        draft_four.add_contributor(user2, permissions=permissions.READ, visible=False)

        draft_five = DraftRegistrationFactory(title='draft_five')
        draft_five.add_contributor(user2, permissions=permissions.READ, visible=False)
        draft_five.add_contributor(user, permissions=permissions.WRITE, visible=True)

        # two drafts shared b/t user and user2
        assert user.draft_registrations.count() == 3
        assert user2.draft_registrations.count() == 4

        user.merge_user(user2)
        draft_one.reload()
        draft_two.reload()
        draft_three.reload()
        draft_four.reload()
        draft_five.reload()

        assert user.draft_registrations.count() == 5
        # one group for each draft
        assert user.groups.filter(name__icontains='draft').count() == 5
        assert user2.draft_registrations.count() == 0
        assert not user2.groups.filter(name__icontains='draft').all()

        contrib_obj = DraftRegistrationContributor.objects.get(user=user, draft_registration=draft_one)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.ADMIN
        assert draft_one.creator == user
        assert not draft_one.has_permission(user2, permissions.READ)
        assert not draft_one.is_contributor(user2)

        contrib_obj = DraftRegistrationContributor.objects.get(user=user, draft_registration=draft_two)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.WRITE
        assert draft_two.creator != user
        assert not draft_two.has_permission(user2, permissions.READ)
        assert not draft_two.is_contributor(user2)

        contrib_obj = DraftRegistrationContributor.objects.get(user=user, draft_registration=draft_three)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.ADMIN  # of the two users the highest perm wins out.
        assert draft_three.creator == user
        assert not draft_three.has_permission(user2, permissions.READ)
        assert not draft_three.is_contributor(user2)

        contrib_obj = DraftRegistrationContributor.objects.get(user=user, draft_registration=draft_four)
        assert contrib_obj.visible is False
        assert contrib_obj.permission == permissions.READ
        assert draft_four.creator != user
        assert not draft_four.has_permission(user2, permissions.READ)
        assert not draft_four.is_contributor(user2)

        contrib_obj = DraftRegistrationContributor.objects.get(user=user, draft_registration=draft_five)
        assert contrib_obj.visible is True
        assert contrib_obj.permission == permissions.WRITE
        assert draft_five.creator != user
        assert not draft_five.has_permission(user2, permissions.READ)
        assert not draft_five.is_contributor(user2)

    def test_cant_create_user_without_username(self):
        u = CODEXUser()  # No username given
        with pytest.raises(ValidationError):
            u.save()

    def test_date_registered_upon_saving(self):
        u = CODEXUser(username=fake_email(), fullname='Foo bar')
        u.set_unusable_password()
        u.save()
        assert bool(u.date_registered) is True
        assert u.date_registered.tzinfo == datetime.UTC

    def test_cant_create_user_without_full_name(self):
        u = CODEXUser(username=fake_email())
        with pytest.raises(ValidationError):
            u.save()

    def test_add_blocked_domain_unconfirmed_email(self, user):
        NotableDomain.objects.get_or_create(
            domain='mailinator.com',
            note=NotableDomain.Note.EXCLUDE_FROM_ACCOUNT_CREATION_AND_CONTENT,
        )
        with pytest.raises(BlockedEmailError) as e:
            user.add_unconfirmed_email('kanye@mailinator.com')
        assert str(e.value) == 'Invalid Email'

    @mock.patch('website.security.random_string')
    def test_get_confirmation_url_for_external_service(self, random_string):
        random_string.return_value = 'abcde'
        u = UnconfirmedUserFactory()
        assert (u.get_confirmation_url(u.username, external_id_provider='service', destination='dashboard') ==
               f'{settings.DOMAIN}confirm/external/{u._id}/abcde/?destination=dashboard')

    @mock.patch('website.security.random_string')
    def test_get_confirmation_token(self, random_string):
        random_string.return_value = '12345'
        u = UserFactory.build()
        u.add_unconfirmed_email('foo@bar.com')
        u.save()
        assert u.get_confirmation_token('foo@bar.com') == '12345'
        assert u.get_confirmation_token('fOo@bar.com') == '12345'

    def test_get_confirmation_token_when_token_is_expired_raises_error(self):
        u = UserFactory()
        # Make sure token is already expired
        expiration = timezone.now() - dt.timedelta(seconds=1)
        u.add_unconfirmed_email('foo@bar.com', expiration=expiration)

        with pytest.raises(ExpiredTokenError):
            u.get_confirmation_token('foo@bar.com')

    @mock.patch('website.security.random_string')
    def test_get_confirmation_token_when_token_is_expired_force(self, random_string):
        random_string.return_value = '12345'
        u = UserFactory()
        # Make sure token is already expired
        expiration = timezone.now() - dt.timedelta(seconds=1)
        u.add_unconfirmed_email('foo@bar.com', expiration=expiration)

        # sanity check
        with pytest.raises(ExpiredTokenError):
            u.get_confirmation_token('foo@bar.com')

        random_string.return_value = '54321'

        token = u.get_confirmation_token('foo@bar.com', force=True)
        assert token == '54321'

    # Some old users will not have an 'expired' key in their email_verifications.
    # Assume the token in expired
    def test_get_confirmation_token_if_email_verification_doesnt_have_expiration(self):
        u = UserFactory()

        email = fake_email()
        u.add_unconfirmed_email(email)
        # manually remove 'expiration' key
        token = u.get_confirmation_token(email)
        del u.email_verifications[token]['expiration']
        u.save()

        with pytest.raises(ExpiredTokenError):
            u.get_confirmation_token(email)

    @mock.patch('website.security.random_string')
    def test_get_confirmation_url(self, random_string):
        random_string.return_value = 'abcde'
        u = UserFactory()
        u.add_unconfirmed_email('foo@bar.com')
        assert (
            u.get_confirmation_url('foo@bar.com') ==
            f'{settings.DOMAIN}confirm/{u._id}/abcde/'
        )

    def test_get_confirmation_url_when_token_is_expired_raises_error(self):
        u = UserFactory()
        # Make sure token is already expired
        expiration = timezone.now() - dt.timedelta(seconds=1)
        u.add_unconfirmed_email('foo@bar.com', expiration=expiration)

        with pytest.raises(ExpiredTokenError):
            u.get_confirmation_url('foo@bar.com')

    @mock.patch('website.security.random_string')
    def test_get_confirmation_url_when_token_is_expired_force(self, random_string):
        random_string.return_value = '12345'
        u = UserFactory()
        # Make sure token is already expired
        expiration = timezone.now() - dt.timedelta(seconds=1)
        u.add_unconfirmed_email('foo@bar.com', expiration=expiration)

        # sanity check
        with pytest.raises(ExpiredTokenError):
            u.get_confirmation_token('foo@bar.com')

        random_string.return_value = '54321'

        url = u.get_confirmation_url('foo@bar.com', force=True)
        expected = f'{settings.DOMAIN}confirm/{u._id}/54321/'
        assert url == expected

    def test_confirm_primary_email(self):
        u = UnconfirmedUserFactory()
        token = u.get_confirmation_token(u.username)
        confirmed = u.confirm_email(token)
        u.save()
        assert bool(confirmed) is True
        assert len(u.email_verifications.keys()) == 0
        assert u.emails.filter(address=u.username).exists()
        assert bool(u.is_registered) is True

    def test_confirm_email(self, user):
        token = user.add_unconfirmed_email('foo@bar.com')
        user.confirm_email(token)

        assert 'foo@bar.com' not in user.unconfirmed_emails
        assert user.emails.filter(address='foo@bar.com').exists()

    def test_confirm_email_merge_select_for_update(self, user):
        mergee = UserFactory(username='foo@bar.com')
        token = user.add_unconfirmed_email('foo@bar.com')

        with transaction.atomic(), CaptureQueriesContext(connection) as ctx:
            user.confirm_email(token, merge=True)

        mergee.reload()
        assert mergee.is_merged
        assert mergee.merged_by == user

        for_update_sql = connection.ops.for_update_sql()
        assert any(for_update_sql in query['sql'] for query in ctx.captured_queries)

    @mock.patch('codex.utils.requests.settings.SELECT_FOR_UPDATE_ENABLED', False)
    def test_confirm_email_merge_select_for_update_disabled(self, user):
        mergee = UserFactory(username='foo@bar.com')
        token = user.add_unconfirmed_email('foo@bar.com')

        with transaction.atomic(), CaptureQueriesContext(connection) as ctx:
            user.confirm_email(token, merge=True)

        mergee.reload()
        assert mergee.is_merged
        assert mergee.merged_by == user

        for_update_sql = connection.ops.for_update_sql()
        assert not any(for_update_sql in query['sql'] for query in ctx.captured_queries)

    def test_confirm_email_comparison_is_case_insensitive(self):
        u = UnconfirmedUserFactory.build(
            username='letsgettacos@lgt.com'
        )
        u.add_unconfirmed_email('LetsGetTacos@LGT.com')
        u.save()
        assert bool(u.is_confirmed) is False  # sanity check

        token = u.get_confirmation_token('LetsGetTacos@LGT.com')

        confirmed = u.confirm_email(token)
        assert confirmed is True
        assert u.is_confirmed is True

    def test_verify_confirmation_token(self):
        u = UserFactory.build()
        u.add_unconfirmed_email('foo@bar.com')
        u.save()

        with pytest.raises(InvalidTokenError):
            u.get_unconfirmed_email_for_token('badtoken')

        valid_token = u.get_confirmation_token('foo@bar.com')
        assert bool(u.get_unconfirmed_email_for_token(valid_token)) is True
        manual_expiration = timezone.now() - dt.timedelta(0, 10)
        u.email_verifications[valid_token]['expiration'] = manual_expiration

        with pytest.raises(ExpiredTokenError):
            u.get_unconfirmed_email_for_token(valid_token)

    def test_verify_confirmation_token_when_token_has_no_expiration(self):
        # A user verification token may not have an expiration
        email = fake_email()
        u = UserFactory.build()
        u.add_unconfirmed_email(email)
        token = u.get_confirmation_token(email)
        # manually remove expiration to simulate legacy user
        del u.email_verifications[token]['expiration']
        u.save()

        assert bool(u.get_unconfirmed_email_for_token(token)) is True

    def test_format_surname(self):
        user = UserFactory(fullname='Duane Johnson')
        summary = user.get_summary(formatter='surname')
        assert summary['user_display_name'] == 'Johnson'

    def test_format_surname_one_name(self):
        user = UserFactory(fullname='Rock')
        summary = user.get_summary(formatter='surname')
        assert summary['user_display_name'] == 'Rock'

    def test_url(self, user):
        assert user.url == f'/{user._id}/'

    def test_absolute_url(self, user):
        assert (
            user.absolute_url ==
            urljoin(settings.DOMAIN, f'/{user._id}/')
        )

    def test_profile_image_url(self, user):
        expected = filters.profile_image_url(settings.PROFILE_IMAGE_PROVIDER,
                                         user,
                                         use_ssl=True,
                                         size=settings.PROFILE_IMAGE_MEDIUM)
        assert user.profile_image_url(settings.PROFILE_IMAGE_MEDIUM) == expected

    def test_set_unusable_username_for_unsaved_user(self):
        user = UserFactory.build()
        user.set_unusable_username()
        assert user.username is not None
        user.save()
        assert user.has_usable_username() is False

    def test_set_unusable_username_for_saved_user(self):
        user = UserFactory()
        user.set_unusable_username()
        assert user.username == user._id

    def test_has_usable_username(self):
        user = UserFactory()
        assert user.has_usable_username() is True
        user.username = user._id
        assert user.has_usable_username() is False

    def test_profile_image_url_has_no_default_size(self, user):
        expected = filters.profile_image_url(settings.PROFILE_IMAGE_PROVIDER,
                                         user,
                                         use_ssl=True)
        assert user.profile_image_url() == expected
        size = parse_qs(urlparse(user.profile_image_url()).query).get('size')
        assert size is None

    def test_activity_points(self, user):
        assert user.get_activity_points() == get_total_activity_count(user._primary_key)

    def test_contributed_property(self):
        user = UserFactory()
        node = NodeFactory()
        node2 = NodeFactory()
        # TODO: Use Node.add_contributor when it's implemented
        Contributor.objects.create(user=user, node=node)
        projects_contributed_to = AbstractNode.objects.filter(_contributors=user)
        assert list(user.contributed) == list(projects_contributed_to)
        assert node2 not in user.contributed

    # copied from tests/test_views.py
    def test_clean_email_verifications(self, user):
        # Do not return bad token and removes it from user.email_verifications
        email = 'test@example.com'
        token = 'blahblahblah'
        user.email_verifications[token] = {'expiration': (timezone.now() + dt.timedelta(days=1)),
                                                'email': email,
                                                'confirmed': False}
        user.save()
        assert user.email_verifications[token]['email'] == email
        user.clean_email_verifications(given_token=token)
        unconfirmed_emails = user.unconfirmed_email_info
        assert unconfirmed_emails == []
        assert user.email_verifications == {}

    def test_display_full_name_registered(self):
        u = UserFactory()
        assert u.display_full_name() == u.fullname

    def test_display_full_name_unregistered(self):
        name = fake.name()
        u = UnregUserFactory()
        project = NodeFactory()
        project.add_unregistered_contributor(
            fullname=name, email=u.username,
            auth=Auth(project.creator)
        )
        project.save()
        u.reload()
        assert u.display_full_name(node=project) == name

    def test_repeat_add_same_unreg_user_with_diff_name(self):
        unreg_user = UnregUserFactory()
        project = NodeFactory()
        old_name = unreg_user.fullname
        project.add_unregistered_contributor(
            fullname=old_name, email=unreg_user.username,
            auth=Auth(project.creator)
        )
        project.save()
        unreg_user.reload()
        name_list = [contrib.fullname for contrib in project.contributors]
        assert unreg_user.fullname in name_list
        project.remove_contributor(contributor=unreg_user, auth=Auth(project.creator))
        project.save()
        project.reload()
        assert unreg_user not in project.contributors
        new_name = fake.name()
        project.add_unregistered_contributor(
            fullname=new_name, email=unreg_user.username,
            auth=Auth(project.creator)
        )
        project.save()
        unreg_user.reload()
        project.reload()
        unregistered_name = unreg_user.unclaimed_records[project._id].get('name', None)
        assert new_name == unregistered_name

    def test_username_is_automatically_lowercased(self):
        user = UserFactory(username='nEoNiCon@bet.com')
        assert user.username == 'neonicon@bet.com'

    def test_update_affiliated_institutions_by_email_domains(self):
        institution = InstitutionFactory()
        email_domain = institution.email_domains[0]

        user_email = f'{fake.domain_word()}@{email_domain}'
        user = UserFactory(username=user_email)
        user.update_affiliated_institutions_by_email_domain()

        assert user.get_affiliated_institutions().count() == 1
        assert user.is_affiliated_with_institution(institution) is True

        user.update_affiliated_institutions_by_email_domain()

        assert user.get_affiliated_institutions().count() == 1

    def test_is_affiliated_with_institution(self, user):
        institution1, institution2 = InstitutionFactory(), InstitutionFactory()

        user.add_or_update_affiliated_institution(institution1)
        user.save()

        assert user.is_affiliated_with_institution(institution1) is True
        assert user.is_affiliated_with_institution(institution2) is False

    def test_has_codexstorage_usersettings(self, user):
        addon = user.get_addon('codexstorage')
        default_region = Region.objects.get(_id=DEFAULT_REGION_ID)

        assert addon
        assert addon.default_region == default_region

class TestProjectsInCommon:

    def test_get_projects_in_common(self, user, auth):
        user2 = UserFactory()
        project = NodeFactory(creator=user)
        project.add_contributor(contributor=user2, auth=auth)
        project.save()

        group = CODEXGroupFactory(creator=user, name='Platform')
        group.make_member(user2)
        group_project = ProjectFactory()
        group_project.add_codex_group(group)
        group_project.save()

        project_keys = {node._id for node in user.all_nodes}
        projects = set(user.all_nodes)
        user2_project_keys = {node._id for node in user2.all_nodes}

        assert {n._id for n in user.get_projects_in_common(user2)} == project_keys.intersection(user2_project_keys)
        assert user.get_projects_in_common(user2) == projects.intersection(user2.all_nodes)

    def test_n_projects_in_common(self, user, auth):
        user2 = UserFactory()
        user3 = UserFactory()
        project = NodeFactory(creator=user)

        project.add_contributor(contributor=user2, auth=auth)
        project.save()

        group = CODEXGroupFactory(name='Platform', creator=user)
        group.make_member(user3)
        project.add_codex_group(group)
        project.save()

        assert user.n_projects_in_common(user2) == 1
        assert user.n_projects_in_common(user3) == 1


class TestCookieMethods:

    def test_user_get_cookie(self):
        user = UserFactory()
        super_secret_key = 'children need maps'
        signer = itsdangerous.Signer(super_secret_key)
        session = SessionStore()
        session['auth_user_id'] = user._id
        session['auth_user_username'] = user.username
        session['auth_user_fullname'] = user.fullname
        session.create()
        UserSessionMap.objects.create(user=user, session_key=session.session_key)

        assert signer.unsign(user.get_or_create_cookie(super_secret_key)).decode() == session.session_key

    def test_user_get_cookie_no_session(self):
        user = UserFactory()
        super_secret_key = 'children need maps'
        signer = itsdangerous.Signer(super_secret_key)
        assert UserSessionMap.objects.filter(user=user).count() == 0

        cookie = user.get_or_create_cookie(super_secret_key)

        session_map = UserSessionMap.objects.filter(user=user).first()
        session = SessionStore(session_key=session_map.session_key)

        assert session.session_key == signer.unsign(cookie).decode()
        assert session['auth_user_id'] == user._id
        assert session['auth_user_username'] == user.username
        assert session['auth_user_fullname'] == user.fullname

    def test_get_user_by_cookie(self):
        user = UserFactory()
        cookie = user.get_or_create_cookie()
        assert user == CODEXUser.from_cookie(cookie)

    def test_get_user_by_cookie_returns_none(self):
        assert CODEXUser.from_cookie('') is None

    def test_get_user_by_cookie_bad_cookie(self):
        assert CODEXUser.from_cookie('foobar') is None

    def test_get_user_by_cookie_no_user_id(self):
        user = UserFactory()
        cookie = user.get_or_create_cookie()
        session_map = UserSessionMap.objects.filter(user=user).first()
        session = SessionStore(session_key=session_map.session_key)
        del session['auth_user_id']
        session.save()
        assert CODEXUser.from_cookie(cookie) is None

    def test_get_user_by_cookie_no_session(self):
        user = UserFactory()
        cookie = user.get_or_create_cookie()
        session_map = UserSessionMap.objects.filter(user=user).first()
        session = SessionStore(session_key=session_map.session_key)
        session.flush()
        assert CODEXUser.from_cookie(cookie) is None


class TestChangePassword:

    def test_change_password(self, user):
        old_password = 'password'
        new_password = 'new password'
        confirm_password = new_password
        user.set_password(old_password)
        user.save()
        user.change_password(old_password, new_password, confirm_password)
        assert bool(user.check_password(new_password)) is True

    @mock.patch('website.mails.send_mail')
    def test_set_password_notify_default(self, mock_send_mail, user):
        old_password = 'password'
        user.set_password(old_password)
        user.save()
        assert mock_send_mail.called is True

    @mock.patch('website.mails.send_mail')
    def test_set_password_no_notify(self, mock_send_mail, user):
        old_password = 'password'
        user.set_password(old_password, notify=False)
        user.save()
        assert mock_send_mail.called is False

    @mock.patch('website.mails.send_mail')
    def test_check_password_upgrade_hasher_no_notify(self, mock_send_mail, user, settings):
        # NOTE: settings fixture comes from pytest-django.
        # changes get reverted after tests run
        settings.PASSWORD_HASHERS = (
            'django.contrib.auth.hashers.MD5PasswordHasher',
            'django.contrib.auth.hashers.SHA1PasswordHasher',
        )
        raw_password = 'password'
        user.password = 'sha1$lNb72DKWDv6P$e6ae16dada9303ae0084e14fc96659da4332bb05'
        user.check_password(raw_password)
        assert user.password.startswith('md5$')
        assert mock_send_mail.called is False

    def test_change_password_invalid(self, old_password=None, new_password=None, confirm_password=None,
                                     error_message='Old password is invalid'):
        user = UserFactory()
        user.set_password('password')
        user.save()
        with pytest.raises(ChangePasswordError, match=error_message):
            user.change_password(old_password, new_password, confirm_password)
            user.save()

        assert bool(user.check_password(new_password)) is False

    def test_change_password_invalid_old_password(self):
        self.test_change_password_invalid(
            'invalid old password',
            'new password',
            'new password',
            'Old password is invalid',
        )

    def test_change_password_invalid_too_short(self):
        self.test_change_password_invalid(
            'password',
            '12345',
            '12345',
            'Password should be at least eight characters',
        )

    def test_change_password_invalid_too_long(self):
        too_long = 'X' * 257
        self.test_change_password_invalid(
            'password',
            too_long,
            too_long,
            'Password should not be longer than 256 characters',
        )

    def test_change_password_invalid_confirm_password(self):
        self.test_change_password_invalid(
            'password',
            'new password',
            'invalid confirm password',
            'Password does not match the confirmation',
        )

    def test_change_password_invalid_blank_password(self, old_password='', new_password='', confirm_password=''):
        self.test_change_password_invalid(
            old_password,
            new_password,
            confirm_password,
            'Passwords cannot be blank',
        )

    def test_change_password_invalid_blank_new_password(self):
        for password in (None, '', '      '):
            self.test_change_password_invalid_blank_password('password', password, 'new password')

    def test_change_password_invalid_blank_confirm_password(self):
        for password in (None, '', '      '):
            self.test_change_password_invalid_blank_password('password', 'new password', password)


class TestIsActive:

    @pytest.fixture()
    def make_user(self):
        def func(**attrs):
            # By default, return an active user
            user = UserFactory.build(
                is_registered=True,
                merged_by=None,
                is_disabled=False,
                date_confirmed=timezone.now(),
            )
            user.set_password('secret')
            for attr, value in attrs.items():
                setattr(user, attr, value)
            return user
        return func

    def test_is_active_is_set_to_true_under_correct_conditions(self, make_user):
        user = make_user()
        user.save()
        assert user.is_active is True

    def test_is_active_is_false_if_not_registered(self, make_user):
        user = make_user(is_registered=False)
        user.save()
        assert user.is_active is False

    def test_user_with_unusable_password_but_verified_orcid_is_active(self, make_user):
        user = make_user()
        user.set_unusable_password()
        user.save()
        assert user.is_active is False
        user.external_identity = {'ORCID': {'fake-orcid': 'VERIFIED'}}
        user.save()
        assert user.is_active is True

    def test_is_active_is_false_if_not_confirmed(self, make_user):
        user = make_user(date_confirmed=None)
        user.save()
        assert user.is_active is False

    def test_is_active_is_false_if_password_unset(self, make_user):
        user = make_user()
        user.set_unusable_password()
        user.save()
        assert user.is_active is False

    def test_is_active_is_false_if_merged(self, make_user):
        merger = UserFactory()
        user = make_user(merged_by=merger)
        user.save()
        assert user.is_active is False

    def test_is_active_is_false_if_disabled(self, make_user):
        user = make_user(date_disabled=timezone.now())
        user.save()
        assert user.is_active is False


class TestAddUnconfirmedEmail:

    @mock.patch('website.security.random_string')
    def test_add_unconfirmed_email(self, random_string):
        token = fake.lexify('???????')
        random_string.return_value = token
        u = UserFactory()
        assert len(u.email_verifications.keys()) == 0
        u.add_unconfirmed_email('foo@bar.com')
        assert len(u.email_verifications.keys()) == 1
        assert u.email_verifications[token]['email'] == 'foo@bar.com'

    @mock.patch('website.security.random_string')
    def test_add_unconfirmed_email_adds_expiration_date(self, random_string):
        token = fake.lexify('???????')
        random_string.return_value = token
        u = UserFactory()
        u.add_unconfirmed_email('test@codex.io')
        assert isinstance(u.email_verifications[token]['expiration'], dt.datetime)

    def test_add_blank_unconfirmed_email(self):
        user = UserFactory()
        with pytest.raises(ValidationError) as exc_info:
            user.add_unconfirmed_email('')
        assert exc_info.value.message == 'Enter a valid email address.'

# Copied from tests/test_models.TestUnregisteredUser

class TestUnregisteredUser:

    @pytest.fixture()
    def referrer(self):
        return UserFactory()

    @pytest.fixture()
    def email(self):
        return fake_email()

    @pytest.fixture()
    def unreg_user(self, referrer, project, email):
        user = UnregUserFactory()
        given_name = 'Fredd Merkury'
        user.add_unclaimed_record(project,
            given_name=given_name, referrer=referrer,
            email=email)
        user.save()
        return user

    @pytest.fixture()
    def provider(self, referrer):
        provider = PreprintProviderFactory()
        provider.add_to_group(referrer, 'moderator')
        provider.save()
        return provider

    @pytest.fixture()
    def unreg_moderator(self, referrer, provider, email):
        user = UnregUserFactory()
        given_name = 'Freddie Merkkury'
        user.add_unclaimed_record(provider,
            given_name=given_name, referrer=referrer,
            email=email)
        user.save()
        return user

    @pytest.fixture()
    def project(self, referrer):
        return NodeFactory(creator=referrer)

    def test_unregistered_factory(self):
        u1 = UnregUserFactory()
        assert bool(u1.is_registered) is False
        assert u1.has_usable_password() is False
        assert bool(u1.fullname) is True

    def test_unconfirmed_factory(self):
        u = UnconfirmedUserFactory()
        assert bool(u.is_registered) is False
        assert bool(u.username) is True
        assert bool(u.fullname) is True
        assert bool(u.password) is True
        assert len(u.email_verifications.keys()) == 1

    def test_add_unclaimed_record(self, unreg_user, unreg_moderator, email, referrer, provider, project):
        # test_unreg_contrib
        data = unreg_user.unclaimed_records[project._primary_key]
        assert data['name'] == 'Fredd Merkury'
        assert data['referrer_id'] == referrer._id
        assert 'token' in data
        assert data['email'] == email
        assert data == unreg_user.get_unclaimed_record(project._primary_key)
        assert f'source:unregistered_created|{referrer._id}' in unreg_user.system_tags

        # test_unreg_moderator
        data = unreg_moderator.unclaimed_records[provider._id]
        assert data['name'] == 'Freddie Merkkury'
        assert data['referrer_id'] == referrer._id
        assert 'token' in data
        assert data['email'] == email
        assert data == unreg_moderator.get_unclaimed_record(provider._id)
        assert f'source:unregistered_created|{referrer._id}' in unreg_user.system_tags

    def test_get_claim_url(self, unreg_user, unreg_moderator, project, provider):
        # test_unreg_contrib
        uid = unreg_user._primary_key
        pid = project._primary_key
        token = unreg_user.get_unclaimed_record(pid)['token']
        domain = settings.DOMAIN
        assert (
            unreg_user.get_claim_url(pid, external=True) ==
            f'{domain}user/{uid}/{pid}/claim/?token={token}'
        )

        # test_unreg_moderator
        uid = unreg_moderator._id
        pid = provider._id
        token = unreg_moderator.get_unclaimed_record(pid)['token']
        domain = settings.DOMAIN
        assert (
            unreg_moderator.get_claim_url(pid, external=True) ==
            f'{domain}user/{uid}/{pid}/claim/?token={token}'
        )

    def test_get_claim_url_raises_value_error_if_not_valid_pid(self, unreg_user, unreg_moderator):
        with pytest.raises(ValueError):
            unreg_user.get_claim_url('invalidinput')
            unreg_moderator.get_claim_url('invalidinput')

    def test_cant_add_unclaimed_record_if_referrer_has_no_permissions(self, referrer, unreg_moderator, unreg_user, provider):
        # test_referrer_is_not_contrib
        project = NodeFactory()
        with pytest.raises(PermissionsError) as e:
            unreg_user.add_unclaimed_record(project,
                given_name='fred m', referrer=referrer)
            unreg_user.save()
        assert str(e.value) == f'Referrer does not have permission to add a contributor to {project._primary_key}'

        # test_referrer_is_not_admin_or_moderator
        referrer = UserFactory()
        with pytest.raises(PermissionsError) as e:
            unreg_moderator.add_unclaimed_record(provider,
                given_name='hodor', referrer=referrer)
            unreg_user.save()
        assert str(e.value) == f'Referrer does not have permission to add a moderator to provider {provider._id}'

    @mock.patch('codex.models.CODEXUser.update_search_nodes')
    @mock.patch('codex.models.CODEXUser.update_search')
    def test_register(self, mock_search, mock_search_nodes):
        user = UnregUserFactory()
        assert user.is_registered is False  # sanity check
        email = fake_email()
        user.register(username=email, password='killerqueen')
        user.save()
        assert user.is_registered is True
        assert user.check_password('killerqueen') is True
        assert user.username == email

    @mock.patch('codex.models.CODEXUser.update_search_nodes')
    @mock.patch('codex.models.CODEXUser.update_search')
    def test_registering_with_a_different_email_adds_to_emails_list(self, mock_search, mock_search_nodes):
        user = UnregUserFactory()
        assert user.has_usable_password() is False  # sanity check
        email = fake_email()
        user.register(username=email, password='killerqueen')
        assert user.emails.filter(address=email).exists()

    def test_verify_claim_token(self, unreg_user, unreg_moderator, project, provider):
        # test_unreg_contrib
        valid = unreg_user.get_unclaimed_record(project._primary_key)['token']
        assert bool(unreg_user.verify_claim_token(valid, project_id=project._primary_key)) is True
        assert bool(unreg_user.verify_claim_token('invalidtoken', project_id=project._primary_key)) is False

        # test_unreg_moderator
        valid = unreg_moderator.get_unclaimed_record(provider._id)['token']
        assert bool(unreg_moderator.verify_claim_token(valid, project_id=provider._id)) is True
        assert bool(unreg_moderator.verify_claim_token('invalidtoken', project_id=provider._id)) is False

    def test_verify_claim_token_with_no_expiration_date(self, unreg_user, project):
        # Legacy records may not have an 'expires' key
        #self.add_unclaimed_record()
        record = unreg_user.get_unclaimed_record(project._primary_key)
        del record['expires']
        unreg_user.save()
        token = record['token']
        assert unreg_user.verify_claim_token(token, project_id=project._primary_key) is True


# Copied from tests/test_models.py
class TestRecentlyAdded:

    def test_recently_added(self, user, auth):
        # Project created
        project = NodeFactory()

        assert hasattr(user, 'recently_added') is True

        # Two users added as contributors
        user2 = UserFactory()
        user3 = UserFactory()
        project.add_contributor(contributor=user2, auth=auth)
        project.add_contributor(contributor=user3, auth=auth)
        recently_added = list(user.get_recently_added())
        assert user3 == recently_added[0]
        assert user2 == recently_added[1]
        assert len(list(recently_added)) == 2

    def test_recently_added_multi_project(self, user, auth):
        # Three users are created
        user2 = UserFactory()
        user3 = UserFactory()
        user4 = UserFactory()

        # 2 projects created
        project = NodeFactory()
        project2 = NodeFactory()

        # Users 2 and 3 are added to original project
        project.add_contributor(contributor=user2, auth=auth)
        project.add_contributor(contributor=user3, auth=auth)

        # Users 2 and 3 are added to another project
        project2.add_contributor(contributor=user2, auth=auth)
        project2.add_contributor(contributor=user4, auth=auth)

        recently_added = list(user.get_recently_added())
        assert user4 == recently_added[0]
        assert user2 == recently_added[1]
        assert user3 == recently_added[2]
        assert len(recently_added) == 3

    def test_recently_added_length(self, user, auth):
        # Project created
        project = NodeFactory()

        assert len(list(user.get_recently_added())) == 0
        # Add 17 users
        for _ in range(17):
            project.add_contributor(
                contributor=UserFactory(),
                auth=auth
            )

        assert len(list(user.get_recently_added())) == 15


@pytest.mark.enable_implicit_clean
class TestTagging:

    def test_add_system_tag(self, user):
        tag_name = fake.word()
        user.add_system_tag(tag_name)
        user.save()

        assert len(user.system_tags) == 1

        tag = Tag.all_tags.get(name=tag_name, system=True)
        assert tag in user.all_tags.all()

    def test_add_system_tag_instance(self, user):
        tag = TagFactory(system=True)
        user.add_system_tag(tag)
        assert tag in user.all_tags.all()

    def test_add_system_tag_with_non_system_instance(self, user):
        tag = TagFactory(system=False)
        with pytest.raises(ValueError):
            user.add_system_tag(tag)
        assert tag not in user.all_tags.all()

    def test_tags_get_lowercased(self, user):
        tag_name = 'NeOn'
        user.add_system_tag(tag_name)
        user.save()

        tag = Tag.all_tags.get(name=tag_name.lower(), system=True)
        assert tag in user.all_tags.all()

    def test_system_tags_property(self, user):
        tag_name = fake.word()
        user.add_system_tag(tag_name)

        assert tag_name.lower() in user.system_tags

class TestCitationProperties:

    @pytest.fixture()
    def referrer(self):
        return UserFactory()

    @pytest.fixture()
    def email(self):
        return fake_email()

    @pytest.fixture()
    def unreg_user(self, referrer, project, email):
        user = UnregUserFactory()
        user.add_unclaimed_record(project,
            given_name=user.fullname, referrer=referrer,
            email=email)
        user.save()
        return user

    @pytest.fixture()
    def project(self, referrer):
        return NodeFactory(creator=referrer)

    def test_registered_user_csl(self, user):
        # Tests the csl name for a registered user
        if user.is_registered:
            assert bool(
                user.csl_name() ==
                {
                    'given': user.csl_given_name,
                    'family': user.family_name,
                }
            )

    def test_unregistered_user_csl(self, unreg_user, project, referrer):
        # Tests the csl name for an unregistered user
        name = unreg_user.unclaimed_records[project._primary_key]['name'].split(' ')
        family_name = name[-1]
        given_name = ' '.join(name[:-1])
        assert bool(
            unreg_user.csl_name(project._id) ==
            {
                'given': given_name,
                'family': family_name,
            }
        )
        # Tests the csl name for a user with different names across unclaimed_records
        project_2 = NodeFactory(creator=referrer)
        unreg_user.add_unclaimed_record(
            project_2,
            given_name='Bob Bobson',
            referrer=referrer,
            email=unreg_user.username
        )
        assert bool(
            unreg_user.csl_name(project_2._id) ==
            {
                'given': 'Bob',
                'family': 'Bobson'
            }
        )

# copied from tests/test_models.py
@pytest.mark.enable_bookmark_creation
@pytest.mark.enable_implicit_clean
class TestMergingUsers:

    @pytest.fixture()
    def email_subscriptions_enabled(self):
        settings.ENABLE_EMAIL_SUBSCRIPTIONS = True
        yield
        settings.ENABLE_EMAIL_SUBSCRIPTIONS = False

    @pytest.fixture()
    def master(self):
        return UserFactory(
            fullname='Joe Shmo',
            is_registered=True,
            emails=['joe@mail.com'],
        )

    @pytest.fixture()
    def dupe(self):
        return UserFactory(
            fullname='Joseph Shmo',
            emails=['joseph123@hotmail.com']
        )

    @pytest.fixture()
    def merge_dupe(self, master, dupe):
        def f():
            """Do the actual merge."""
            master.merge_user(dupe)
            master.save()
        return f

    def test_bookmark_collection_nodes_arent_merged(self, dupe, master, merge_dupe):
        dashnode = find_bookmark_collection(dupe)
        assert dupe.collection_set.filter(id=dashnode.id).exists()
        merge_dupe()
        assert not master.collection_set.filter(id=dashnode.id).exists()

    def test_dupe_is_merged(self, dupe, master, merge_dupe):
        merge_dupe()
        assert dupe.is_merged
        assert dupe.merged_by == master

    def test_dupe_email_is_appended(self, master, merge_dupe):
        merge_dupe()
        assert master.emails.filter(address='joseph123@hotmail.com').exists()

    @mock.patch('website.mailchimp_utils.get_mailchimp_api')
    def test_send_user_merged_signal(self, mock_get_mailchimp_api, dupe, merge_dupe):
        dupe.mailchimp_mailing_lists['foo'] = True
        dupe.save()

        with capture_signals() as mock_signals:
            merge_dupe()
            assert mock_signals.signals_sent() == {user_account_merged}

    @pytest.mark.enable_enqueue_task
    @mock.patch('website.mailchimp_utils.unsubscribe_mailchimp_async')
    @mock.patch('website.mailchimp_utils.get_mailchimp_api')
    def test_merged_user_unsubscribed_from_mailing_lists(self, mock_mailchimp_api, mock_unsubscribe, dupe, merge_dupe, email_subscriptions_enabled):
        list_name = settings.MAILCHIMP_GENERAL_LIST
        dupe.mailchimp_mailing_lists[list_name] = True
        dupe.save()
        merge_dupe()
        assert mock_unsubscribe.called

    def test_inherits_projects_contributed_by_dupe(self, dupe, master, merge_dupe):
        project = ProjectFactory()
        project.add_contributor(dupe)
        project.save()
        merge_dupe()
        project.reload()
        assert project.is_contributor(master) is True
        assert project.is_contributor(dupe) is False

    def test_inherits_projects_created_by_dupe(self, dupe, master, merge_dupe):
        project = ProjectFactory(creator=dupe)
        merge_dupe()
        project.reload()
        assert project.creator == master

    def test_adding_merged_user_as_contributor_adds_master(self, dupe, master, merge_dupe):
        project = ProjectFactory(creator=UserFactory())
        merge_dupe()
        project.add_contributor(contributor=dupe)
        assert project.is_contributor(master) is True
        assert project.is_contributor(dupe) is False

    def test_merging_dupe_who_is_contributor_on_same_projects(self, master, dupe, merge_dupe):
        # Both master and dupe are contributors on the same project
        project = ProjectFactory()
        project.add_contributor(contributor=master, visible=True)
        project.add_contributor(contributor=dupe, visible=True)
        project.save()
        merge_dupe()  # perform the merge
        project.reload()
        assert project.is_contributor(master)
        assert project.is_contributor(dupe) is False
        assert len(project.contributors) == 2   # creator and master are the only contribs
        assert project.contributor_set.get(user=master).visible is True

    def test_merging_dupe_who_has_different_visibility_from_master(self, master, dupe, merge_dupe):
        # Both master and dupe are contributors on the same project
        project = ProjectFactory()
        project.add_contributor(contributor=master, visible=False)
        project.add_contributor(contributor=dupe, visible=True)

        project.save()
        merge_dupe()  # perform the merge
        project.reload()

        assert project.contributor_set.get(user=master).visible is True

    def test_merging_dupe_who_is_a_non_bib_contrib_and_so_is_the_master(self, master, dupe, merge_dupe):
        # Both master and dupe are contributors on the same project
        project = ProjectFactory()
        project.add_contributor(contributor=master, visible=False)
        project.add_contributor(contributor=dupe, visible=False)

        project.save()
        merge_dupe()  # perform the merge
        project.reload()

        assert project.contributor_set.get(user=master).visible is False

    def test_merge_user_with_higher_permissions_on_project(self, master, dupe, merge_dupe):
        # Both master and dupe are contributors on the same project
        project = ProjectFactory()
        project.add_contributor(contributor=master, permissions=permissions.WRITE)
        project.add_contributor(contributor=dupe, permissions=permissions.ADMIN)

        project.save()
        merge_dupe()  # perform the merge

        assert project.get_permissions(master) == [permissions.READ, permissions.WRITE, permissions.ADMIN]

    def test_merge_user_with_lower_permissions_on_project(self, master, dupe, merge_dupe):
        # Both master and dupe are contributors on the same project
        project = ProjectFactory()
        project.add_contributor(contributor=master, permissions=permissions.ADMIN)
        project.add_contributor(contributor=dupe, permissions=permissions.WRITE)

        project.save()
        merge_dupe()  # perform the merge

        assert project.get_permissions(master) == [permissions.READ, permissions.WRITE, permissions.ADMIN]

    def test_merge_user_into_self_fails(self, master):
        with pytest.raises(ValueError):
            master.merge_user(master)

    def test_merging_user_moves_all_institution_affiliations(self):
        user_1 = UserFactory()
        institution_1 = InstitutionFactory()
        user_1.add_or_update_affiliated_institution(institution_1, sso_identity=f'{user_1._id}@{institution_1._id}', sso_mail=user_1.username)
        user_2 = UserFactory()
        institution_2 = InstitutionFactory()
        institution_3 = InstitutionFactory()
        user_2.add_or_update_affiliated_institution(institution_2, sso_identity=f'{user_2._id}@{institution_2._id}', sso_mail=user_2.username)
        user_2.add_or_update_affiliated_institution(institution_3, sso_identity=None, sso_mail=user_2.username)
        user_1.merge_user(user_2)
        user_1.reload()
        # Verify that the main user has the dupe user's institution affiliations
        assert user_1.is_affiliated_with_institution(institution_2)
        assert user_1.is_affiliated_with_institution(institution_3)
        user_2.reload()
        # Verify that the dupe user no longer has any institution affiliations
        assert not user_2.is_affiliated_with_institution(institution_2)
        assert not user_2.is_affiliated_with_institution(institution_3)
        # Verify that only one user is found when identity is present
        try:
            user_by_identity, is_identity_eligible = get_user_by_institution_identity(institution_2, f'{user_2._id}@{institution_2._id}')
            assert user_by_identity == user_1
            assert is_identity_eligible is True
        except InstitutionAffiliationStateError:
            pytest.fail('get_user_by_institution_identity() failed with InstitutionAffiliationStateError')
        # Verify that user is not found when identity is empty
        user_by_identity, is_identity_eligible = get_user_by_institution_identity(institution_2, None)
        assert user_by_identity is None
        assert is_identity_eligible is False


class TestDisablingUsers(CodexTestCase):
    def setUp(self):
        super().setUp()
        self.user = UserFactory()

    def test_user_enabled_by_default(self):
        assert self.user.is_disabled is False

    def test_disabled_user(self):
        """Ensure disabling a user sets date_disabled"""
        self.user.is_disabled = True
        self.user.save()

        assert isinstance(self.user.date_disabled, dt.datetime)
        assert self.user.is_disabled is True
        assert self.user.is_active is False

    def test_reenabled_user(self):
        """Ensure restoring a disabled user unsets date_disabled"""
        self.user.is_disabled = True
        self.user.save()

        self.user.is_disabled = False
        self.user.save()

        assert self.user.date_disabled is None
        assert self.user.is_disabled is False
        assert self.user.is_active is True

    def test_is_disabled_idempotency(self):
        self.user.is_disabled = True
        self.user.save()

        old_date_disabled = self.user.date_disabled

        self.user.is_disabled = True
        self.user.save()

        new_date_disabled = self.user.date_disabled

        assert new_date_disabled == old_date_disabled

    @mock.patch('website.mailchimp_utils.get_mailchimp_api')
    def test_deactivate_account_and_remove_sessions(self, mock_mail):
        session1 = SessionStore()
        session1.create()
        UserSessionMap.objects.create(user=self.user, session_key=session1.session_key)

        session2 = SessionStore()
        session2.create()
        UserSessionMap.objects.create(user=self.user, session_key=session2.session_key)

        self.user.mailchimp_mailing_lists[settings.MAILCHIMP_GENERAL_LIST] = True
        self.user.save()
        self.user.deactivate_account()

        assert self.user.is_disabled is True
        assert isinstance(self.user.date_disabled, dt.datetime)
        assert self.user.mailchimp_mailing_lists[settings.MAILCHIMP_GENERAL_LIST] is False

        assert not SessionStore().exists(session_key=session1.session_key)
        assert not SessionStore().exists(session_key=session2.session_key)


# Copied from tests/modes/test_user.py
@pytest.mark.enable_bookmark_creation
class TestUser(CodexTestCase):
    def setUp(self):
        super().setUp()
        self.user = AuthUserFactory()

    # Regression test for https://github.com/CenterForOpenScience/codex.io/issues/2454
    def test_add_unconfirmed_email_when_email_verifications_is_empty(self):
        self.user.email_verifications = []
        self.user.save()
        email = fake_email()
        self.user.add_unconfirmed_email(email)
        self.user.save()
        assert email in self.user.unconfirmed_emails

    def test_unconfirmed_emails(self):
        assert self.user.unconfirmed_emails == []
        self.user.add_unconfirmed_email('foo@bar.com')
        assert self.user.unconfirmed_emails == ['foo@bar.com']

        # email_verifications field may NOT be None
        self.user.email_verifications = []
        self.user.save()
        assert self.user.unconfirmed_emails == []

    def test_unconfirmed_emails_unregistered_user(self):
        assert UnregUserFactory().unconfirmed_emails == []

    def test_unconfirmed_emails_unconfirmed_user(self):
        user = UnconfirmedUserFactory()

        assert user.unconfirmed_emails == [user.username]

    # regression test for https://sentry.cos.io/sentry/codex/issues/6510/
    def test_unconfirmed_email_info_when_email_verifications_is_empty(self):
        user = UserFactory()
        user.email_verifications = []
        assert user.unconfirmed_email_info == []

    def test_remove_unconfirmed_email(self):
        self.user.add_unconfirmed_email('foo@bar.com')
        self.user.save()

        assert 'foo@bar.com' in self.user.unconfirmed_emails  # sanity check

        self.user.remove_unconfirmed_email('foo@bar.com')
        self.user.save()

        assert 'foo@bar.com' not in self.user.unconfirmed_emails

    def test_confirm_email(self):
        token = self.user.add_unconfirmed_email('foo@bar.com')
        self.user.confirm_email(token)

        assert 'foo@bar.com' not in self.user.unconfirmed_emails
        assert self.user.emails.filter(address='foo@bar.com').exists()

    def test_confirm_email_comparison_is_case_insensitive(self):
        u = UnconfirmedUserFactory.build(
            username='letsgettacos@lgt.com'
        )
        u.add_unconfirmed_email('LetsGetTacos@LGT.com')
        u.save()
        assert u.is_confirmed is False  # sanity check

        token = u.get_confirmation_token('LetsGetTacos@LGT.com')

        confirmed = u.confirm_email(token)
        assert confirmed is True
        assert u.is_confirmed is True

    def test_cannot_remove_primary_email_from_email_list(self):
        with pytest.raises(PermissionsError) as e:
            self.user.remove_email(self.user.username)
        assert str(e.value) == 'Can\'t remove primary email'

    def test_add_same_unconfirmed_email_twice(self):
        email = 'test@mail.com'
        token1 = self.user.add_unconfirmed_email(email)
        self.user.save()
        self.user.reload()
        assert token1 == self.user.get_confirmation_token(email)
        assert email == self.user.get_unconfirmed_email_for_token(token1)

        token2 = self.user.add_unconfirmed_email(email)
        self.user.save()
        self.user.reload()
        assert token1 != self.user.get_confirmation_token(email)
        assert token2 == self.user.get_confirmation_token(email)
        assert email == self.user.get_unconfirmed_email_for_token(token2)
        with pytest.raises(InvalidTokenError):
            self.user.get_unconfirmed_email_for_token(token1)

    def test_contributed_property(self):
        projects_contributed_to = self.user.nodes.all()
        assert list(self.user.contributed.all()) == list(projects_contributed_to)

    def test_contributor_to_property(self):
        normal_node = ProjectFactory(creator=self.user)
        normal_contributed_node = ProjectFactory()
        normal_contributed_node.add_contributor(self.user)
        normal_contributed_node.save()
        deleted_node = ProjectFactory(creator=self.user, is_deleted=True)
        bookmark_collection_node = find_bookmark_collection(self.user)
        collection_node = CollectionFactory(creator=self.user)
        project_to_be_invisible_on = ProjectFactory()
        project_to_be_invisible_on.add_contributor(self.user, visible=False)
        project_to_be_invisible_on.save()
        group = CODEXGroupFactory(creator=self.user, name='Platform')
        group_project = ProjectFactory()
        group_project.add_codex_group(group, permissions.READ)

        contributor_to_nodes = [node._id for node in self.user.contributor_to]

        assert normal_node._id in contributor_to_nodes
        assert normal_contributed_node._id in contributor_to_nodes
        assert project_to_be_invisible_on._id in contributor_to_nodes
        assert deleted_node._id not in contributor_to_nodes
        assert bookmark_collection_node._id not in contributor_to_nodes
        assert collection_node._id not in contributor_to_nodes
        assert group_project._id not in contributor_to_nodes

    def test_contributor_or_group_member_to_property(self):
        normal_node = ProjectFactory(creator=self.user)
        normal_contributed_node = ProjectFactory()
        normal_contributed_node.add_contributor(self.user)
        normal_contributed_node.save()
        deleted_node = ProjectFactory(creator=self.user, is_deleted=True)
        bookmark_collection_node = find_bookmark_collection(self.user)
        collection_node = CollectionFactory(creator=self.user)
        project_to_be_invisible_on = ProjectFactory()
        project_to_be_invisible_on.add_contributor(self.user, visible=False)
        project_to_be_invisible_on.save()
        group = CODEXGroupFactory(creator=self.user, name='Platform')
        group_project = ProjectFactory()
        group_project.add_codex_group(group, permissions.READ)
        registration = RegistrationFactory(creator=self.user)

        contributor_to_or_group_member_nodes = [node._id for node in self.user.contributor_or_group_member_to]

        assert normal_node._id in contributor_to_or_group_member_nodes
        assert normal_contributed_node._id in contributor_to_or_group_member_nodes
        assert project_to_be_invisible_on._id in contributor_to_or_group_member_nodes
        assert deleted_node._id not in contributor_to_or_group_member_nodes
        assert bookmark_collection_node._id not in contributor_to_or_group_member_nodes
        assert collection_node._id not in contributor_to_or_group_member_nodes
        assert group_project._id in contributor_to_or_group_member_nodes
        assert registration._id in contributor_to_or_group_member_nodes

    def test_all_nodes_property(self):
        project = ProjectFactory(creator=self.user)
        project_two = ProjectFactory()

        group = CODEXGroupFactory(creator=self.user)
        project_two.add_codex_group(group)
        project_two.save()

        project_three = ProjectFactory()
        project_three.save()

        user_nodes = self.user.all_nodes
        assert user_nodes.count() == 2
        assert project in user_nodes
        assert project_two in user_nodes
        assert project_three not in user_nodes

    def test_visible_contributor_to_property(self):
        invisible_contributor = UserFactory()
        normal_node = ProjectFactory(creator=invisible_contributor)
        deleted_node = ProjectFactory(creator=invisible_contributor, is_deleted=True)
        bookmark_collection_node = find_bookmark_collection(invisible_contributor)
        collection_node = CollectionFactory(creator=invisible_contributor)
        project_to_be_invisible_on = ProjectFactory()
        project_to_be_invisible_on.add_contributor(invisible_contributor, visible=False)
        project_to_be_invisible_on.save()
        visible_contributor_to_nodes = [node._id for node in invisible_contributor.visible_contributor_to]

        assert normal_node._id in visible_contributor_to_nodes
        assert deleted_node._id not in visible_contributor_to_nodes
        assert bookmark_collection_node._id not in visible_contributor_to_nodes
        assert collection_node._id not in visible_contributor_to_nodes
        assert project_to_be_invisible_on._id not in visible_contributor_to_nodes

    def test_created_property(self):
        # make sure there's at least one project
        ProjectFactory(creator=self.user)
        projects_created_by_user = AbstractNode.objects.filter(creator=self.user)
        assert list(self.user.nodes_created.all()) == list(projects_created_by_user)

    def test_remove_all_affiliated_institutions(self):
        user = UserFactory()
        for institution in [InstitutionFactory(), InstitutionFactory(), InstitutionFactory()]:
            user.add_or_update_affiliated_institution(institution, sso_identity=f'{user._id}@{institution._id}', sso_mail=user.username)
        assert user.get_affiliated_institutions().count() == 3
        user.remove_all_affiliated_institutions()
        user.reload()
        assert user.get_affiliated_institutions().count() == 0


@pytest.mark.enable_implicit_clean
class TestUserValidation(CodexTestCase):

    def setUp(self):
        super().setUp()
        self.user = AuthUserFactory()

    def test_validate_fullname_none(self):
        self.user.fullname = None
        with pytest.raises(ValidationError):
            self.user.save()

    def test_validate_fullname_empty(self):
        self.user.fullname = ''
        with pytest.raises(ValidationError):
            self.user.save()

    def test_validate_social_profile_websites_empty(self):
        self.user.social = {'profileWebsites': []}
        self.user.save()
        assert self.user.social['profileWebsites'] == []

    def test_validate_social_profile_website_many_different(self):
        basepath = os.path.dirname(__file__)
        url_data_path = os.path.join(basepath, '../website/static/urlValidatorTest.json')
        with open(url_data_path) as url_test_data:
            data = json.load(url_test_data)

        previous_number_of_domains = NotableDomain.objects.all().count()
        fails_at_end = False
        for should_pass in data['testsPositive']:
            try:
                self.user.social = {'profileWebsites': [should_pass]}
                with mock.patch.object(spam_tasks.requests, 'head'):
                    self.user.save()
                assert self.user.social['profileWebsites'] == [should_pass]
            except ValidationError:
                fails_at_end = True
                print('\"' + should_pass + '\" failed but should have passed while testing that the validator ' + data['testsPositive'][should_pass])

        for should_fail in data['testsNegative']:
            self.user.social = {'profileWebsites': [should_fail]}
            try:
                with pytest.raises(ValidationError):
                    with mock.patch.object(spam_tasks.requests, 'head'):
                        self.user.save()
            except AssertionError:
                fails_at_end = True
                print('\"' + should_fail + '\" passed but should have failed while testing that the validator ' + data['testsNegative'][should_fail])
        if fails_at_end:
            raise

        # Not all domains that are permissable are possible to use as spam,
        # some are correctly not extracted and not kept in notable domain so spot
        # check some, not all, because not all `testsPositive` urls should be in
        # NotableDomains
        assert NotableDomain.objects.all().count() == previous_number_of_domains + 12
        assert NotableDomain.objects.get(domain='definitelyawebsite.com')
        assert NotableDomain.objects.get(domain='a.b-c.de')

    def test_validate_multiple_profile_websites_valid(self):
        self.user.social = {'profileWebsites': ['http://cos.io/', 'http://thebuckstopshere.com', 'http://dinosaurs.com']}
        with mock.patch.object(spam_tasks.requests, 'head'):
            self.user.save()
        assert self.user.social['profileWebsites'] == ['http://cos.io/', 'http://thebuckstopshere.com', 'http://dinosaurs.com']

    def test_validate_social_profile_websites_invalid(self):
        self.user.social = {'profileWebsites': ['help computer']}
        with pytest.raises(ValidationError):
            self.user.save()

    def test_validate_multiple_profile_social_profile_websites_invalid(self):
        self.user.social = {'profileWebsites': ['http://cos.io/', 'help computer', 'http://dinosaurs.com']}
        with pytest.raises(ValidationError):
            self.user.save()

    def test_empty_social_links(self):
        assert self.user.social_links == {}
        assert len(self.user.social_links) == 0

    def test_profile_website_unchanged(self):
        self.user.social = {'profileWebsites': ['http://cos.io/']}
        with mock.patch.object(spam_tasks.requests, 'head'):
            self.user.save()
        assert self.user.social_links['profileWebsites'] == ['http://cos.io/']
        assert len(self.user.social_links) == 1

    def test_various_social_handles(self):
        self.user.social = {
            'profileWebsites': ['http://cos.io/'],
            'twitter': ['CODEXramework'],
            'github': ['CenterForOpenScience'],
            'scholar': 'ztt_j28AAAAJ'
        }
        with mock.patch.object(spam_tasks.requests, 'head'):
            self.user.save()
        assert self.user.social_links == {
            'profileWebsites': ['http://cos.io/'],
            'twitter': 'http://twitter.com/CODEXramework',
            'github': 'http://github.com/CenterForOpenScience',
            'scholar': 'http://scholar.google.com/citations?user=ztt_j28AAAAJ'
        }

    def test_multiple_profile_websites(self):
        self.user.social = {
            'profileWebsites': ['http://cos.io/', 'http://thebuckstopshere.com', 'http://dinosaurs.com'],
            'twitter': ['CODEXramework'],
            'github': ['CenterForOpenScience']
        }
        with mock.patch.object(spam_tasks.requests, 'head'):
            self.user.save()
        assert self.user.social_links == {
            'profileWebsites': ['http://cos.io/', 'http://thebuckstopshere.com', 'http://dinosaurs.com'],
            'twitter': 'http://twitter.com/CODEXramework',
            'github': 'http://github.com/CenterForOpenScience'
        }

    def test_nonsocial_ignored(self):
        self.user.social = {
            'foo': 'bar',
        }
        with pytest.raises(ValidationError) as exc_info:
            self.user.save()
        assert isinstance(exc_info.value.args[0], dict)
        assert self.user.social_links == {}

    def test_validate_jobs_valid(self):
        self.user.jobs = [{
            'institution': 'School of Lover Boys',
            'department': 'Fancy Patter',
            'title': 'Lover Boy',
            'startMonth': 1,
            'startYear': '1970',
            'endMonth': 1,
            'endYear': '1980',
        }]
        self.user.save()

    def test_validate_jobs_institution_empty(self):
        self.user.jobs = [{'institution': ''}]
        with pytest.raises(ValidationError):
            self.user.save()

    def test_validate_jobs_bad_end_date(self):
        # end year is < start year
        self.user.jobs = [{
            'institution': fake.company(),
            'department': fake.bs(),
            'position': fake.catch_phrase(),
            'startMonth': 1,
            'startYear': '1970',
            'endMonth': 1,
            'endYear': '1960',
        }]
        with pytest.raises(ValidationError):
            self.user.save()

    def test_validate_schools_bad_end_date(self):
        # end year is < start year
        self.user.schools = [{
            'degree': fake.catch_phrase(),
            'institution': fake.company(),
            'department': fake.bs(),
            'startMonth': 1,
            'startYear': '1970',
            'endMonth': 1,
            'endYear': '1960',
        }]
        with pytest.raises(ValidationError):
            self.user.save()

    def test_validate_jobs_bad_year(self):
        start_year = ['hi', '20507', '99', '67.34']
        for year in start_year:
            self.user.jobs = [{
                'institution': fake.company(),
                'department': fake.bs(),
                'position': fake.catch_phrase(),
                'startMonth': 1,
                'startYear': year,
                'endMonth': 1,
                'endYear': '1960',
            }]
            with pytest.raises(ValidationError):
                self.user.save()

    def test_validate_schools_bad_year(self):
        start_year = ['hi', '20507', '99', '67.34']
        for year in start_year:
            self.user.schools = [{
                'degree': fake.catch_phrase(),
                'institution': fake.company(),
                'department': fake.bs(),
                'startMonth': 1,
                'startYear': year,
                'endMonth': 1,
                'endYear': '1960',
            }]
            with pytest.raises(ValidationError):
                self.user.save()


class TestUserGdprDelete:

    @pytest.fixture()
    def user(self):
        return AuthUserFactory()

    @pytest.fixture()
    def project_with_two_admins(self, user):
        second_admin_contrib = UserFactory()
        project = ProjectFactory(creator=user)
        project.add_contributor(second_admin_contrib)
        project.set_permissions(user=second_admin_contrib, permissions=permissions.ADMIN)
        project.save()
        return project

    @pytest.fixture()
    def project_with_two_admins_and_addon_credentials(self, user):
        second_admin_contrib = UserFactory()
        project = ProjectFactory(creator=user)
        project.add_contributor(second_admin_contrib)
        project.set_permissions(user=second_admin_contrib, permissions=permissions.ADMIN)
        user = project.creator

        node_settings = project.add_addon('github', auth=None)
        user_settings = user.add_addon('github')
        node_settings.user_settings = user_settings
        github_account = GitHubAccountFactory()
        github_account.save()
        node_settings.external_account = github_account
        node_settings.save()
        user.save()
        project.save()
        return project

    @pytest.fixture()
    def registration(self, user):
        registration = RegistrationFactory(creator=user)
        registration.save()
        return registration

    @pytest.fixture()
    def registration_with_draft_node(self, user, registration):
        registration.branched_from = DraftNodeFactory(creator=user)
        registration.save()
        return registration

    @pytest.fixture()
    def project(self, user):
        project = ProjectFactory(creator=user)
        project.save()
        return project

    @pytest.fixture()
    def preprint(self, user):
        preprint = PreprintFactory(creator=user)
        preprint.save()
        return preprint

    @pytest.fixture()
    def project_user_is_only_admin(self, user):
        non_admin_contrib = UserFactory()
        project = ProjectFactory(creator=user)
        project.add_contributor(non_admin_contrib)
        project.add_unregistered_contributor('lisa', 'lisafrank@cos.io', permissions=permissions.ADMIN, auth=Auth(user))
        project.save()
        return project

    def test_can_gdpr_delete(self, user):
        user.social = ['fake social']
        user.schools = ['fake schools']
        user.jobs = ['fake jobs']
        user.external_identity = ['fake external identity']
        user.external_accounts.add(ExternalAccountFactory())

        user.gdpr_delete()

        assert user.fullname == 'Deleted user'
        assert user.suffix == ''
        assert user.social == {}
        assert user.schools == []
        assert user.jobs == []
        assert user.external_identity == {}
        assert not user.emails.exists()
        assert not user.external_accounts.exists()
        assert user.is_disabled
        assert user.deleted is not None

    def test_can_gdpr_delete_personal_nodes(self, user):

        user.gdpr_delete()
        assert user.nodes.exclude(is_deleted=True).count() == 0

    def test_can_gdpr_delete_personal_registrations(self, user, registration_with_draft_node):
        assert DraftRegistration.objects.all().count() == 1
        assert DraftNode.objects.all().count() == 1

        with pytest.raises(UserStateError) as exc_info:
            user.gdpr_delete()

        assert exc_info.value.args[0] == 'You cannot delete this user because they have one or more registrations.'
        assert DraftRegistration.objects.all().count() == 1
        assert DraftNode.objects.all().count() == 1

        registration_with_draft_node.remove_node(Auth(user))
        assert DraftRegistration.objects.all().count() == 1
        assert DraftNode.objects.all().count() == 1
        user.gdpr_delete()

        # DraftNodes soft-deleted, DraftRegistions hard-deleted
        assert user.nodes.exclude(is_deleted=True).count() == 0
        assert DraftRegistration.objects.all().count() == 0

    def test_can_gdpr_delete_shared_nodes_with_multiple_admins(self, user, project_with_two_admins):

        user.gdpr_delete()
        assert user.nodes.all().count() == 0

    def test_can_gdpr_delete_shared_draft_registration_with_multiple_admins(self, user, registration):
        other_admin = AuthUserFactory()
        draft_registrations = user.draft_registrations.get()
        draft_registrations.add_contributor(other_admin, permissions='admin')
        assert draft_registrations.contributors.all().count() == 2
        registration.delete_registration_tree(save=True)

        user.gdpr_delete()
        assert draft_registrations.contributors.get() == other_admin
        assert user.nodes.filter(deleted__isnull=True).count() == 0

    def test_cant_gdpr_delete_registrations(self, user, registration):

        with pytest.raises(UserStateError) as exc_info:
            user.gdpr_delete()

        assert exc_info.value.args[0] == 'You cannot delete this user because they have one or more registrations.'

    def test_cant_gdpr_delete_preprints(self, user, preprint):

        with pytest.raises(UserStateError) as exc_info:
            user.gdpr_delete()

        assert exc_info.value.args[0] == 'You cannot delete this user because they have one or more preprints.'

    def test_cant_gdpr_delete_shared_node_if_only_admin(self, user, project_user_is_only_admin):

        with pytest.raises(UserStateError) as exc_info:
            user.gdpr_delete()

        assert exc_info.value.args[0] == 'You cannot delete Node {} because it would' \
                                         ' be a Node with contributors, but with no admin.'.format(project_user_is_only_admin._id)

    def test_cant_gdpr_delete_codex_group_if_only_manager(self, user):
        group = CODEXGroupFactory(name='My Group', creator=user)
        codex_group_name = group.name
        manager_group_name = group.manager_group.name
        member_group_name = group.member_group.name
        member = AuthUserFactory()
        group.make_member(member)

        with pytest.raises(UserStateError) as exc_info:
            user.gdpr_delete()

        assert exc_info.value.args[0] == 'You cannot delete this user because ' \
                                        'they are the only registered manager of CODEXGroup ' \
                                        '{} that contains other members.'.format(group._id)

        unregistered = group.add_unregistered_member('fake_user', 'fake_email@cos.io', Auth(user), 'manager')
        assert len(group.managers) == 2

        with pytest.raises(UserStateError) as exc_info:
            user.gdpr_delete()

        assert exc_info.value.args[0] == 'You cannot delete this user because ' \
                                        'they are the only registered manager of CODEXGroup ' \
                                        '{} that contains other members.'.format(group._id)

        group.remove_member(member)
        member.gdpr_delete()
        # User is not the last member in the group, so they are just removed
        assert CODEXGroup.objects.filter(name=codex_group_name).exists()
        assert Group.objects.filter(name=manager_group_name).exists()
        assert Group.objects.filter(name=member_group_name).exists()
        assert group.is_member(member) is False
        assert group.is_manager(member) is False

        group.remove_member(unregistered)
        user.gdpr_delete()
        # Group was deleted because user was the only member
        assert not CODEXGroup.objects.filter(name=codex_group_name).exists()
        assert not Group.objects.filter(name=manager_group_name).exists()
        assert not Group.objects.filter(name=member_group_name).exists()

    def test_cant_gdpr_delete_with_addon_credentials(self, user, project_with_two_admins_and_addon_credentials):

        with pytest.raises(UserStateError) as exc_info:
            user.gdpr_delete()
        assert exc_info.value.args[0] == 'You cannot delete this user because they have an external account for' \
                                         ' github attached to Node {}, which has other contributors.'.format(project_with_two_admins_and_addon_credentials._id)
