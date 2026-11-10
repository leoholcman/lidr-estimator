"""Estado de la conversación: historial (ventana deslizante) y metadata del proyecto.

Todo vive en memoria del proceso, así que se pierde al reiniciar el servicio.
Para esta fase alcanza; si hiciera falta persistir, se cambia SessionStore.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.services.providers import Message

DEFAULT_MAX_TURNS = 6


class ProjectMetadata(BaseModel):
    """Hechos conocidos del proyecto en curso."""

    project_name: str | None = None
    assumed_team_size: int | None = Field(default=None, ge=1, le=100)
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str | None = None

    def is_empty(self) -> bool:
        return self == ProjectMetadata()

    def merge(self, update: "ProjectMetadata") -> "ProjectMetadata":
        """Combina con lo extraído en el último turno.

        Los campos escalares se pisan solo si el nuevo valor existe; las
        tecnologías se acumulan sin duplicados (sin distinguir mayúsculas).
        """
        technologies = list(self.mentioned_technologies)
        known = {t.lower() for t in technologies}
        for tech in update.mentioned_technologies:
            if tech.lower() not in known:
                technologies.append(tech)
                known.add(tech.lower())
        return ProjectMetadata(
            project_name=update.project_name or self.project_name,
            assumed_team_size=update.assumed_team_size or self.assumed_team_size,
            mentioned_technologies=technologies,
            agreed_scope=update.agreed_scope or self.agreed_scope,
        )


class ConversationHistory:
    """Ventana deslizante de los últimos `max_turns` turnos (par user + assistant).

    El system prompt no se guarda acá: se regenera en cada llamada a partir del
    `ProjectMetadata` actual, así que siempre está presente y actualizado.
    """

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS):
        if max_turns < 1:
            raise ValueError("max_turns debe ser >= 1")
        self.max_turns = max_turns
        self._turns: list[tuple[str, str]] = []
        self.total_turns = 0  # incluye los descartados

    def add_turn(self, user: str, assistant: str) -> None:
        self._turns.append((user, assistant))
        self.total_turns += 1
        if len(self._turns) > self.max_turns:
            # descarta los pares más antiguos
            self._turns = self._turns[-self.max_turns :]

    def __len__(self) -> int:
        return len(self._turns)

    def to_messages_list(self, system_prompt: str, pending_user: str | None = None) -> list[Message]:
        """Array `messages` listo para la API: system + ventana (+ mensaje nuevo)."""
        messages: list[Message] = [{"role": "system", "content": system_prompt}]
        for user, assistant in self._turns:
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": assistant})
        if pending_user is not None:
            messages.append({"role": "user", "content": pending_user})
        return messages


@dataclass
class Session:
    session_id: str
    history: ConversationHistory
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    created_at: float = field(default_factory=time.time)
    # Serializa los turnos de una misma sesión (dos pestañas enviando a la vez)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionStore:
    """Sesiones indexadas por `session_id`, en memoria del proceso."""

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS, max_sessions: int = 1000):
        self.max_turns = max_turns
        self.max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        if len(self._sessions) >= self.max_sessions:
            self._sessions.pop(next(iter(self._sessions)))  # la más antigua
        session = Session(session_id=str(uuid.uuid4()), history=ConversationHistory(self.max_turns))
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def clear(self) -> None:
        self._sessions.clear()
