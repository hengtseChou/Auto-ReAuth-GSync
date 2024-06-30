# Auto-ReAuth-GSync

A google drive sync tool that does not requires re-authorize.

Some of the code was inspired by the [Google-Drive-sync](https://github.com/dtsvetkov1/Google-Drive-sync) project and refactored with PyDrive2 packages.

# Installation

It is recommanded to use pipx for an isolated environment.

```
pipx install argsync
```

# Setup

1. Enable a Google Drive API over [GCP](https://console.cloud.google.com) and retrieve client id and client secret. Make sure you include the account you want to link with this tool when adding user for your API.
2. Run `argsync setup`, and input your client id and client secret. 
3. When first time running `argsync push` or `argsync pull`, your will be redirected to authorization page. And that's it. From now on, the tool will refresh the credentials automatically. 
4. To switch for different account, run `argsync remove-profile` to remove the credentials and re-authorize with another account.

# Disclaimer

This project is not widely tested. Some issues might occur. Anyone is welcomed to contribute.
