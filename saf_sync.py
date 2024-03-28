#!/data/data/com.termux/files/usr/bin/python

from enum import Enum
from collections.abc import Iterator
from typing import Optional, Tuple
import subprocess
import json
import argparse


class SAFType(Enum):
    FILE = 'FILE'
    DIR = 'DIR'


class SAFEntry:
    name: str
    uri: str
    file_type: SAFType
    parent: Optional["SAFEntry"]
    length: Optional[int]
    modified: Optional[int]

    def __init__(self, uri: str, name: str, file_type: SAFType, parent: Optional["SAFEntry"] = None,
                 length: Optional[int] = None, modified: Optional[int] = None) -> None:
        self.name = name
        self.uri = uri
        self.file_type = file_type
        self.parent = parent
        self.length = length
        self.modified = modified

    def __repr__(self) -> str:
        return f'SAF({self.file_type} {self.name} at {self.uri})'


class SAFStat:
    file_type: SAFType
    length: int
    modified: Optional[int]

    def __init__(self, file_type: SAFType, length: int, modified: Optional[int]):
        self.file_type = file_type
        self.length = length
        self.modified = modified


def debug(s: str) -> None:
    print(s)


def map_mime_to_saf_type(mime: str) -> SAFType:
    return SAFType.DIR if mime == 'vnd.android.document/directory' else SAFType.FILE


def ls(entry: SAFEntry) -> Iterator[SAFEntry]:
    listing_str = subprocess.check_output(['termux-saf-ls', entry.uri])
    listing_result = json.loads(listing_str)
    for listed_entry in listing_result:
        entry_type = map_mime_to_saf_type(listed_entry['type'])
        yield SAFEntry(
            uri=listed_entry['uri'],
            name=listed_entry['name'],
            file_type=entry_type,
            parent=entry,
            length=listed_entry.get("length"),
            modified=listed_entry.get("last_modified")
        )


def ls_map(entry: SAFEntry) -> dict[str, SAFEntry]:
    ret: dict[str, SAFEntry] = {}
    for listed_entry in ls(entry):
        ret[listed_entry.name] = listed_entry
    return ret


def mkdir(parent: SAFEntry, name: str) -> SAFEntry:
    debug(f"Making directory {name} in {parent.name}")
    if parent.file_type != SAFType.DIR:
        raise ValueError("Trying to create a directory inside a non-directory")
    uri = subprocess.check_output(['termux-saf-mkdir', parent.uri, name], text=True).strip()
    return SAFEntry(uri, name, SAFType.DIR, parent)


def saf_write(entry: SAFEntry, content: bytes) -> None:
    debug(f"Writing content for {entry.name}")
    if entry.file_type != SAFType.FILE:
        raise ValueError("Trying to write to a non-file")
    subprocess.run(['termux-saf-write', entry.uri], input=content, check=True)


def saf_read(entry: SAFEntry) -> bytes:
    if entry.file_type != SAFType.FILE:
        raise ValueError("Trying to read a non-file")
    return subprocess.check_output(['termux-saf-read', entry.uri])


def mkfile(parent: SAFEntry, name: str, content: Optional[bytes] = None) -> SAFEntry:
    debug(f"Making file {name} in {parent.name}")
    if parent.file_type != SAFType.DIR:
        raise ValueError("Trying to create a file inside a non-directory")
    uri = subprocess.check_output(['termux-saf-create', parent.uri, name], text=True).strip()
    ret = SAFEntry(uri, name, SAFType.FILE, parent)
    if content is not None:
        saf_write(ret, content)
    return ret


def stat(entry: SAFEntry) -> SAFStat:
    if entry.file_type != SAFType.FILE:
        raise ValueError("Stat is intended for files, not directories here")
    stat_str = subprocess.check_output(['termux-saf-stat', entry.uri])
    stat_result = json.loads(stat_str)

    result_type = map_mime_to_saf_type(stat_result['type'])
    return SAFStat(result_type, stat_result['length'], stat_result.get('last_modified'))


def rm(entry: SAFEntry) -> None:
    debug(f"Removing {entry.name}")
    subprocess.check_call(['termux-saf-rm', entry.uri])


def create_dest_to_match(source: SAFEntry, dest_parent: SAFEntry) -> Optional[Tuple[SAFEntry, SAFEntry]]:
    debug(f"Creating {source.name} in {dest_parent.name} to match")
    if source.file_type == SAFType.DIR:
        new_dir = mkdir(dest_parent, source.name)
        return source, new_dir

    source_contents = saf_read(source)
    mkfile(dest_parent, source.name, source_contents)
    return None


def sync(root_source: SAFEntry, root_dest: SAFEntry) -> None:
    process_stack: list[Tuple[SAFEntry, SAFEntry]] = [(root_source, root_dest)]
    while len(process_stack) > 0:
        source, dest = process_stack.pop()
        debug(f"Syncing {source} -> {dest}")
        if source.file_type == SAFType.DIR:
            if dest.file_type != SAFType.DIR:
                debug(f"Source {source.name} is dir but dest {dest.name} is not; removing and recreating")
                rm(dest)
                dest = mkdir(dest.parent, dest.name)
            source_entries = ls_map(source)
            dest_entries = ls_map(dest)
            for entry_name in source_entries:
                entry = source_entries[entry_name]
                if entry_name not in dest_entries:
                    new_sync = create_dest_to_match(entry, dest)
                    if new_sync is not None:
                        process_stack.append(new_sync)
                else:
                    dest_entry = dest_entries[entry_name]
                    source_type = entry.file_type
                    dest_type = dest_entry.file_type
                    if source_type != dest_type:
                        rm(dest_entry)
                        new_sync = create_dest_to_match(entry, dest)
                        if new_sync is not None:
                            process_stack.append(new_sync)
                    elif source_type == SAFType.DIR:
                        process_stack.append((entry, dest_entry))
                    else:
                        if entry.modified is not None and entry.length == dest_entry.length and entry.modified > dest_entry.modified:
                            debug(f"Skipping transfer of {entry.name} because dest file is same size and at least as new")
                        else:
                            contents = saf_read(entry)
                            saf_write(dest_entry, contents)
            for entry_name in dest_entries:
                if entry_name in source_entries:
                    continue
                debug(f"{entry_name} does not exist in source; deleting")
                rm(dest_entries[entry_name])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='saf_sync', description='Make one directory on Android match the contents of another, using the Storage Access Framework')

    parser.add_argument('source_uri', help='Storage Access Framework URI of source')
    parser.add_argument('dest_uri', help='Storage Access Framework URI of destination')

    args = parser.parse_args()

    source_saf = SAFEntry(args.source_uri, '<source_root>', SAFType.DIR)
    dest_saf = SAFEntry(args.dest_uri, '<dest_root>', SAFType.DIR)

    sync(source_saf, dest_saf)
