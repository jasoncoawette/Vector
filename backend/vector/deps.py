from __future__ import annotations

import sqlite3
from pathlib import Path

from .agents import AgentManager
from .agents.executor import SYSTEM_PROMPTS, ClaudeAgentExecutor
from .agents.types import AgentSpec, RunResult
from .config import get_settings
from .memory import HashEmbedder, MemoryStore, SqliteMemoryStore
from .store import connect
from .tools.builder import build_registry_for
from .tools.files import FileGuard
from .plans import PlanRunner
from .voice.brain import Brain, ClaudeBrain
from .voice.session import VoiceSession
from .voice.stt import STT, WhisperSTT
from .voice.tts import TTS, ElevenLabsTTS, PiperFallbackTTS

_conn: sqlite3.Connection | None = None
_agents: AgentManager | None = None
_plans: PlanRunner | None = None
_memory: MemoryStore | None = None
_file_guard: FileGuard | None = None
_obsidian = None  # ObsidianVault | None (avoid hard import at module load)
_maps = None  # MapsClient | None
_oauth_flow = None  # OAuthFlow | None
_token_store = None  # TokenStore | None
_session_factory: "callable[[], VoiceSession] | None" = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        s = get_settings()
        path = Path(s.workspace) / "vector.db"
        _conn = connect(path)
    return _conn


def set_db(conn: sqlite3.Connection | None) -> None:
    global _conn
    _conn = conn


def get_memory() -> MemoryStore:
    global _memory
    if _memory is None:
        _memory = SqliteMemoryStore(get_db(), HashEmbedder())
    return _memory


def set_memory(store: MemoryStore | None) -> None:
    global _memory
    _memory = store


def get_file_guard() -> FileGuard:
    global _file_guard
    if _file_guard is None:
        s = get_settings()
        _file_guard = FileGuard(read_root=s.workspace.parent, write_root=s.workspace)
    return _file_guard


def set_file_guard(guard: FileGuard | None) -> None:
    global _file_guard
    _file_guard = guard


def get_obsidian():
    """Lazily build an ObsidianVault pointed at the configured path.

    Returns None when the vault directory doesn't exist and can't be
    created — agents fall back to file + memory tools only."""
    global _obsidian
    if _obsidian is None:
        from .tools.obsidian import ObsidianVault

        s = get_settings()
        try:
            _obsidian = ObsidianVault(root=s.obsidian_vault)
        except (OSError, ValueError):
            return None
    return _obsidian


def set_obsidian(vault) -> None:
    global _obsidian
    _obsidian = vault


def get_maps():
    """Lazily build a MapsClient. Returns None when no API key is set
    so agents fall back to other tools without a hard failure."""
    global _maps
    if _maps is None:
        s = get_settings()
        if not s.google_maps_api_key:
            return None
        from .tools.maps import MapsClient

        _maps = MapsClient(api_key=s.google_maps_api_key)
    return _maps


def set_maps(client) -> None:
    global _maps
    _maps = client


def get_token_store():
    """Lazily build a Google TokenStore on top of the shared DB.

    Returns None when no token-encryption key is configured (refuse to
    write plaintext refresh tokens)."""
    global _token_store
    if _token_store is None:
        import os

        s = get_settings()
        key = s.oauth_token_key
        if not key:
            return None
        # The encrypt/decrypt helpers read VECTOR_OAUTH_TOKEN_KEY from
        # the environment; mirror the setting there so they line up.
        os.environ["VECTOR_OAUTH_TOKEN_KEY"] = key
        from .google_oauth import TokenStore

        _token_store = TokenStore(get_db())
    return _token_store


def set_token_store(store) -> None:
    global _token_store
    _token_store = store


def get_oauth_flow():
    """Lazily build the Google OAuthFlow. Returns None when the OAuth
    client id / secret aren't configured."""
    global _oauth_flow
    if _oauth_flow is None:
        s = get_settings()
        if not s.google_oauth_client_id or not s.google_oauth_client_secret:
            return None
        from .google_oauth import OAuthFlow

        _oauth_flow = OAuthFlow(
            client_id=s.google_oauth_client_id,
            client_secret=s.google_oauth_client_secret,
            port=s.port,
        )
    return _oauth_flow


def set_oauth_flow(flow) -> None:
    global _oauth_flow
    _oauth_flow = flow


def _registry_factory(agent_type: str):
    return build_registry_for(
        agent_type,
        guard=get_file_guard(),
        memory=get_memory(),
        obsidian=get_obsidian(),
        maps=get_maps(),
    )


async def _placeholder_executor(spec: AgentSpec, prompt: str) -> RunResult:
    return RunResult(
        output=f"[placeholder {spec.type}] {prompt[:200]}",
        cost_usd=0.0,
        meta={"executor": "placeholder"},
    )


def _build_anthropic_client(api_key: str):
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.AsyncAnthropic(api_key=api_key).messages


def _build_real_executor() -> ClaudeAgentExecutor | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    client = _build_anthropic_client(s.anthropic_api_key)
    if client is None:
        return None

    from .voice import bandit
    from .voice.routing import TIER_MODELS, Tier

    def factory(agent_type: str, *, prompt: str | None = None) -> Brain:
        # Route by complexity score when we have a prompt; otherwise fall
        # back to Sonnet which is the safest default tier for unknowns.
        if prompt:
            decision = bandit.route(get_db(), prompt, agent_type=agent_type)
            model = decision.model
        else:
            model = TIER_MODELS[Tier.SONNET]
        return ClaudeBrain(
            api_key=s.anthropic_api_key,
            model=model,
            client=client,
            system=SYSTEM_PROMPTS.get(agent_type, ""),
        )

    return ClaudeAgentExecutor(
        brain_factory=factory,
        registry_factory=_registry_factory,
    )


def _build_verifier():
    """Return a Haiku-backed verifier when the API key is set, else None.

    The verifier shares the Anthropic client but always routes to Haiku
    regardless of complexity score — verification is bounded and cheap."""
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    client = _build_anthropic_client(s.anthropic_api_key)
    if client is None:
        return None
    from .agents.verifier import VERIFIER_SYSTEM, ClaudeVerifier
    from .voice.routing import TIER_MODELS, Tier

    def factory(_agent_type: str):
        return ClaudeBrain(
            api_key=s.anthropic_api_key,
            model=TIER_MODELS[Tier.HAIKU],
            client=client,
            system=VERIFIER_SYSTEM,
        )

    return ClaudeVerifier(brain_factory=factory)


def get_agents() -> AgentManager:
    global _agents
    if _agents is None:
        s = get_settings()
        executor = _build_real_executor() or _placeholder_executor
        verifier = _build_verifier()
        from .store import runs as runs_store

        def _persist(summary: dict, queued_at: float | None) -> None:
            runs_store.upsert_from_summary(get_db(), summary, queued_at=queued_at)

        _agents = AgentManager(
            executor=executor,
            max_parallel=s.max_parallel_agents,
            verifier=verifier,
            persist=_persist,
        )
        if s.auto_security_review:
            from .agents.auto_security import register_auto_security

            register_auto_security(_agents)
    return _agents


def set_agents(mgr: AgentManager | None) -> None:
    global _agents
    _agents = mgr


def get_plans() -> PlanRunner:
    """Lazily build a PlanRunner that drives the existing AgentManager."""
    global _plans
    if _plans is None:
        _plans = PlanRunner(manager=get_agents())
    return _plans


def set_plans(runner: PlanRunner | None) -> None:
    global _plans
    _plans = runner


def _build_stt() -> STT:
    s = get_settings()
    return WhisperSTT(model=s.whisper_model)


def _build_tts() -> TTS:
    s = get_settings()
    if not s.elevenlabs_api_key:
        return PiperFallbackTTS()
    return ElevenLabsTTS(
        api_key=s.elevenlabs_api_key, voice_id=s.elevenlabs_voice_id
    )


def _build_brain() -> Brain | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    client = _build_anthropic_client(s.anthropic_api_key)
    if client is None:
        return None
    from .prompts import VOICE_BRAIN_SYSTEM

    return ClaudeBrain(
        api_key=s.anthropic_api_key,
        model=s.brain_model_hot,
        client=client,
        system=VOICE_BRAIN_SYSTEM,
    )


def new_voice_session() -> VoiceSession:
    if _session_factory is not None:
        return _session_factory()
    brain = _build_brain()
    if brain is None:
        from .voice.brain import FakeBrain

        brain = FakeBrain([])
    return VoiceSession(stt=_build_stt(), brain=brain, tts=_build_tts())


def set_session_factory(factory: "callable[[], VoiceSession] | None") -> None:
    global _session_factory
    _session_factory = factory
