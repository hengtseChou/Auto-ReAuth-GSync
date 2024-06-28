import click
import yaml
import os

from push import push as pushing
from pull import pull as pulling


@click.group()
def cli():
    pass


@cli.command()
@click.argument("src", type=click.Path(exists=True))
@click.option("-d", "--dest", default=None)
def push(src, dest):
    if dest is None:
        dest = "gdrive:"
    pushing(src, dest)


@cli.command()
@click.argument("src")
@click.option("-d", "--dest", default=None, type=click.Path(exists=True))
def pull(src, dest):
    if dest is None:
        dest = os.path.expanduser("~")
    pulling(src, dest)


@cli.command()
def remove_profile():
    if os.path.exists("credentials.json"):
        os.remove("credentials.json")
        print("Profile removed successfully.")
    else:
        print("No profile found.")


@cli.command()
def setup():
    client_id = click.prompt("Please enter your client id", type=str)
    client_secret = click.prompt("client secret", type=str, hide_input=True)

    settings_yaml = {
        "client_config_backend": "settings",
        "client_config": {"client_id": client_id, "client_secret": client_secret},
        "save_credentials": True,
        "save_credentials_backend": "file",
        "save_credentials_file": "credentials.json",
        "get_refresh_token": True,
        "oauth_scope": ["https://www.googleapis.com/auth/drive"],
    }
    with open("settings.yaml", "w") as f:
        yaml.dump(settings_yaml, f, default_flow_style=False)
    print("Setup complete.")


if __name__ == "__main__":
    cli()
