"""Autoriza o AgendaBot a usar o Google Agenda (OAuth2).

1. No Google Cloud Console, ative a "Google Calendar API".
2. Em APIs e serviços > Credenciais, crie um "ID do cliente OAuth" do tipo
   "App para computador" e baixe o JSON como `credentials.json` na raiz do projeto.
3. Rode:  python scripts/autorizar_google.py
4. Faça login com a conta da clínica. Um arquivo `token.json` será criado.
   Ele contém o refresh token, e o bot renova o acesso sozinho depois disso.

Nunca suba `credentials.json` nem `token.json` para o GitHub (já estão no .gitignore).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.json", "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print("token.json criado. Agora defina CALENDAR_PROVIDER=google no .env.")


if __name__ == "__main__":
    main()
