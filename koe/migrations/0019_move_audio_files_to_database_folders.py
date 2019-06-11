# Generated by Django 2.0.4 on 2019-03-26 02:19
import os

import errno
from logging import warning

from bulk_update.helper import bulk_update
from django.conf import settings
from django.db import migrations, models
from django.db import transaction
from django.db.models import F


def create_database_folders_for_audio_files(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    model = apps.get_model('koe', 'Database')
    media_dir = settings.MEDIA_URL[1:]
    compressed_format = settings.AUDIO_COMPRESSED_FORMAT

    new_wav_dir = os.path.join(settings.BASE_DIR, media_dir, 'audio', 'wav')
    new_compressed_dir = os.path.join(settings.BASE_DIR, media_dir, 'audio', compressed_format)

    for database_id in model.objects.using(db_alias).values_list('id', flat=True):
        database_id = str(database_id)
        this_new_wav_dir = os.path.join(new_wav_dir, database_id)
        this_new_compressed_dir = os.path.join(new_compressed_dir, database_id)

        try:
            os.mkdir(this_new_wav_dir)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(this_new_wav_dir):
                pass
            else:
                raise

        try:
            os.mkdir(this_new_compressed_dir)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(this_new_compressed_dir):
                pass
            else:
                raise


def move_audio_files_to_respective_folders(apps, schema_editor):
    """

    """
    db_alias = schema_editor.connection.alias
    model = apps.get_model('koe', 'AudioFile')

    media_dir = settings.MEDIA_URL[1:]
    compressed_format = settings.AUDIO_COMPRESSED_FORMAT

    old_wav_dir = os.path.join(settings.BASE_DIR, media_dir, 'audio', 'wav')
    old_compressed_dir = os.path.join(settings.BASE_DIR, media_dir, 'audio', compressed_format)

    values = model.objects.using(db_alias).filter(original=None).values_list('name', 'database__id')

    for filename, database__id in values:
        database_id = str(database__id)
        old_wav_filepath = os.path.join(old_wav_dir, '{}.wav'.format(filename))
        old_compressed_filepath = os.path.join(old_compressed_dir, '{}.{}'.format(filename, compressed_format))

        new_wav_filepath = os.path.join(settings.BASE_DIR, media_dir, 'audio', 'wav', database_id,
                                        '{}.wav'.format(filename))
        new_compressed_filepath = os.path.join(settings.BASE_DIR, media_dir, 'audio', compressed_format, database_id,
                                               '{}.{}'.format(filename, compressed_format))

        if not os.path.isfile(old_wav_filepath):
            if not os.path.isfile(new_wav_filepath):
                warning('File {} (from database {}) doesn\'t exist.'.format(old_wav_filepath, database_id))
        else:
            os.rename(old_wav_filepath, new_wav_filepath)

        if not os.path.isfile(old_compressed_filepath):
            if not os.path.isfile(new_compressed_filepath):
                warning('File {} (from database {}) doesn\'t exist.'.format(old_compressed_filepath, database_id))
        else:
            os.rename(old_compressed_filepath, new_compressed_filepath)


def remove_extension(apps, schema_editor):
    """
    Add filename (path to real file) to AudioFile model.
    AudioFile objects that are original will have this field changed to '{database_id}/{name}'
    AudioFile objects that are not original will have this field changed to '{original_database_id}/{name}'
    """
    db_alias = schema_editor.connection.alias
    audio_file_model = apps.get_model('koe', 'AudioFile')

    audio_files = audio_file_model.objects.using(db_alias).all()
    updated = []

    for af in audio_files:
        name = af.name
        if name.lower().endswith('.wav'):
            name = name[:-4]
            af.name = name
            updated.append(af)

    if len(updated) > 0:
        bulk_update(updated, update_fields=['name'], batch_size=10000)


# def add_field_filename(apps, schema_editor):
#     """
#     Add filename (path to real file) to AudioFile model.
#     AudioFile objects that are original will have this field changed to '{database_id}/{name}'
#     AudioFile objects that are not original will have this field changed to '{original_database_id}/{name}'
#     """
#     db_alias = schema_editor.connection.alias
#     audio_file_model = apps.get_model('koe', 'AudioFile')
#     audio_file_model.objects.using(db_alias).all().update(file_name=F('name'))
#
#     original_files = audio_file_model.objects.using(db_alias).filter(original=None)
#     copied_files = audio_file_model.objects.using(db_alias).exclude(original=None)
#
#     for af in original_files:
#         name = af.name
#         if name.lower().endswith('.wav'):
#             name = name[:-4]
#         af.name = name
#         af.file_name = os.path.join(str(af.database.id), name)
#
#     for af in copied_files:
#         name, ext = os.path.splitext(af.name)
#         af.name = name
#         af.file_name = os.path.join(str(af.original.database.id), name)
#
#     bulk_update(original_files, update_fields=['name', 'file_name'], batch_size=10000)
#     bulk_update(copied_files, update_fields=['name', 'file_name'], batch_size=10000)


class Migration(migrations.Migration):

    dependencies = [
        ('koe', '0018_ordination_params'),
    ]

    operations = [
        # migrations.AddField(
        #     model_name='audiofile',
        #     name='file_name',
        #     field=models.CharField(max_length=255, null=True),
        # ),
        # migrations.RunPython(add_field_filename, reverse_code=migrations.RunPython.noop),
        # migrations.AlterField(
        #     model_name='audiofile',
        #     name='file_name',
        #     field=models.CharField(max_length=255, null=False),
        # ),
        migrations.RunPython(remove_extension, reverse_code=migrations.RunPython.noop),
        migrations.RunPython(create_database_folders_for_audio_files, reverse_code=migrations.RunPython.noop),
        migrations.RunPython(move_audio_files_to_respective_folders, reverse_code=migrations.RunPython.noop),
    ]