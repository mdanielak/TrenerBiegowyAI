class FieldError(ValueError):
    """Błąd walidacji powiązany z polem formularza."""

    def __init__(self, message: str, field: str):
        super().__init__(message)
        self.field = field
