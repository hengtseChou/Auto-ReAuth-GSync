import os
import pathlib
import re
import warnings

import click
import yaml

from argsync.pull import pull as pulling
from argsync.push import push as pushing


def is_valid_gdrive_path(path: str) -> bool:
    pattern = r"^gdrive:([a-zA-Z0-9 _\.\-\u4E00-\u9FFF]*)$"
    return bool(re.match(pattern, path))


@click.group()
def cli():
    warnings.filterwarnings("ignore")


@cli.command()
@click.argument("src", type=click.Path(exists=True))
@click.option("-d", "--dest", default=None, help="Push into this gdrive folder.")
def push(src, dest):
    """Push to gdrive folder."""
    settings_path = pathlib.Path(__file__).parent / "settings.yaml"
    if not os.path.exists(settings_path):
        raise click.ClickException("Google Drive API not setup. Please run `argsync setup` to resolve it.")
    if dest is None:
        dest = "gdrive:"
    if not is_valid_gdrive_path(dest):
        raise click.BadParameter("The path to Google Drive folder should be like `gdrive:path/to/folder`.")
    pushing(src, dest)


@cli.command()
@click.argument("src")
@click.option("-d", "--dest", default=None, type=click.Path(exists=True), help="Pull folder to this directory.")
def pull(src, dest):
    """Pull from gdrive folder."""
    settings_path = pathlib.Path(__file__).parent / "settings.yaml"
    if not os.path.exists(settings_path):
        raise click.ClickException("Google Drive API not setup. Please run `argsync setup` to resolve it.")
    if not is_valid_gdrive_path(src):
        raise click.BadParameter("The path to Google Drive folder should be like `gdrive:path/to/folder`.")
    if dest is None:
        dest = os.path.expanduser("~")
    pulling(src, dest)


@cli.command()
def remove_profile():
    """Remove user's credentials."""

    creds = pathlib.Path(__file__).parent / "credentials.json"

    if os.path.exists(creds):
        os.remove(creds)
        print("Profile removed successfully.")
    else:
        print("No profile found.")


@cli.command()
def setup():
    """Setup Google Drive API."""
    settings_path = pathlib.Path(__file__).parent / "settings.yaml"
    if os.path.exists(settings_path):
        click.confirm("Setup file exists. Overwrite?", abort=True)

    client_id = click.prompt("Please enter your client id", type=str)
    client_secret = click.prompt("client secret", type=str, hide_input=True)

    settings_yaml = {
        "client_config_backend": "settings",
        "client_config": {"client_id": client_id, "client_secret": client_secret},
        "save_credentials": True,
        "save_credentials_backend": "file",
        "save_credentials_file": str(pathlib.Path(__file__).parent / "credentials.json"),
        "get_refresh_token": True,
        "oauth_scope": ["https://www.googleapis.com/auth/drive"],
    }
    settings_path = pathlib.Path(__file__).parent / "settings.yaml"
    with open(settings_path, "w") as f:
        yaml.dump(settings_yaml, f, default_flow_style=False)
    print("Setup complete.")


if __name__ == "__main__":
    cli()
