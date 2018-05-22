import io
import json
import zipfile
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from django_bulk_update.helper import bulk_update

from koe.model_utils import assert_permission, \
    get_or_error, assert_values, get_user_databases
from koe.models import Segment, HistoryEntry, Database, DatabasePermission, AudioFile, Segmentation
from root.exceptions import CustomAssertionError
from root.models import ExtraAttrValue, ExtraAttr
from root.utils import history_path, ensure_parent_folder_exists

__all__ = ['save_history', 'import_history', 'delete_history']


def save_label_history(database, user, zip_file, segments_ids=None, song_ids=None):
    if segments_ids is None:
        segments_ids = frozenset(Segment.objects
                                 .filter(segmentation__audio_file__database=database, segmentation__source='user')
                                 .values_list('id', flat=True))
    if song_ids is None:
        song_ids = frozenset(AudioFile.objects.filter(database=database).values_list('id', flat=True))

    seg_extra_attr_values = list(ExtraAttrValue.objects
                                 .filter(user=user, owner_id__in=segments_ids, attr__klass=Segment.__name__)
                                 .values_list('owner_id', 'attr__id', 'value'))

    song_extra_attr_values = list(ExtraAttrValue.objects
                                  .filter(user=user, owner_id__in=song_ids, attr__klass=AudioFile.__name__)
                                  .values_list('owner_id', 'attr__id', 'value'))

    extra_attrs = list(ExtraAttr.objects.values_list('id', 'klass', 'type', 'name'))
    zip_file.writestr('extraattr.json', json.dumps(extra_attrs, indent=4))
    zip_file.writestr('segment.extraattrvalue.json', json.dumps(seg_extra_attr_values, indent=4))
    zip_file.writestr('audiofile.extraattrvalue.json', json.dumps(song_extra_attr_values, indent=4))


def save_segmentation_history(database, user, zip_file):
    """
    Save segmentation scheme of all songs in this database. Songs are referenced BY NAME
    :param database:
    :param user:
    :param zip_file:
    :return:
    """
    segment_values = Segment.objects.filter(segmentation__audio_file__database=database, segmentation__source='user') \
        .values_list('id', 'segmentation__audio_file__name', 'segmentation__audio_file', 'start_time_ms', 'end_time_ms',
                     'mean_ff', 'min_ff', 'max_ff')

    seg_ids = []
    song_ids = []
    song_info = {}
    for seg_id, song_name, song_id, start, end, mean_ff, min_ff, max_ff in segment_values:
        seg_ids.append(seg_id)
        if song_name not in song_info:
            song_ids.append(song_id)
            song_info[song_name] = (song_id, [])

        song_info[song_name][1].append((seg_id, start, end, mean_ff, min_ff, max_ff))

    zip_file.writestr('songinfo.json', json.dumps(song_info, indent=4))
    save_label_history(database, user, zip_file, seg_ids, song_ids)


def save_history(request):
    """
    Save a copy of all ExtraAttrValue (labels, notes, ...) in a HistoryEntry
    :param request: must specify a comment to store with this copy
    :return: name of the zip file created
    :version: 2.0.0
    """
    version = 4
    user = request.user

    comment = get_or_error(request.POST, 'comment')
    database_id = get_or_error(request.POST, 'database')
    backup_type = get_or_error(request.POST, 'type')

    database = get_or_error(Database, dict(id=database_id))
    assert_permission(user, database, DatabasePermission.VIEW)
    assert_values(backup_type, ['labels', 'segmentation'])

    meta = dict(database=database_id, user=user.id, time=timezone.now(), version=version, note=comment,
                type=backup_type)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_BZIP2, False) as zip_file:
        zip_file.writestr('meta.json', json.dumps(meta))
        zip_file.writestr('root.extraattrvalue.json', 'here for checking purpose')

        if backup_type == 'labels':
            save_label_history(database, user, zip_file)
        else:
            save_segmentation_history(database, user, zip_file)

    binary_content = zip_buffer.getvalue()

    he = HistoryEntry.objects.create(user=user, time=timezone.now(), database=database, version=version, note=comment,
                                     type=backup_type)
    filename = he.filename
    filepath = history_path(filename)
    ensure_parent_folder_exists(filepath)

    with open(filepath, 'wb') as f:
        f.write(binary_content)

    return filename


def delete_history(request):
    """
    Delete a HistoryEntry given its id
    :param request: must specify version-id
    :return:
    """
    version_id = get_or_error(request.POST, 'version-id')
    he = HistoryEntry.objects.get(id=version_id)
    creator = he.user
    if creator != request.user:
        raise CustomAssertionError('Only {} can delete this version'.format(creator.username))

    he.delete()
    return True


def change_owner_and_attr_ids(entries, _extra_attrs, owner_old_to_new_id=None):
    # Match saved extra attr IDs with their current IDs
    extra_attrs = ExtraAttr.objects.values_list('id', 'klass', 'type', 'name')
    if _extra_attrs is None:
        _extra_attrs = extra_attrs
    extra_attr_old_id_to_key = {x[0]: (x[1], x[2], x[3]) for x in _extra_attrs}
    extra_attr_key_to_new_id = {(x[1], x[2], x[3]): x[0] for x in extra_attrs}
    extra_attr_old_to_new_id = {}
    for old_id, key in extra_attr_old_id_to_key.items():
        if key in extra_attr_key_to_new_id:
            extra_attr_old_to_new_id[old_id] = extra_attr_key_to_new_id[key]
        else:
            extra_attr = ExtraAttr.objects.create(klass=key[0], type=key[1], name=key[2])
            extra_attr_old_to_new_id[old_id] = extra_attr.id

    _entries = []

    for owner_id, _attr_id, value in entries:
        attr_id = extra_attr_old_to_new_id[_attr_id]
        _entries.append((owner_id, attr_id, value))

    if owner_old_to_new_id:
        __entries = []
        for _owner_id, attr_id, value in _entries:
            if _owner_id not in owner_old_to_new_id:
                continue
            owner_id = owner_old_to_new_id[_owner_id]
            __entries.append((owner_id, attr_id, value))
        return __entries
    return _entries


def import_history_version_4(database, user, filelist):
    """
    For version 4 - the segment endpoints are also stored, so object IDs don't matter.
    - Recreate segmentation for files that haven't got segmentation, or theirs are different
    - Populate labels using file names and segment endpoints
    :param database:
    :param user:
    :param filelist:
    :return:
    """
    try:
        _extra_attrs = json.loads(filelist['extraattr.json'])
        segment_attr_values = json.loads(filelist['segment.extraattrvalue.json'])
        song_attr_values = json.loads(filelist['audiofile.extraattrvalue.json'])
        _song_info = json.loads(filelist['songinfo.json'])
    except Exception:
        raise CustomAssertionError('The history content is malformed and cannot be parsed.')

    # Match saved song IDs to their actual IDs on the datbase (if exists)
    # Songs that don't exist in the database are ignore
    song_names = frozenset(list(_song_info.keys()))

    existing_songs_no_segmentation = AudioFile.objects \
        .filter(name__in=song_names, segmentation=None, database=database) \
        .values_list('id', flat=True)

    with transaction.atomic():
        for song_id in existing_songs_no_segmentation:
            Segmentation.objects.create(audio_file_id=song_id, source='user')

    song_name_to_segmentation_id = {
        x[0]: x[1] for x in Segmentation.objects
        .filter(source='user', audio_file__database=database, audio_file__name__in=song_names)
        .values_list('audio_file__name', 'id')
    }

    segmentation_ids = frozenset(list(song_name_to_segmentation_id.values()))
    song_names = frozenset(list(song_name_to_segmentation_id.keys()))

    existing_segments = Segment.objects \
        .filter(segmentation__audio_file__name__in=song_names, segmentation__audio_file__database=database) \
        .values_list('id', 'segmentation__audio_file__name', 'segmentation__audio_file', 'start_time_ms', 'end_time_ms')

    song_name_to_new_id = {
        x[0]: x[1] for x in AudioFile.objects.filter(name__in=song_names, database=database).values_list('name', 'id')}

    seg_old_to_new_id = {}
    song_info = {}
    new_segments = []
    song_old_to_new_id = {}

    for seg_id, song_name, song_id, start, end in existing_segments:
        if song_name not in song_info:
            song_info[song_name] = (song_id, [])
        song_info[song_name][1].append((seg_id, start, end))

    seg_key_to_new_id = {}
    seg_key_to_old_id = {}
    seg_key_to_extras = {}
    for song_name, (_song_id, _info) in _song_info.items():

        # Ignore songs that exist in the saved but not in this database
        if song_name not in song_name_to_new_id:
            continue

        for _seg_id, start, end, mean_ff, min_ff, max_ff in _info:
            seg_key = (start, end, song_name)
            seg_key_to_old_id[seg_key] = _seg_id
            seg_key_to_extras[seg_key] = (mean_ff, min_ff, max_ff)

        if song_name in song_info:
            song_id, info = song_info[song_name]
            song_old_to_new_id[_song_id] = song_id

            for seg_id, start, end in info:
                seg_key_to_new_id[(start, end, song_name)] = seg_id
        else:
            song_old_to_new_id[_song_id] = song_name_to_new_id[song_name]

    for seg_key, _seg_id in seg_key_to_old_id.items():
        if seg_key in seg_key_to_new_id:
            seg_id = seg_key_to_new_id[seg_key]
            seg_old_to_new_id[_seg_id] = seg_id
        else:
            start, end, song_name = seg_key
            mean_ff, min_ff, max_ff = seg_key_to_extras[seg_key]
            segmentation_id = song_name_to_segmentation_id[song_name]
            new_segments.append(Segment(start_time_ms=start, end_time_ms=end, segmentation_id=segmentation_id,
                                        mean_ff=mean_ff, min_ff=min_ff, max_ff=max_ff))

    Segment.objects.bulk_create(new_segments)
    seg_key_to_new_id = {
        (x[0], x[1], x[2]): x[3] for x in Segment.objects.filter(segmentation__in=segmentation_ids)
        .values_list('start_time_ms', 'end_time_ms', 'segmentation__audio_file__name', 'id')
    }

    for seg_key, _seg_id in seg_key_to_old_id.items():
        if seg_key in seg_key_to_new_id:
            seg_old_to_new_id[_seg_id] = seg_key_to_new_id[seg_key]

    seg_old_to_new_id = {str(k): str(v) for k, v in seg_old_to_new_id.items()}

    segment_attr_values = change_owner_and_attr_ids(segment_attr_values, _extra_attrs, seg_old_to_new_id)
    song_attr_values = change_owner_and_attr_ids(song_attr_values, _extra_attrs, song_old_to_new_id)

    update_extra_attr_values(user, segment_attr_values)
    update_extra_attr_values(user, song_attr_values)

    return True


def update_extra_attr_values(user, new_entries):
    """
    Update the ExtraAttr ids in case they are different from the saved
    :param user:
    :param new_entries:
    :return:
    """
    extra_attr_key_to_value = {
        (x[0], x[1]): (x[2], x[3]) for x in
        ExtraAttrValue.objects.filter(user=user).values_list('owner_id', 'attr', 'value', 'id')
    }

    extra_attr_values_to_update = {}
    extra_attr_values_to_create = []

    for owner_id, attr_id, _value in new_entries:
        key = (owner_id, attr_id)

        if key in extra_attr_key_to_value:
            value, extra_attr_value_id = extra_attr_key_to_value[key]
            if value != _value:
                extra_attr_values_to_update[extra_attr_value_id] = _value
        else:
            extra_attr_values_to_create.append(
                ExtraAttrValue(owner_id=owner_id, value=_value, user=user, attr_id=attr_id)
            )

    extra_attr_values_object_to_update = ExtraAttrValue.objects \
        .filter(id__in=extra_attr_values_to_update.keys()) \
        .only('value', 'id')

    for extra_attr_value in extra_attr_values_object_to_update:
        new_value = extra_attr_values_to_update[extra_attr_value.id]
        extra_attr_value.value = new_value

    bulk_update(extra_attr_values_object_to_update, update_fields=['value'])

    ExtraAttrValue.objects.bulk_create(extra_attr_values_to_create)

    return True


def import_history(request):
    """
    Import a HistoryEntry from any user to this user.
    If this operation fails, the database is intact.
    :param request: must specify either : version-id, which is the id of the HistoryEntry object to be imported to
                                          or FILES['zipfile'] which should be created somewhere by Koe for someone
    :return: True if everything goes well.
    """
    version_id = request.POST.get('version-id', None)
    zip_file = request.FILES.get('zipfile', None)
    user = request.user

    _, current_database = get_user_databases(user)
    if current_database is None:
        raise CustomAssertionError('You don\'t have a current working database')

    assert_permission(user, current_database, DatabasePermission.ANNOTATE)

    if not (version_id or zip_file):
        raise CustomAssertionError('No ID or file provided. Abort.')

    if version_id:
        he = HistoryEntry.objects.get(id=version_id)
        file = open(history_path(he.filename), 'rb')
    else:
        file = File(file=zip_file)

    filelist = {}
    with zipfile.ZipFile(file, "r") as zip_file:
        namelist = zip_file.namelist()
        for name in namelist:
            filelist[name] = zip_file.read(name)

    version = 1
    backup_type = 'labels'
    extra_attrs = None

    if 'meta.json' in filelist:
        meta = json.loads(filelist['meta.json'])
        version = meta['version']
        backup_type = meta.get('type', backup_type)

    try:
        content = filelist['root.extraattrvalue.json']
    except KeyError:
        raise CustomAssertionError('This is not a Koe history file')

    if version == 4:
        if backup_type == 'segmentation':
            return import_history_version_4(current_database, user, filelist)
        else:
            contents = [
                filelist['segment.extraattrvalue.json'],
                filelist['audiofile.extraattrvalue.json']
            ]
            extra_attrs = json.loads(filelist['extraattr.json'])
    else:
        contents = [content]

    try:
        new_entries = []
        for content in contents:
            loaded = json.loads(content)
            new_entries += loaded
    except Exception:
        raise CustomAssertionError('The history content is malformed and cannot be parsed.')

    if version == 1:
        new_entries = [
            (x['fields']['owner_id'], x['fields']['attr'], x['fields']['value']) for x in new_entries
        ]

    new_entries = change_owner_and_attr_ids(new_entries, extra_attrs)

    return update_extra_attr_values(user, new_entries)
