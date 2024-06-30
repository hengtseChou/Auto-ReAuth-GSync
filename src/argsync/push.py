import hashlib
import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor

import tqdm
from pydrive2.drive import GoogleDrive

from argsync.gdrive import load_authorized_gdrive


def list_folders(parents_id, drive: GoogleDrive):

    return drive.ListFile(
        {"q": f"'{parents_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"}
    ).GetList()


def list_files(parents_id, drive: GoogleDrive):

    return drive.ListFile(
        {"q": f"'{parents_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"}
    ).GetList()


def create_empty_folder(folder_name, parents_id, drive: GoogleDrive):

    folder_metadata = {
        "title": folder_name,
        "parents": [{"id": parents_id}],
        "mimeType": "application/vnd.google-apps.folder",
    }

    new_folder = drive.CreateFile(folder_metadata)
    new_folder.Upload()
    folder_id = new_folder["id"]

    return folder_id


def new_folder_upload(src_full_path, target_parents_id, drive: GoogleDrive, ignore_dirs):
    """Uploads folder and all it's content (if it doesnt exists)

    Args:
        items: List of folders in root path on Google Drive.
        service: Google Drive service instance.

    Returns:
        Dictionary, where keys are folder's names
        and values are id's of these folders.
    """

    parents_id = {}

    for root, dirs, files in os.walk(src_full_path, topdown=True):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        last_dir = os.path.basename(root)
        pre_last_dir = os.path.basename(os.path.dirname(root))
        if pre_last_dir not in parents_id:
            pre_last_dir = target_parents_id
        else:
            pre_last_dir = parents_id[pre_last_dir]

        folder_id = create_empty_folder(last_dir, pre_last_dir, drive)

        with ThreadPoolExecutor(max_workers=5) as executor:

            for name in files:
                file_metadata = {
                    "title": name,
                    "parents": [{"id": folder_id}],
                    "mimeType": mimetypes.MimeTypes().guess_type(name)[0] or "application/octet-stream",
                }
                executor.submit(file_upload, file_metadata, os.path.join(root, name), drive)

        parents_id[last_dir] = folder_id

    return parents_id


def get_dest_dir_id(dest_dir, drive: GoogleDrive) -> str:

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
    """Checks if folder is already uploaded,
    and if it's not, uploads it.

    Args:
        service: Google Drive service instance.

    Returns:
        ID of uploaded folder, full path to this folder on computer.

    """
    folder_name = src_full_path.split(os.path.sep)[-1]
    items = list_folders(dest_dir_id, drive)
    if folder_name in [item["title"] for item in items]:
        folder_id = [item["id"] for item in items if item["title"] == folder_name][0]
        return folder_id
    return None


def file_upload(args):
    """Upload a file to Google Drive using provided arguments packed as a tuple.

    Args:
        args (tuple): A tuple containing file_metadata, file_path, and drive object.
    """
    file_metadata, file_path, drive = args
    file = drive.CreateFile(file_metadata)
    file.SetContentFile(file_path)
    file.Upload()
    return file_path


def file_trash(args):
    """Trashing a file from Google Drive using provided arguments packed as a tuple.

    Args:
        args (tuple): A tuple containing file_id, and drive object.
    """
    file_id, drive = args
    file = drive.CreateFile({"id": file_id})
    file.Trash()


def progress_bar_with_threading_executor(fn, iterable, desc):

    disable_pbar = len(iterable) == 0

    with tqdm.tqdm(total=len(iterable), desc=desc, disable=disable_pbar) as progress:
        with ThreadPoolExecutor(max_workers=5) as executor:
            for _ in executor.map(fn, iterable):
                progress.update()


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
    items = list_folders(folder_id, drive)
    root += folder_name + os.path.sep

    for item in items:
        parents_id[item["title"]] = item["id"]
        tree_list.append(root + item["title"])
        folder_id = [i["id"] for i in items if i["title"] == item["title"]][0]
        folder_name = item["title"]
        get_tree(folder_name, tree_list, root, parents_id, drive)


def by_lines(input_str):
    """Helps Sort items by the number of slashes in it.

    Returns:
        Number of slashes in string.
    """
    return input_str.count(os.path.sep)


def push(src_full_path, dest_dir, ignore_dirs):
    """Push files to google drive"""
    drive = load_authorized_gdrive()
    dest_dir = dest_dir.rstrip("/")

    print("Push started.")
    if ignore_dirs:
        print(f"Ignoring dirs: {','.join(ignore_dirs)}")
    # Get id of Google Drive folder and it's path (from other script)
    # folder_id, full_path = initial_upload.check_upload(service)
    folder_name = src_full_path.split(os.path.sep)[-1]
    dest_dir_id = get_dest_dir_id(dest_dir, drive)
    folder_id = check_upload(src_full_path, dest_dir_id, drive)

    if folder_id is None:
        print(f"{dest_dir}{folder_name} does not exist. Uploading folder to gdrive...")
        parents_id = new_folder_upload(src_full_path, dest_dir_id, drive, ignore_dirs)
        folder_id = parents_id[folder_name]
        print("Upload completed.")

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

    # Here we upload new (absent on Drive) folders
    for folder_dir in upload_folders:
        parent_folder = os.path.sep + os.path.join(*src_full_path.split(os.path.sep)[0:-1])
        folder = os.path.join(parent_folder, folder_dir)
        last_dir = folder_dir.split(os.path.sep)[-1]
        pre_last_dir = folder_dir.split(os.path.sep)[-2]

        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        folder_id = create_empty_folder(last_dir, parents_id[pre_last_dir], drive)
        print(f"Create new folder for {folder}")
        parents_id[last_dir] = folder_id

        upload_tasks = []
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
        progress_bar_with_threading_executor(file_upload, upload_tasks, f"Uploading files in {folder}")

    # Check files in existed folders and replace them
    # with newer versions if needed
    for folder_dir in exact_folders:

        parent_folder = (os.path.sep).join(src_full_path.split(os.path.sep)[0:-1])
        folder = os.path.join(parent_folder, folder_dir)
        last_dir = folder_dir.split(os.path.sep)[-1]
        local_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        items = list_files(parents_id[last_dir], drive)

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
        progress_bar_with_threading_executor(file_upload, upload_tasks, f"Uploading files in {folder}")

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
                    "parents": [{"id": parents_id[last_dir]}],
                    "mimeType": file_mime,
                }
                update_tasks.append((file_metadata, file_dir, drive))
        progress_bar_with_threading_executor(file_upload, update_tasks, f"Updating files in {folder}")

        removal_tasks = []
        for drive_file in remove_files:
            file_id = [f["id"] for f in items if f["title"] == drive_file["title"]][0]
            removal_tasks.append((file_id, drive))
        progress_bar_with_threading_executor(file_trash, removal_tasks, f"Removing files in {folder}")

    remove_folders = sorted(remove_folders, key=by_lines, reverse=True)

    # Delete old folders from Drive
    removal_tasks = []
    for folder_dir in remove_folders:
        parent_folder = (os.path.sep).join(src_full_path.split(os.path.sep)[0:-1]) + os.path.sep
        folder = parent_folder + folder_dir
        last_dir = folder_dir.split("/")[-1]
        folder_id = parents_id[last_dir]
        removal_tasks.append((file_id, drive))
    progress_bar_with_threading_executor(file_trash, removal_tasks, "Deleting unwanted folders")
    print("Push completed.")
