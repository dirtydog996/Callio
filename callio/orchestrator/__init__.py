from __future__ import annotations

from typing import Any

from callio.config.settings import Settings, get_settings
from callio.core.database import Database
from callio.core.session_events import SessionEventStore
from callio.orchestrator.event_bus import EventBus
from callio.orchestrator.progress_snapshot import ProgressSnapshot
from callio.orchestrator.session_registry import SessionRegistry
from callio.orchestrator.task_coordinator import TaskCoordinator
from callio.orchestrator.task_proposal import TaskProposal
from callio.orchestrator.transcript_buffer import TranscriptBuffer


class Orchestrator:
    def __init__(
        self,
        database: Database,
        status_manager: Any,
        task_dispatcher: Any,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.database = database
        self.events = SessionEventStore(database)
        self.event_bus = EventBus(database, self.events, status_manager.broadcast_status)
        self.sessions = SessionRegistry(database, self.event_bus)
        self.coordinator = TaskCoordinator(database, self.event_bus, task_dispatcher, self.settings)
        self.transcripts = TranscriptBuffer(database, self.event_bus, self.settings, self.coordinator)
        self.proposals = TaskProposal(database, self.event_bus)
        self.progress = ProgressSnapshot(database, self.settings)
