"""Kontrakt API — wejście i wyjście REST-a."""

from pydantic import BaseModel, Field


class CreateSessionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Login i hasło są opcjonalne, bo zalogowany administrator przychodzi
    # z tokenem panelu w nagłówku — nie ma powodu pytać go o to drugi raz.
    login: str | None = Field(default=None, max_length=40)
    password: str | None = None
    host_name: str = Field(default="Host", min_length=1, max_length=40)


class JoinIn(BaseModel):
    display_name: str = Field(default="", max_length=40)
    # Token z localStorage. Jeśli pasuje do tej sesji, ma pierwszeństwo przed
    # nickiem — to jest ścieżka powrotu po utracie łączności.
    token: str | None = None


class PromoteIn(BaseModel):
    """Awans gościa na admina — konto administratora, także z telefonu.

    `token` to tożsamość uczestnika w sesji. Konto podaje się loginem
    i hasłem albo tokenem panelu w nagłówku, jeśli jest się już zalogowanym.
    """

    token: str
    login: str | None = Field(default=None, max_length=40)
    password: str | None = None
    is_voting: bool = False


class IdentityOut(BaseModel):
    code: str
    token: str
    participant_id: int
    display_name: str
    role: str
    is_voting: bool


class SessionInfoOut(BaseModel):
    """Minimum potrzebne ekranowi dołączania, bez ujawniania składu sesji."""

    code: str
    name: str
    status: str
    status_label: str
    is_active: bool
    participants: int
