import json
from unittest import mock
import pytest
import builtins

from django.db.utils import IntegrityError
from codex.models.licenses import serialize_node_license_record, serialize_node_license
from codex.utils.migrations import ensure_licenses
from codex.exceptions import NodeStateError
from framework.auth.core import Auth


from codex.models import (
    NodeLicense,
    NodeLog
)

from codex_tests.factories import (
    AuthUserFactory,
    ProjectFactory,
    NodeLicenseRecordFactory
)

CHANGED_NAME = 'FOO BAR'
CHANGED_TEXT = 'Some good new text'

CHANGED_PROPERTIES = ['foo', 'bar']
LICENSE_TEXT = json.dumps({
    'MIT': {
        'name': CHANGED_NAME,
        'text': CHANGED_TEXT,
        'properties': CHANGED_PROPERTIES
    }
})


@pytest.mark.django_db
class TestNodeLicenses:

    @pytest.fixture()
    def user(self):
        return AuthUserFactory()

    @pytest.fixture()
    def node(self, node_license, user):
        node = ProjectFactory(creator=user)
        node.node_license = NodeLicenseRecordFactory(
            node_license=node_license,
            year=self.YEAR,
            copyright_holders=self.COPYRIGHT_HOLDERS
        )
        node.save()
        return node

    LICENSE_NAME = 'MIT License'
    YEAR = '2105'
    COPYRIGHT_HOLDERS = ['Foo', 'Bar']

    @pytest.fixture()
    def node_license(self):
        return NodeLicense.objects.get(name=self.LICENSE_NAME)

    def test_serialize_node_license(self, node_license):
        serialized = serialize_node_license(node_license)
        assert serialized['name'] == self.LICENSE_NAME
        assert serialized['id'] == node_license.license_id
        assert serialized['text'] == node_license.text

    def test_serialize_node_license_record(self, node, node_license):
        serialized = serialize_node_license_record(node.node_license)
        assert serialized['name'] == self.LICENSE_NAME
        assert serialized['id'] == node_license.license_id
        assert serialized['text'] == node_license.text
        assert serialized['year'] == self.YEAR
        assert serialized['copyright_holders'] == self.COPYRIGHT_HOLDERS

    def test_serialize_node_license_record_None(self, node):
        node.node_license = None
        serialized = serialize_node_license_record(node.node_license)
        assert serialized == {}

    def test_copy_node_license_record(self, node):
        record = node.node_license
        copied = record.copy()
        assert copied._id is not None
        assert record._id != copied._id
        for prop in ('license_id', 'name', 'node_license'):
            assert getattr(record, prop) == getattr(copied, prop)

    def test_license_uniqueness_on_id_is_enforced_in_the_database(self):
        NodeLicense(license_id='foo', name='bar', text='baz').save()
        with pytest.raises(IntegrityError):
            NodeLicense(license_id='foo', name='buz', text='boo').save()

    def test_ensure_licenses_updates_existing_licenses(self):
        assert ensure_licenses() == (0, 18)

    def test_ensure_licenses_no_licenses(self):
        before_count = NodeLicense.objects.all().count()
        NodeLicense.objects.all().delete()
        assert not NodeLicense.objects.all().count()

        ensure_licenses()
        assert before_count == NodeLicense.objects.all().count()

    def test_ensure_licenses_some_missing(self):
        NodeLicense.objects.get(license_id='LGPL3').delete()
        with pytest.raises(NodeLicense.DoesNotExist):
            NodeLicense.objects.get(license_id='LGPL3')
        ensure_licenses()
        found = NodeLicense.objects.get(license_id='LGPL3')
        assert found is not None

    def test_ensure_licenses_updates_existing(self):
        with mock.patch.object(builtins, 'open', mock.mock_open(read_data=LICENSE_TEXT)):
            ensure_licenses()
        MIT = NodeLicense.objects.get(license_id='MIT')
        assert MIT.name == CHANGED_NAME
        assert MIT.text == CHANGED_TEXT
        assert MIT.properties == CHANGED_PROPERTIES

    def test_node_set_node_license(self, node, user):
        GPL3 = NodeLicense.objects.get(license_id='GPL3')
        NEW_YEAR = '2014'
        COPYLEFT_HOLDERS = ['Richard Stallman']
        node.set_node_license(
            {
                'id': GPL3.license_id,
                'year': NEW_YEAR,
                'copyrightHolders': COPYLEFT_HOLDERS
            },
            auth=Auth(user),
            save=True
        )

        assert node.node_license.license_id == GPL3.license_id
        assert node.node_license.name == GPL3.name
        assert node.node_license.copyright_holders == COPYLEFT_HOLDERS
        assert node.logs.latest().action == NodeLog.CHANGED_LICENSE

    def test_node_set_node_license_invalid(self, node, user):
        with pytest.raises(NodeStateError):
            node.set_node_license(
                {
                    'id': 'SOME ID',
                    'year': 'foo',
                    'copyrightHolders': []
                },
                auth=Auth(user)
            )
        action = node.logs.latest().action if node.logs.count() else None
        assert action != NodeLog.CHANGED_LICENSE

    def test_manager_methods(self):
        # Projects can't have CCBYNCND but preprints can
        assert 'CCBYNCND' not in list(NodeLicense.objects.project_licenses().values_list('license_id', flat=True))
        assert 'CCBYNCND' in list(NodeLicense.objects.preprint_licenses().values_list('license_id', flat=True))
