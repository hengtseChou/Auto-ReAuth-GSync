import hashlib
import os
import shutil
import tqdm

import click
from pydrive2.drive import GoogleDrive

from argsync.gdrive import load_authorized_gdrive

GOOGLE_MIME_TYPES = {
    "application/vnd.google-apps.document": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ],
    # 'application/vnd.google-apps.document':
    # 'application/vnd.oasis.opendocument.text',
    "application/vnd.google-apps.spreadsheet": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ],
    # 'application/vnd.oasis.opendocument.spreadsheet',
    "application/vnd.google-apps.presentation": [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ],
    # 'application/vnd.oasis.opendocument.presentation'
}


def get_target_folder_id(src_full_path: str, drive: GoogleDrive) -> str:

    if src_full_path == "gdrive:":
        return "root"

    src_folder_list = src_full_path.split(":")[1].rstrip("/").split("/")
    src_parents_id = []
    for src in src_folder_list:
        if not src_parents_id:
            items = drive.ListFile(
                {"q": "'root' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"}
            ).GetList()
            if src in [item["title"] for item in items]:
                new_folder_id = [item["id"] for item in items if item["title"] == src][0]
            else:
                return None
        else:
            items = drive.ListFile(
                {
                    "q": f"'{src_parents_id[-1]}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
                }
            ).GetList()
            if src in [item["title"] for item in items]:
                new_folder_id = [item["id"] for item in items if item["title"] == src][0]
            else:
                return None
        src_parents_id.append(new_folder_id)
    return src_parents_id[-1]


def get_tree(folder_name, tree_list, root, parents_id, drive: GoogleDrive):
    """Gets folder tree relative paths.

    Recursively gets through subfolders, remembers their names ad ID's.

    Args:
        folder_name: Name of folder, initially
        name of parent folder string.
        folder_id: ID of folder, initially ID of parent folder.
        tree_list: List of relative folder paths, initially
        empy list.
        root: Current relative folder path, initially empty string.
        parents_id: Dictionary with pairs of {key:value} like
        {folder's name: folder's Drive ID}, initially empty dict.
        service: Google Drive service instance.

    Returns:
        List of folder tree relative folder paths.

    """
    folder_id = parents_id[folder_name]
    items = drive.ListFile(
        {"q": f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"}
    ).GetList()
    root += folder_name + os.path.sep

    for item in items:
        parents_id[item["title"]] = item["id"]
        tree_list.append(root + item["title"])
        folder_id = [i["id"] for i in items if i["title"] == item["title"]][0]
        folder_name = item["title"]
        get_tree(folder_name, tree_list, root, parents_id, drive)


def download_file_from_gdrive(file_dir, drive_file, drive: GoogleDrive):
    """Downloads file from Google Drive.

    If file is Google Doc's type, then it will be downloaded
    with the corresponding non-Google mimetype.

    Args:
        path: Directory string, where file will be saved.
        file: File information object (dictionary), including it's name, ID
        and mimeType.
        service: Google Drive service instance.
    """
    file_id = drive_file["id"]
    file_name = drive_file["title"]

    file_download = drive.CreateFile({"id": file_id})

    if drive_file["mimeType"] in GOOGLE_MIME_TYPES.keys():
        if file_name.endswith(GOOGLE_MIME_TYPES[drive_file["mimeType"]][1]):
            file_name = drive_file["title"]
        else:
            file_name = "{}{}".format(drive_file["title"], GOOGLE_MIME_TYPES[drive_file["mimeType"]][1])
            file_download["title"] = file_name
        file_download["mimeType"] = GOOGLE_MIME_TYPES[drive_file["mimeType"]][0]

    file_download.GetContentFile(os.path.join(file_dir, file_name))


def by_lines(input_str):
    """Helps Sort items by the number of slashes in it.

    Returns:
        Number of slashes in string.
    """
    return input_str.count(os.path.sep)


def pull(src_full_path, dest_dir):
    """Pull files from Google Drive."""
    # credentials = get_credentials()
    drive = load_authorized_gdrive()

    # Get id of Google Drive folder and it's path (from other script)
    # folder_id, full_path = initial_upload.check_upload(service)
    print("Pull started.")
    folder_id = get_target_folder_id(src_full_path, drive)
    if folder_id is None:
        raise click.BadParameter(f"{src_full_path} cannot be found.")
    if not os.path.exists(dest_dir) and os.path.isdir(dest_dir):
        raise click.BadParameter(f"{dest_dir} is not a valid directory.")
    folder_name = src_full_path.split(":")[1].rstrip("/").split("/")[-1]
    if not os.path.exists(os.path.join(dest_dir, folder_name)):
        os.mkdir(os.path.join(dest_dir, folder_name))
    tree_list, root, parents_id = [], "", {}

    print("Comparing gdrive to local stroage...")
    parents_id[folder_name] = folder_id
    get_tree(folder_name, tree_list, root, parents_id, drive)
    os_tree_list = []
    dest_full_path = os.path.join(dest_dir, folder_name)
    root_len = len(dest_full_path.split(os.path.sep)[0:-2])

    # Get list of folders three paths on computer
    for root, dirs, files in os.walk(dest_full_path, topdown=True):
        for name in dirs:
            var_path = (os.path.sep).join(root.split(os.path.sep)[root_len + 1 :])
            os_tree_list.append(os.path.join(var_path, name))

    # old folders on computer
    download_folders = list(set(tree_list).difference(set(os_tree_list)))
    # new folders on computer, which you dont have(i suppose heh)
    remove_folders = list(set(os_tree_list).difference(set(tree_list)))
    # foldes that match
    exact_folders = list(set(os_tree_list).intersection(set(tree_list)))

    exact_folders.append(folder_name)

    parent_folder = (os.path.sep).join(dest_full_path.split(os.path.sep)[0:-1]) + os.path.sep

    # Download folders from Drive
    download_folders = sorted(download_folders, key=by_lines)

    print("Downloading new folders...")
    for folder_dir in tqdm.tqdm(download_folders, disable=(len(download_folders) == 0)):
        folder = parent_folder + folder_dir
        last_dir = folder_dir.split(os.path.sep)[-1]

        folder_id = parents_id[last_dir]
        items = drive.ListFile({"q": f"'{folder_id}' in parents and trashed = false"}).GetList()
        os.makedirs(folder)
        files = [f for f in items if f["mimeType"] != "application/vnd.google-apps.folder"]

        for drive_file in files:
            download_file_from_gdrive(folder, drive_file, drive)

    # Check and refresh files in existing folders
    print("Updating existing folders...")
    for folder_dir in tqdm.tqdm(exact_folders, disable=(len(exact_folders) == 0)):

        folder = parent_folder + folder_dir
        last_dir = folder_dir.split(os.path.sep)[-1]
        os_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        folder_id = parents_id[last_dir]

        items = drive.ListFile(
            {"q": f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"}
        ).GetList()

        refresh_files = [f for f in items if f["title"] in os_files]
        upload_files = [f for f in items if f["title"] not in os_files]
        remove_files = [f for f in os_files if f not in [j["title"] for j in items]]

        for drive_file in refresh_files:
            file_dir = os.path.join(folder, drive_file["title"])

            drive_md5 = drive_file["md5Checksum"]
            os_file_md5 = hashlib.md5(open(file_dir, "rb").read()).hexdigest()

            if drive_md5 != os_file_md5:
                os.remove(os.path.join(folder, drive_file["title"]))
                download_file_from_gdrive(folder, drive_file, drive)

        for os_file in remove_files:
            os.remove(os.path.join(folder, os_file))

        for drive_file in upload_files:
            download_file_from_gdrive(folder, drive_file, drive)

    # Delete old and unwanted folders from computer
    remove_folders = sorted(remove_folders, key=by_lines, reverse=True)

    print("Deleting unwanted folders...")
    for folder_dir in tqdm.tqdm(remove_folders, disable=(len(remove_folders) == 0)):
        folder = parent_folder + folder_dir
        last_dir = folder_dir.split(os.path.sep)[-1]
        shutil.rmtree(folder)
    print("Pull completed.")
