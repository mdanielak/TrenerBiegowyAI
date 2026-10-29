# -*- coding: utf-8 -*-
"""
Daily training recommendation via AI.

Generates a structured recommendation based on training context.
NO automatic workout sending — recommendation only.
"""
from pydantic import BaseModel, Field
from typing import Optional

from ai.base import AIProvider
from ai.context import format_context_for_user


class DailyRecommendation(BaseModel):
    """Structured daily training recommendation from AI coach."""

    readiness: str = Field(
        description="ready | ready_with_reserves | not_ready"
    )
    recommendation: str = Field(
        description="Natural language training recommendation for today"
    )
    planned_workout: Optional[str] = Field(
        default=None,
        description="Specific workout to do today (if adjustment needed)"
    )
    adjustment_needed: bool = Field(
        description="Whether today's planned workout should be modified"
    )
    reasoning_summary: str = Field(
        description="Brief explanation of why this recommendation"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Any warnings (HRV, fatigue, overtraining risk, etc.)"
    )


RECOMMENDATION_USER_PROMPT = """Na podstawie poniższych danych o treningu i stanie zdrowia,
przygotuj rekomendację na dzisiejszy dzień.

Odpowiedz WYŁĄCZNIE w formacie JSON z polami:
- readiness: "ready" | "ready_with_reserves" | "not_ready"
- recommendation: krótka rekomendacja naturalnym językiem (po polsku)
- planned_workout: jeśli zalecasz zmianę planu, opisz jaki trening wykonać (lub null)
- adjustment_needed: true jeśli dzisiejszy plan wymaga zmiany
- reasoning_summary: krótkie uzasadnienie (1-2 zdania)
- warnings: lista ostrzeżeń (pusta jeśli brak)

Uwzględnij:
- aktualny stan HRV i ewentualne alerty
- jakość snu i poziom stresu
- obciążenie tygodniowe
- trendy z ostatnich treningów
- zaplanowany trening na dziś
- wiadomość od biegacza, jeśli jest: uwzględnij życzenia, o ile nie przeczą zdrowiu i regeneracji;
  ból i objawy z dziennika mają pierwszeństwo

Bądź konkretny ale ostrożny — priorytetem jest zdrowie i regeneracja.
Pisz dla osoby nietechnicznej: bez angielskich kodów z danych (LOW, UNBALANCED, RHR, score) —
„HRV niskie”, „tętno spoczynkowe”, „ocena snu” — i bez form zależnych od płci."""


def get_daily_recommendation(provider: AIProvider, context: dict) -> DailyRecommendation:
    """Generate daily training recommendation via AI.

    Args:
        provider: AI provider instance (e.g. OpenAICompatibleProvider).
        context: Training context from build_training_context().

    Returns:
        DailyRecommendation with structured recommendation.

    Raises:
        AIProviderError: On API errors.
        AIResponseError: If AI response cannot be parsed/validated.
    """
    system_prompt = context.get("system_prompt", "")
    user_message = format_context_for_user(context)

    return provider.chat(
        system_prompt=system_prompt,
        user_message=RECOMMENDATION_USER_PROMPT + "\n\n" + user_message,
        response_model=DailyRecommendation,
    )
