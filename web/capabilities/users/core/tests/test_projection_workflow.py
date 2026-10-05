from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.recovery import ToolUsersRecoveryService
from atlanticus.web.users.store import UsersRuntimeStore
from atlanticus.web.users.web.projection_workflow import UsersProjectionWorkflow


def user(subject='subject'):
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer',
        subject_id=subject,
        display_name='User',
    )
    return RuntimeUser(
        identity=identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )


class Runtime(UsersRuntimeStore):
    def __init__(self, users=()):
        self.users = tuple(users)

    def resolve(self, identity):
        return None

    def list_users(self):
        return self.users

    def replace_all(self, users):
        self.users = tuple(sorted(users, key=lambda item: item.user_id))
        return self.users


class Snapshots:
    def __init__(self):
        self.items = {}

    def save(self, value):
        self.items[value.snapshot_id] = value

    def load(self, snapshot_id):
        return self.items[snapshot_id]

    def list_snapshot_ids(self, *, max_items=200):
        return tuple(self.items)

    def list_snapshot_summaries(self, *, max_items=200):
        return tuple((key, None) for key in self.items)


class Audit:
    def record(self, event):
        pass


class Before:
    def save(self, image):
        pass


def test_workflow_capture_inspect_and_replace_uses_complete_runtime_snapshot():
    desired = (user('a'), user('b'))
    runtime = Runtime((user('obsolete'),))
    snapshots = Snapshots()
    recovery = ToolUsersRecoveryService(
        runtime=runtime,
        materialize=lambda: desired,
        snapshots=snapshots,
        audit=Audit(),
        before_images=Before(),
        environment='local:test',
    )
    workflow = UsersProjectionWorkflow(
        recovery=recovery,
        snapshot_ids=snapshots.list_snapshot_ids,
        snapshot_summaries=snapshots.list_snapshot_summaries,
        read_snapshot=snapshots.load,
        operator_id=lambda: 'operator',
    )
    preview = workflow.preview_capture()
    saved = workflow.capture(preview, 'ticket')
    description = workflow.describe_snapshot(saved['snapshot_id'])
    assert description['snapshot_id'] == saved['snapshot_id']
    assert description['approved_count'] == 2
    assert 'tool_key' not in description
    inspection = workflow.inspect(saved['snapshot_id'])
    assert inspection['create_ids']
    assert inspection['delete_ids']
    result = workflow.apply(
        inspection=inspection,
        approval_reference='ticket-2',
        maintenance_confirmed=True,
        revocations_reviewed=True,
        confirmed=True,
    )
    assert result['created'] == 2
    assert result['deleted'] == 1
    assert runtime.list_users() == tuple(sorted(desired, key=lambda item: item.user_id))
