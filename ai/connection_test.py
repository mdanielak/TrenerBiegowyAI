"""Jednorazowy test Chat Completions bez profilu i danych treningowych."""
from openai import (
    APIConnectionError, APIStatusError, APITimeoutError, DefaultHttpxClient, OpenAI,
)


class AIConnectionTestError(Exception):
    """Bezpieczny komunikat dla użytkownika, bez odpowiedzi dostawcy i sekretów."""


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
            400: "API odrzuciło żądanie. Sprawdź model i obsługę Chat Completions.",
            401: "API odrzuciło klucz. Sprawdź klucz API.",
            403: "Brak uprawnień do API lub wybranego modelu.",
            404: "Nie znaleziono modelu lub endpointu. Sprawdź adres API i nazwę modelu.",
            429: "Limit zapytań lub środków u dostawcy. Spróbuj później lub sprawdź rozliczenia.",
        }
        raise AIConnectionTestError(messages.get(
            exc.status_code, "API zwróciło błąd. Sprawdź dostępność dostawcy i konfigurację."
        )) from None
    except Exception:
        # Nie pokazuj str(exc): SDK/dostawca może w nim umieścić klucz lub treść odpowiedzi.
        raise AIConnectionTestError("Nie udało się przetestować API. Sprawdź zgodność z Chat Completions.") from None
