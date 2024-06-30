import hashlib
import mimetypes
import os
import pathlib
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Tuple

import tqdm
from pydrive2.drive import GoogleDrive, GoogleDriveFile

from argsync.gdrive import load_authorized_gdrive


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
        {"q": f"'{parents_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"}
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
        {"q": f"'{parents_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"}
    ).GetList()


def create_empty_folder(folder_name: str, parents_id: str, drive: GoogleDrive) -> str:
    """
    Creates a new folder in Google Drive under a specified parent directory.

    Args:
        folder_name (str): The name of the folder to create.
        parents_id (str): The ID of the parent directory under which the folder will be created.
        drive (GoogleDrive): An instance of the GoogleDrive class.

    Returns:
        str: The ID of the newly created folder.
    """
    folder_metadata = {
        "title": folder_name,
        "parents": [{"id": parents_id}],
        "mimeType": "application/vnd.google-apps.folder",
    }

    new_folder = drive.CreateFile(folder_metadata)
    new_folder.Upload()
    folder_id = new_folder["id"]

    return folder_id


def new_folder_upload(
    src_full_path: str, target_parents_id: str, drive: GoogleDrive, ignore_dirs: Tuple[str], num_of_uploader: int
) -> None:
    """
    Recursively uploads a folder and its content to Google Drive if it does not already exist.

    Args:
        src_full_path (str): The local path of the source folder to upload.
        target_parents_id (str): The ID of the target parent folder on Google Drive.
        drive (GoogleDrive): An instance of the GoogleDrive class.
        ignore_dirs (list): A list of directory names to ignore during upload.
    """
    parents_id = {}

    for root, dirs, files in os.walk(src_full_path, topdown=True):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        last_dir = pathlib.Path(root)
        pre_last_dir = pathlib.Path(root).parent
        if str(pre_last_dir) not in parents_id:
            pre_last_dir = target_parents_id
        else:
            pre_last_dir = parents_id[str(pre_last_dir)]

        folder_id = create_empty_folder(last_dir.name, str(pre_last_dir), drive)

        upload_tasks = []
        for name in files:
            file_metadata = {
                "title": name,
                "parents": [{"id": folder_id}],
                "mimeType": mimetypes.MimeTypes().guess_type(name)[0] or "application/octet-stream",
            }
            upload_tasks.append((file_metadata, os.path.join(root, name), drive))
        progress_bar_with_threading_executor(file_upload, upload_tasks, f"Uploading files from {root}", num_of_uploader)

        parents_id[str(last_dir)] = folder_id


def get_dest_dir_id(dest_dir: str, drive: GoogleDrive) -> str:
    """
    Determines the Google Drive folder ID for a specified path, creating folders as needed.

    Args:
        dest_dir (str): The Google Drive path where the folders should be checked or created.
        drive (GoogleDrive): An instance of the GoogleDrive class.

    Returns:
        str: The Google Drive folder ID corresponding to the specified path.
    """
    dest_dir_id = "root"

    if dest_dir != "gdrive:":
        dest_folder_list = dest_dir.split(":")[1].rstrip(os.path.sep).split(os.path.sep)
        dest_parents_id = []

        for dest in dest_folder_list:
            if not dest_parents_id:
                items = list_folders("root", drive)
                if dest in [item["title"] for item in items]:
                    new_folder_id = [item["id"] for item in items if item["title"] == dest][0]

                else:
                    new_folder_id = create_empty_folder(dest, "root", drive)

            else:
                items = list_folders(dest_parents_id[-1], drive)
                if dest in [item["title"] for item in items]:
                    new_folder_id = [item["id"] for item in items if item["title"] == dest][0]

                else:
                    new_folder_id = create_empty_folder(dest, dest_parents_id[-1], drive)

            dest_parents_id.append(new_folder_id)
        dest_dir_id = dest_parents_id[-1]

    return dest_dir_id


def check_upload(src_full_path: str, dest_dir_id: str, drive: GoogleDrive) -> str:
    """
    Checks if a folder is already uploaded to Google Drive and uploads it if not.

    Args:
        src_full_path (str): The path of the source folder on the local system.
        dest_dir_id (str): The ID of the destination directory on Google Drive.
        drive (GoogleDrive): An instance of the GoogleDrive class.

    Returns:
        str: The ID of the uploaded folder.
    """
    folder_name = src_full_path.split(os.path.sep)[-1]
    items = list_folders(dest_dir_id, drive)
    if folder_name in [item["title"] for item in items]:
        folder_id = [item["id"] for item in items if item["title"] == folder_name][0]
        return folder_id
    return None


def file_upload(args: Tuple[Dict, str, GoogleDrive]) -> None:
    """
    Uploads a file to Google Drive.

    Args:
        args (tuple): Contains file metadata, the path of the file to upload, and the Google Drive instance.
    """
    file_metadata, file_path, drive = args
    file = drive.CreateFile(file_metadata)
    file.SetContentFile(file_path)
    file.Upload()
    return file_path


def file_trash(args: Tuple[str, GoogleDrive]) -> None:
    """
    Moves a file to the trash in Google Drive.

    Args:
        args (tuple): Contains the ID of the file to trash and the Google Drive instance.
    """
    file_id, drive = args
    file = drive.CreateFile({"id": file_id})
    file.Trash()


def progress_bar_with_threading_executor(fn: Callable, iterable: Tuple, desc: str, num_of_uploader: int) -> None:
    """
    Executes a function over an iterable with a progress bar, using multiple threads.

    Args:
        fn (function): The function to apply to each item in the iterable.
        iterable (iterable): An iterable where each item will be processed by the function.
        desc (str): Description text for the progress bar.
    """
    disable_pbar = len(iterable) == 0

    with tqdm.tqdm(total=len(iterable), desc=desc, disable=disable_pbar) as progress:
        with ThreadPoolExecutor(max_workers=num_of_uploader) as executor:
            for _ in executor.map(fn, iterable):
                progress.update()


def get_tree(folder_name: str, tree_list: List[str], root: str, parents_id: Dict, drive: GoogleDrive) -> None:
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


def push(src_full_path: str, dest_dir: str, ignore_dirs: Tuple[str], num_of_uploader: int) -> None:
    """
    Pushes local files to Google Drive, creating folders and uploading files as necessary.

    Args:
        src_full_path (str): The local path to push from.
        dest_dir (str): The destination directory path on Google Drive.
        ignore_dirs (list): A list of directories to ignore during the push.
        num_of_uploader(int): Number of workers in threading executor.

    Returns:
        None
    """
    drive = load_authorized_gdrive()
    dest_dir = dest_dir.rstrip("/")

    print("Push started.")
    if ignore_dirs:
        print(f"Ignoring dirs: {' '.join(ignore_dirs)}")
    print(f"Number of uploaders: {num_of_uploader}")
    # Get id of Google Drive folder and it's path (from other script)
    # folder_id, full_path = initial_upload.check_upload(service)
    folder_name = src_full_path.split(os.path.sep)[-1]
    dest_dir_id = get_dest_dir_id(dest_dir, drive)
    folder_id = check_upload(src_full_path, dest_dir_id, drive)

    if folder_id is None:
        print(f"{os.path.join(dest_dir, folder_name)} does not exist. Uploading folder to gdrive...")
        new_folder_upload(src_full_path, dest_dir_id, drive, ignore_dirs, num_of_uploader)
        print("Push completed.")
        return

    tree_list = []
    root = ""
    parents_id = {}

    print("Comparing local stroage to gdrive...")
    parents_id[folder_name] = folder_id
    get_tree(folder_name, tree_list, root, parents_id, drive)
    local_tree_list = []
    root_len = len(src_full_path.split(os.path.sep)[0:-2])

    # Get list of folders three paths on computer
    for root, dirs, files in os.walk(src_full_path, topdown=True):

        for dir in ignore_dirs:
            dirs[:] = [d for d in dirs if dir not in d.split(os.path.sep)]

        for name in dirs:
            var_path = (os.path.sep).join(root.split(os.path.sep)[root_len + 1 :])
            local_tree_list.append(os.path.join(var_path, name))

    # new folders on drive, which you dont have(i suppose hehe)
    upload_folders = list(set(local_tree_list).difference(set(tree_list)))
    # foldes that match
    exact_folders = list(set(local_tree_list).intersection(set(tree_list)))
    # old folders on drive
    remove_folders = list(set(tree_list).difference(set(local_tree_list)))

    # Add starting directory
    exact_folders.append(folder_name)
    # Sort uploadable folders
    # so now in can be upload from top to down of tree
    upload_folders = sorted(upload_folders, key=by_lines)

    parent_folder = pathlib.Path(src_full_path).parent.resolve()

    # Here we upload new (absent on Drive) folders
    for folder_dir in upload_folders:
        folder = os.path.join(parent_folder, folder_dir)
        last_dir = pathlib.Path(folder_dir)
        pre_last_dir = pathlib.Path(folder_dir).parent

        folder_id = create_empty_folder(last_dir.name, parents_id[str(pre_last_dir)], drive)
        print(f"Created new folder for {folder}")
        parents_id[str(last_dir)] = folder_id

        upload_tasks = []
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        for local_file in files:
            local_file_mimetype = (
                mimetypes.MimeTypes().guess_type(os.path.join(folder, local_file))[0] or "application/octet-stream"
            )
            file_metadata = {
                "title": local_file,
                "parents": [{"id": folder_id}],
                "mimeType": local_file_mimetype,
            }
            upload_tasks.append((file_metadata, os.path.join(folder, local_file), drive))
        progress_bar_with_threading_executor(
            file_upload, upload_tasks, f"Uploading files from {folder}", num_of_uploader
        )

    # Check files in existed folders and replace them
    # with newer versions if needed
    for folder_dir in exact_folders:

        folder = os.path.join(parent_folder, folder_dir)
        last_dir = pathlib.Path(folder_dir)
        local_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        items = list_files(parents_id[str(last_dir)], drive)

        upload_files = [f for f in local_files if f not in [i["title"] for i in items]]
        update_files = [f for f in items if f["title"] in local_files]
        remove_files = [f for f in items if f["title"] not in local_files]

        upload_tasks = []
        for local_file in upload_files:
            local_file_mimetype = (
                mimetypes.MimeTypes().guess_type(os.path.join(folder, local_file))[0] or "application/octet-stream"
            )
            file_metadata = {
                "title": local_file,
                "parents": [{"id": folder_id}],
                "mimeType": local_file_mimetype,
            }
            upload_tasks.append((file_metadata, os.path.join(folder, local_file), drive))
        progress_bar_with_threading_executor(
            file_upload, upload_tasks, f"Uploading files from {folder}", num_of_uploader
        )

        update_tasks = []
        for drive_file in update_files:

            file_dir = os.path.join(folder, drive_file["title"])

            drive_md5 = drive_file["md5Checksum"]
            local_file_md5 = hashlib.md5(open(file_dir, "rb").read()).hexdigest()

            if drive_md5 != local_file_md5:
                file_id = [f["id"] for f in items if f["title"] == drive_file["title"]][0]
                file_mime = [f["mimeType"] for f in items if f["title"] == drive_file["title"]][0]

                file_metadata = {
                    "id": file_id,
                    "title": drive_file["title"],
                    "parents": [{"id": parents_id[str(last_dir)]}],
                    "mimeType": file_mime,
                }
                update_tasks.append((file_metadata, file_dir, drive))
        progress_bar_with_threading_executor(
            file_upload, update_tasks, f"Updating files from {folder}", num_of_uploader
        )

        removal_tasks = []
        for drive_file in remove_files:
            file_id = [f["id"] for f in items if f["title"] == drive_file["title"]][0]
            removal_tasks.append((file_id, drive))
        progress_bar_with_threading_executor(
            file_trash, removal_tasks, f"Removing files that were in {folder}", num_of_uploader
        )

    remove_folders = sorted(remove_folders, key=by_lines, reverse=True)

    # Delete old folders from Drive
    removal_tasks = []
    for folder_dir in remove_folders:
        folder = parent_folder + folder_dir
        last_dir = pathlib.Path(folder_dir)
        folder_id = parents_id[str(last_dir)]
        removal_tasks.append((folder_id, drive))
    progress_bar_with_threading_executor(file_trash, removal_tasks, "Deleting unwanted folders", num_of_uploader)
    print("Push completed.")
