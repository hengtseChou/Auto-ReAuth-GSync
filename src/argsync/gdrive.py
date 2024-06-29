import pathlib

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


def load_authorized_gdrive() -> GoogleDrive:

    creds = pathlib.Path(__file__).parent / "credentials.json"
    settings = pathlib.Path(__file__).parent / "settings.yaml"

    gauth = GoogleAuth(settings_file=settings)
    # Try to load saved client credentials
    gauth.LoadCredentialsFile(creds)
    if gauth.credentials is None:
        # Authenticate if they're not there
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        # Refresh them if expired
        gauth.Refresh()
    else:
        # Initialize the saved creds
        gauth.Authorize()
    # Save the current credentials to a file
    gauth.SaveCredentialsFile(creds)

    return GoogleDrive(gauth)
