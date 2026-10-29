"""Jednorazowy test Chat Completions bez profilu i danych treningowych."""
import json

from openai import (
    APIConnectionError, APIStatusError, APITimeoutError, DefaultHttpxClient, OpenAI,
)


class AIConnectionTestError(Exception):
    """Bezpieczny komunikat dla użytkownika, bez odpowiedzi dostawcy i sekretów."""


# Znane przyczyny rozpoznawane po kodach w odpowiedzi; treści dostawcy nie pokazujemy,
# bo może zawierać prywatne dane — tylko własny komunikat.
_KNOWN_REASONS = (
    (("API_KEY_INVALID", "API key not valid"),
     "Klucz API jest nieprawidłowy. Skopiuj go ponownie, bez spacji, i zapisz."),
    (("location is not supported", "FAILED_PRECONDITION"),
     "Dostawca nie obsługuje tego regionu albo konta. Sprawdź warunki w panelu dostawcy."),
)


def known_reason(exc) -> str | None:
    """Własny opis znanej przyczyny błędu albo None."""
    text = json.dumps(getattr(exc, "body", None), ensure_ascii=False, default=str)
    for markers, message in _KNOWN_REASONS:
        if any(marker in text for marker in markers):
            return message
    return None


def check_connection(*, base_url: str, api_key: str, model: str) -> None:
    """Sprawdź autoryzację i wybrany model; nie zapisuj odpowiedzi modelu."""
    try:
        with DefaultHttpxClient(follow_redirects=False) as http_client:
            with OpenAI(base_url=base_url, api_key=api_key, timeout=20.0,
                        max_retries=0, http_client=http_client) as client:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Connection test. Reply only OK."}],
                )
                if not response.choices or not response.choices[0].message.content:
                    raise AIConnectionTestError("API odpowiedziało, ale model nie zwrócił tekstu.")
    except AIConnectionTestError:
        raise
    except APITimeoutError:
        raise AIConnectionTestError("Przekroczono czas oczekiwania na API (20 s).") from None
    except APIConnectionError:
        raise AIConnectionTestError("Nie można połączyć się z API. Sprawdź adres, sieć i certyfikat TLS.") from None
    except APIStatusError as exc:
        messages = {
            # Gemini zgłasza nieprawidłowy klucz jako 400, nie 401.
            400: "API odrzuciło żądanie. Najczęściej to nieprawidłowy klucz albo zła nazwa modelu.",
            401: "API odrzuciło klucz. Sprawdź klucz API.",
            402: "Brak środków na koncie u dostawcy AI. Doładuj konto albo wybierz darmową opcję (Gemini).",
            403: "Brak uprawnień do API lub wybranego modelu.",
            404: "Nie znaleziono modelu lub endpointu. Sprawdź adres API i nazwę modelu.",
            429: "Limit zapytań lub środków u dostawcy. Spróbuj później lub sprawdź rozliczenia.",
        }
        raise AIConnectionTestError(known_reason(exc) or messages.get(
            exc.status_code, "API zwróciło błąd. Sprawdź dostępność dostawcy i konfigurację."
        )) from None
    except Exception:
        # Nie pokazuj str(exc): SDK/dostawca może w nim umieścić klucz lub treść odpowiedzi.
        raise AIConnectionTestError("Nie udało się przetestować API. Sprawdź zgodność z Chat Completions.") from None
