"""Import every ORM model so Alembic can discover complete metadata."""

from app.modules.admins.models import Admin
from app.modules.broadcasts.models import Broadcast, BroadcastRecipient
from app.modules.channels.models import Channel
from app.modules.favorites.models import UserFavorite
from app.modules.notifications.models import NotificationType, UserNotificationSetting
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.referrals.models import Referral
from app.modules.settings.models import BotSetting, BotSettingValueType
from app.modules.signals.models import (
    Signal,
    SignalDirection,
    SignalEvent,
    SignalEventType,
    SignalStatus,
    SignalPublicationScope,
    SignalTarget,
    SignalTargetStatus,
)
from app.modules.signal_automation.models import SignalAutomationMetadata, SignalRuleEvidence
from app.modules.paper_runtime.models import SignalDelivery
from app.modules.signal_quality.models import SignalQualityAssessment
from app.modules.scale_in.models import (
    BrooksPosition,
    BrooksPositionEntryLot,
    BrooksPositionExitFill,
    BrooksPositionScaleEvent,
    BrooksPositionRiskSnapshot,
)
from app.modules.operations.models import (
    PaymentSettlementState,
    RuntimeHealth,
    SignalLifecycleState,
    VipEntitlementState,
)
from app.modules.support.models import SupportMessage, SupportTicket
from app.modules.subscriptions.models import (
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.modules.users.models import User, UserStatus
from app.modules.performance_intelligence.models import (
    PerformanceMetric,
    PatternStatistic,
    FailureAnalysis,
    DecisionQualityScore,
)

MODEL_TYPES = (
    User,
    Admin,
    Channel,
    BotSetting,
    Broadcast,
    BroadcastRecipient,
    SupportTicket,
    SupportMessage,
    Signal,
    SignalTarget,
    SignalEvent,
    SignalAutomationMetadata,
    SignalRuleEvidence,
    SignalDelivery,
    SignalQualityAssessment,
    BrooksPosition,
    BrooksPositionEntryLot,
    BrooksPositionExitFill,
    BrooksPositionScaleEvent,
    BrooksPositionRiskSnapshot,
    SignalLifecycleState,
    VipEntitlementState,
    PaymentSettlementState,
    RuntimeHealth,
    UserFavorite,
    UserNotificationSetting,
    SubscriptionPlan,
    Subscription,
    Payment,
    Referral,
    PerformanceMetric,
    PatternStatistic,
    FailureAnalysis,
    DecisionQualityScore,
)

__all__ = [
    "Admin",
    "BotSetting",
    "BotSettingValueType",
    "Broadcast",
    "BroadcastRecipient",
    "Channel",
    "MODEL_TYPES",
    "NotificationType",
    "Payment",
    "PaymentStatus",
    "Referral",
    "Signal",
    "SignalDirection",
    "SignalEvent",
    "SignalEventType",
    "SignalStatus",
    "SignalPublicationScope",
    "SignalTarget",
    "SignalTargetStatus",
    "SignalAutomationMetadata",
    "SignalRuleEvidence",
    "SignalDelivery",
    "BrooksPosition",
    "BrooksPositionEntryLot",
    "BrooksPositionExitFill",
    "BrooksPositionScaleEvent",
    "BrooksPositionRiskSnapshot",
    "SignalLifecycleState",
    "VipEntitlementState",
    "PaymentSettlementState",
    "RuntimeHealth",
    "UserFavorite",
    "UserNotificationSetting",
    "User",
    "UserStatus",
    "SupportMessage",
    "SupportTicket",
    "PerformanceMetric",
    "PatternStatistic",
    "FailureAnalysis",
    "DecisionQualityScore",
    "Subscription",
    "SubscriptionPlan",
    "SubscriptionStatus",
]

from app.modules.operations.approval_evidence import ApprovedMarketEvidence  # noqa: F401
