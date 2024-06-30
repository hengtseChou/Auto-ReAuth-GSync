import hashlib
import os
import pathlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, List, Tuple

import click
import tqdm
from pydrive2.drive import GoogleDrive, GoogleDriveFile

from argsync.gdrive import load_authorized_gdrive

GOOGLE_MIME_TYPES = {
    "application/vnd.google-apps.document": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ],
    "application/vnd.google-apps.spreadsheet": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ],
    "application/vnd.google-apps.presentation": [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ],
}


def list_folders(parents_id: str, drive: GoogleDrive) -> List[GoogleDriveFile]:
    """
    Lists all folders in the specified Google Drive directory.

    Args:
        parents_id (str): The ID of the parent directory in Google Drive.
        drive (GoogleDrive): An instance of the GoogleDrive class.

    Returns:
        list: A list of Google Drive file objects representing folders.
    """
    return drive.ListFile(
        {"q": f"'{parents_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"}
    ).GetList()


def list_files(parents_id: str, drive: GoogleDrive) -> List[GoogleDriveFile]:
    """
    Lists all files in the specified Google Drive directory excluding folders.

    Args:
        parents_id (str): The ID of the parent directory in Google Drive.
        drive (GoogleDrive): An instance of the GoogleDrive class.

    Returns:
        list: A list of Google Drive file objects representing files.
    """
    return drive.ListFile(
        {"q": f"'{parents_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'"}
    ).GetList()


def get_target_folder_id(src_full_path: str, drive: GoogleDrive) -> str:
    """
    Retrieves the Google Drive folder ID based on the given path.

    Args:
        src_full_path (str): The full path in Google Drive, formatted as 'gdrive:path/to/folder'.
        drive (GoogleDrive): An instance of the GoogleDrive class.

    Returns:
        str or None: The folder ID if found, otherwise None.
    """
    if src_full_path == "gdrive:":
        return "root"

    src_folder_list = src_full_path.split(":")[1].rstrip("/").split("/")
    src_parents_id = []
    for src in src_folder_list:
        if not src_parents_id:
            items = list_folders("root", drive)
            if src in [item["title"] for item in items]:
                new_folder_id = [item["id"] for item in items if item["title"] == src][0]
            else:
                return None
        else:
            items = list_folders(src_parents_id[-1], drive)
            if src in [item["title"] for item in items]:
                new_folder_id = [item["id"] for item in items if item["title"] == src][0]
            else:
                return None
        src_parents_id.append(new_folder_id)
    return src_parents_id[-1]


def file_download(args: Tuple[str, GoogleDriveFile, GoogleDrive]) -> None:
    """
    Downloads a file from Google Drive and handles different types based on their MIME type.

    Args:
        args (tuple): A tuple containing the path where the file will be saved, the file information, and the Google Drive service instance.
    """
    file_dir, drive_file, drive = args
    file_id = drive_file["id"]
    file_name = drive_file["title"]

    file = drive.CreateFile({"id": file_id})

    if drive_file["mimeType"] in GOOGLE_MIME_TYPES.keys():
        if file_name.endswith(GOOGLE_MIME_TYPES[drive_file["mimeType"]][1]):
            file_name = drive_file["title"]
        else:
            file_name = "{}{}".format(drive_file["title"], GOOGLE_MIME_TYPES[drive_file["mimeType"]][1])
            file["title"] = file_name
        file["mimeType"] = GOOGLE_MIME_TYPES[drive_file["mimeType"]][0]

    file.GetContentFile(os.path.join(file_dir, file_name))


def progress_bar_with_threading_executor(fn: Callable, iterable: Iterable[Tuple], desc: str) -> None:
    """
    Executes a function over an iterable with a progress bar, using multiple threads.

    Args:
        fn (function): The function to apply to each item in the iterable.
        iterable (iterable): An iterable where each item will be processed by the function.
        desc (str): Description text for the progress bar.
    """
    disable_pbar = len(iterable) == 0

    with tqdm.tqdm(total=len(iterable), desc=desc, disable=disable_pbar) as progress:
        with ThreadPoolExecutor(max_workers=5) as executor:
            for _ in executor.map(fn, iterable):
                progress.update()


def get_tree(folder_name: str, tree_list: List[str], root: str, parents_id: str, drive: GoogleDrive) -> None:
    """
    Recursively builds a list of all folder paths under a specified Google Drive folder.

    Args:
        folder_name (str): The name of the starting folder.
        tree_list (list): Accumulator for storing folder paths.
        root (str): Current path prefix.
        parents_id (dict): A dictionary mapping folder names to their Google Drive IDs.
        drive (GoogleDrive): An instance of the GoogleDrive class.

    Returns:
        None. It will modify tree_list that was passed in.
    """
    folder_id = parents_id[root + folder_name]
    items = list_folders(folder_id, drive)
    root += folder_name + os.path.sep

    for item in items:
        parents_id[root + item["title"]] = item["id"]
        tree_list.append(root + item["title"])
        folder_id = [i["id"] for i in items if i["title"] == item["title"]][0]
        folder_name = item["title"]
        get_tree(folder_name, tree_list, root, parents_id, drive)


def by_lines(input_str: str) -> int:
    """
    Returns the count of slashes in a string, used for sorting paths.

    Args:
        input_str (str): The string to count slashes in.

    Returns:
        int: The number of slashes in the input string.
    """
    return input_str.count(os.path.sep)


def pull(src_full_path: str, dest_dir: str) -> None:
    """
    Synchronizes a local directory with the contents of a Google Drive directory.

    Args:
        src_full_path (str): The Google Drive path to synchronize, formatted as 'gdrive:path/to/directory'.
        dest_dir (str): The local directory path where files will be synchronized to.

    Raises:
        click.BadParameter: If the specified paths are not valid or not found.
    """
    drive = load_authorized_gdrive()

    # Get id of Google Drive folder and it's path (from other script)
    # folder_id, full_path = initial_upload.check_upload(service)
    print("Pull started.")
    folder_id = get_target_folder_id(src_full_path, drive)
    if folder_id is None:
        raise click.BadParameter(f"{src_full_path} cannot be found.")
    folder_name = src_full_path.split(":")[1].rstrip("/").split("/")[-1]
    if not os.path.exists(os.path.join(dest_dir, folder_name)):
        os.mkdir(os.path.join(dest_dir, folder_name))
    tree_list, root, parents_id = [], "", {}

    print("Comparing gdrive to local stroage...")
    parents_id[folder_name] = folder_id
    get_tree(folder_name, tree_list, root, parents_id, drive)
    local_tree_list = []
    dest_full_path = os.path.join(dest_dir, folder_name)
    root_len = len(dest_full_path.split(os.path.sep)[0:-2])

    # Get list of folders three paths on computer
    for root, dirs, files in os.walk(dest_full_path, topdown=True):
        for name in dirs:
            var_path = (os.path.sep).join(root.split(os.path.sep)[root_len + 1 :])
            local_tree_list.append(os.path.join(var_path, name))

    # old folders on computer
    download_folders = list(set(tree_list).difference(set(local_tree_list)))
    # new folders on computer, which you dont have(i suppose heh)
    remove_folders = list(set(local_tree_list).difference(set(tree_list)))
    # foldes that match
    exact_folders = list(set(local_tree_list).intersection(set(tree_list)))

    exact_folders.append(folder_name)

    parent_folder = pathlib.Path(dest_full_path).parent.resolve()

    # Download folders from Drive
    download_folders = sorted(download_folders, key=by_lines)

    for folder_dir in download_folders:

        folder = os.path.join(parent_folder, folder_dir)
        os.makedirs(folder)
        print(f"Created new folder {folder}")
        last_dir = pathlib.Path(folder_dir)
        folder_id = parents_id[str(last_dir)]
        files = list_files(folder_id, drive)

        download_tasks = []
        for drive_file in files:
            download_tasks.append((folder, drive_file, drive))
        progress_bar_with_threading_executor(file_download, download_tasks, f"Downloading files to {folder}")

    # Check and refresh files in existing folders
    for folder_dir in exact_folders:

        folder = os.path.join(parent_folder, folder_dir)
        last_dir = pathlib.Path(folder_dir)
        folder_id = parents_id[str(last_dir)]
        local_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]

        items = list_files(folder_id, drive)

        download_files = [f for f in items if f["title"] not in local_files]
        update_files = [f for f in items if f["title"] in local_files]
        remove_files = [f for f in local_files if f not in [i["title"] for i in items]]

        download_tasks = []
        for drive_file in download_files:
            download_tasks.append((folder, drive_file, drive))
        progress_bar_with_threading_executor(file_download, download_tasks, f"Downloading files to {folder}")

        update_tasks = []
        for drive_file in update_files:

            file_dir = os.path.join(folder, drive_file["title"])
            drive_md5 = drive_file["md5Checksum"]
            os_file_md5 = hashlib.md5(open(file_dir, "rb").read()).hexdigest()

            if drive_md5 != os_file_md5:
                os.remove(os.path.join(folder, drive_file["title"]))
                update_tasks.append((folder, drive_file, drive))
        progress_bar_with_threading_executor(file_download, update_tasks, f"Downloading files to {folder}")

        for local_file in tqdm.tqdm(
            remove_files, disable=(len(remove_files) == 0), desc=f"Removing files from {folder}"
        ):
            os.remove(os.path.join(folder, local_file))

    # Delete old and unwanted folders from computer
    remove_folders = sorted(remove_folders, key=by_lines, reverse=True)

    for folder_dir in tqdm.tqdm(remove_folders, disable=(len(remove_folders) == 0), desc=f"Deleting unwanted folders"):
        folder = os.path.join(parent_folder, folder_dir)
        shutil.rmtree(folder)
    print("Pull completed.")
