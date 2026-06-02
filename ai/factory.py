from ai.alpha_beta_ai import AlphaBetaAI
from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from ai.alpha_belta_plus_ai import AlphaBeltaPlusAI
from ai.ab_kata_ai import ABKataAI
from ai.kata_gomo_ai import KataGomoAI


def _with_think_time(ai, config):
    if hasattr(config, "ai_think_time_seconds"):
        ai.total_think_time_seconds = config.ai_think_time_seconds
    return ai


def build_ai(config):
    """根据游戏配置创建 AI 实例。"""
    if config.ai_type == "kata_gomo":
        return _with_think_time(KataGomoAI(), config)
    if config.ai_type == "ab_kata":
        return _with_think_time(ABKataAI(), config)
    if config.ai_type == "alpha_belta_max":
        return _with_think_time(AlphaBeltaMaxAI(), config)
    if config.ai_type == "alpha_belta_plus":
        return _with_think_time(AlphaBeltaPlusAI(), config)
    return _with_think_time(AlphaBetaAI(), config)
