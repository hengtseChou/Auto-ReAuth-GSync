import click
import yaml

from push import push as pushing


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
@click.option("-s", "--source")
def pull(source):
    pass


@cli.command()
def sync():
    pass


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
