import datetime
import hashlib
import mimetypes
import os
import time

from pydrive2.drive import GoogleDrive

from gdrive import load_authorized_gdrive


def folder_upload(src_full_path, drive: GoogleDrive):
    """Uploads folder and all it's content (if it doesnt exists)
    in root folder.

    Args:
        items: List of folders in root path on Google Drive.
        service: Google Drive service instance.

    Returns:
        Dictionary, where keys are folder's names
        and values are id's of these folders.
    """

    parents_id = {}

    for root, _, files in os.walk(src_full_path, topdown=True):
        last_dir = root.split("/")[-1]
        pre_last_dir = root.split("/")[-2]
        if pre_last_dir not in parents_id.keys():
            pre_last_dir = "root"
        else:
            pre_last_dir = parents_id[pre_last_dir]

        folder_metadata = {
            "title": last_dir,
            "parents": [{"id": pre_last_dir}],
            "mimeType": "application/vnd.google-apps.folder",
        }
        new_folder = drive.CreateFile(folder_metadata)
        new_folder.Upload()
        folder_id = new_folder["id"]

        for name in files:
            file_metadata = {
                "title": name,
                "parents": [{"id": folder_id}],
                "mimeType": mimetypes.MimeTypes().guess_type(name)[0],
            }
            file = drive.CreateFile(file_metadata)
            file.SetContentFile(os.path.join(root, name))
            file.Upload()

        parents_id[last_dir] = folder_id

    return parents_id


def check_upload(src_full_path: str, drive: GoogleDrive) -> str:
    """Checks if folder is already uploaded,
    and if it's not, uploads it.

    Args:
        service: Google Drive service instance.

    Returns:
        ID of uploaded folder, full path to this folder on computer.

    """
    folder_name = src_full_path.split(os.path.sep)[-1]
    items = drive.ListFile(
        {"q": "'root' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"}
    ).GetList()
    if folder_name in [item["title"] for item in items]:
        folder_id = [item["id"] for item in items if item["title"] == folder_name][0]
    else:
        parents_id = folder_upload(src_full_path, drive)
        folder_id = parents_id[folder_name]

    return folder_id


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


def by_lines(input_str):
    """Helps Sort items by the number of slashes in it.

    Returns:
        Number of slashes in string.
    """
    return input_str.count(os.path.sep)


def push(src_full_path):
    """Syncronizes computer folder with Google Drive folder.

    Checks files if they exist, uploads new files and subfolders,
    deletes old files from Google Drive and refreshes existing stuff.
    """
    drive = load_authorized_gdrive()

    # Get id of Google Drive folder and it's path (from other script)
    # folder_id, full_path = initial_upload.check_upload(service)
    folder_id = check_upload(src_full_path, drive)
    folder_name = src_full_path.split(os.path.sep)[-1]
    tree_list = []
    root = ""
    parents_id = {}

    parents_id[folder_name] = folder_id
    get_tree(folder_name, tree_list, root, parents_id, drive)
    os_tree_list = []
    root_len = len(src_full_path.split(os.path.sep)[0:-2])

    # Get list of folders three paths on computer
    for root, dirs, files in os.walk(src_full_path, topdown=True):
        for name in dirs:
            var_path = (os.path.sep).join(root.split(os.path.sep)[root_len + 1 :])
            os_tree_list.append(os.path.join(var_path, name))

    # old folders on drive
    remove_folders = list(set(tree_list).difference(set(os_tree_list)))
    # new folders on drive, which you dont have(i suppose hehe)
    upload_folders = list(set(os_tree_list).difference(set(tree_list)))
    # foldes that match
    exact_folders = list(set(os_tree_list).intersection(set(tree_list)))

    # Add starting directory
    exact_folders.append(folder_name)
    # Sort uploadable folders
    # so now in can be upload from top to down of tree
    upload_folders = sorted(upload_folders, key=by_lines)

    # Here we upload new (absent on Drive) folders
    for folder_dir in upload_folders:
        var = os.path.sep + os.path.join(*src_full_path.split(os.path.sep)[0:-1])
        variable = os.path.join(var, folder_dir)
        last_dir = folder_dir.split(os.path.sep)[-1]
        pre_last_dir = folder_dir.split(os.path.sep)[-2]

        files = [f for f in os.listdir(variable) if os.path.isfile(os.path.join(variable, f))]

        folder_metadata = {
            "title": last_dir,
            "parents": [{"id": parents_id[pre_last_dir]}],
            "mimeType": "application/vnd.google-apps.folder",
        }
        new_folder = drive.CreateFile(folder_metadata)
        new_folder.Upload()
        folder_id = new_folder["id"]

        parents_id[last_dir] = folder_id

        for os_file in files:
            os_file_mimetype = mimetypes.MimeTypes().guess_type(os.path.join(variable, os_file))[0]
            file_metadata = {
                "name": os_file,
                "parents": [{"id": folder_id}],
                "mimeType": os_file_mimetype,
            }

            file_upload = drive.CreateFile(file_metadata)
            file_upload.SetContentFile(os.path.join(variable, os_file))
            file_upload.Upload()

    # Check files in existed folders and replace them
    # with newer versions if needed
    for folder_dir in exact_folders:

        var = os.path.sep + (os.path.sep).join(src_full_path.split(os.path.sep)[0:-1])
        variable = os.path.join(var, folder_dir)
        last_dir = folder_dir.split(os.path.sep)[-1]
        os_files = [f for f in os.listdir(variable) if os.path.isfile(os.path.join(variable, f))]
        items = drive.ListFile(
            {
                "q": f"'{parents_id[last_dir]}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
            }
        ).GetList()

        refresh_files = [f for f in items if f["title"] in os_files]
        remove_files = [f for f in items if f["title"] not in os_files]
        upload_files = [f for f in os_files if f not in [j["title"] for j in items]]

        # Check files that exist both on Drive and on PC
        for drive_file in refresh_files:
            file_dir = os.path.join(variable, drive_file["title"])
            file_time = os.path.getmtime(file_dir)
            mtime = [f["modifiedDate"] for f in items if f["title"] == drive_file["title"]][0]
            mtime = datetime.datetime.strptime(mtime[:-2], "%Y-%m-%dT%H:%M:%S.%f")
            drive_time = time.mktime(mtime.timetuple())

            os_file_md5 = hashlib.md5(open(file_dir, "rb").read()).hexdigest()
            if "md5Checksum" in drive_file.keys():
                drive_md5 = drive_file["md5Checksum"]
            else:
                drive_md5 = None

            if (file_time > drive_time) or (drive_md5 != os_file_md5):
                file_id = [f["id"] for f in items if f["title"] == drive_file["title"]][0]
                file_mime = [f["mimeType"] for f in items if f["title"] == drive_file["title"]][0]

                file_metadata = {
                    "title": drive_file["title"],
                    "parents": [{"id": parents_id[last_dir]}],
                    "mimeType": file_mime,
                }
                file_update = drive.CreateFile(file_metadata)
                file_update.SetContentFile(file_dir)
                file_update.Upload()

        # Remove old files from Drive
        for drive_file in remove_files:

            file_id = [f["id"] for f in items if f["title"] == drive_file["title"]][0]
            file_trash = drive.CreateFile({"id": file_id})
            file_trash.Trash()

        # Upload new files on Drive
        for os_file in upload_files:

            file_dir = os.path.join(variable, os_file)

            # File's new content.
            filemime = mimetypes.MimeTypes().guess_type(file_dir)[0]
            file_metadata = {
                "title": os_file,
                "parents": [{"id": parents_id[last_dir]}],
                "mimeType": filemime,
            }

            new_upload = drive.CreateFile(file_metadata)
            new_upload.SetContentFile(file_dir)
            new_upload.Upload()

    remove_folders = sorted(remove_folders, key=by_lines, reverse=True)

    # Delete old folders from Drive
    for folder_dir in remove_folders:
        var = (os.path.sep).join(src_full_path.split(os.path.sep)[0:-1]) + os.path.sep
        variable = var + folder_dir
        last_dir = folder_dir.split("/")[-1]
        folder_id = parents_id[last_dir]
        file_trash = drive.CreateFile({"id": folder_id})
        file_trash.Trash()
