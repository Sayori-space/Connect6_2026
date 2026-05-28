from ai.alpha_beta_ai import AlphaBetaAI
from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from ai.alpha_belta_plus_ai import AlphaBeltaPlusAI


def _with_think_time(ai, config):
    if hasattr(config, "ai_think_time_seconds"):
        ai.think_time_seconds = config.ai_think_time_seconds
    return ai


def build_ai(config):
    """Create an AI instance for a game config."""
    if config.ai_type == "alpha_belta_max":
        return _with_think_time(AlphaBeltaMaxAI(), config)
    if config.ai_type == "alpha_belta_plus":
        return _with_think_time(AlphaBeltaPlusAI(), config)
    return _with_think_time(AlphaBetaAI(), config)
