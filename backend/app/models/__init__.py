"""Import all models so metadata is complete (used by alembic autogenerate)."""

from app.models.base import Base, GUID, TimestampMixin, UUIDPkMixin, utcnow  # noqa: F401
from app.models.device import (  # noqa: F401
    Device,
    DeviceCapability,
    DeviceCredential,
    DeviceNetwork,
    DeviceProtocol,
    DeviceRawData,
)
from app.models.enums import (  # noqa: F401
    CapabilityState,
    CredentialKind,
    CredentialVerificationState,
    DetectionState,
    DeviceStatus,
    DiscoveryStage,
    EventType,
    JobStatus,
    OperationAction,
    SyncDirection,
    SyncStatus,
    UserRole,
    VerificationType,
)
from app.models.jobs import DiscoveryJob, DiscoveryResult, SyncJob  # noqa: F401
from app.models.personnel import (  # noqa: F401
    AttendanceLog,
    AuditLog,
    DeviceUser,
    SystemSetting,
    SystemUser,
)


def register_models() -> None:
    """No-op that forces model import side effects (tables registered)."""
    return None
