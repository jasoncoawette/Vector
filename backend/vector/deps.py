from __future__ import annotations

import sqlite3
from pathlib import Path

from .agents import AgentManager
from .agents.executor import SYSTEM_PROMPTS, ClaudeAgentExecutor
from .agents.types import AgentSpec, RunResult
from .config import get_settings
from .store import connect
from .voice.brain import Brain, ClaudeBrain
from .voice.session import VoiceSession
from .voice.stt import STT, FakeSTT, WhisperSTT
from .voice.tts import TTS, ElevenLabsTTS, PiperFallbackTTS

_conn: sqlite3.Connection | None = None
_agents: AgentManager | None = None
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

    return ClaudeAgentExecutor(brain_factory=factory, registry=None)


def get_agents() -> AgentManager:
    global _agents
    if _agents is None:
        s = get_settings()
        executor = _build_real_executor() or _placeholder_executor
        _agents = AgentManager(executor=executor, max_parallel=s.max_parallel_agents)
    return _agents


def set_agents(mgr: AgentManager | None) -> None:
    global _agents
    _agents = mgr


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
    return ClaudeBrain(
        api_key=s.anthropic_api_key,
        model=s.brain_model_hot,
        client=client,
        system=(
            "You are Vector, Jason's local voice assistant. "
            "Reply in one or two sentences unless asked for more."
        ),
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
