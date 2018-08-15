import django.db.models.options as options
import hashlib
import numpy as np
import os
import pickle
from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from logging import warning

from koe.utils import base64_to_array, array_to_base64
from root.exceptions import CustomAssertionError
from root.models import SimpleModel, User, MagicChoices
from root.utils import history_path, ensure_parent_folder_exists, pickle_path, wav_path, audio_path

__all__ = ['NumpyArrayField', 'AudioTrack', 'Species', 'Individual', 'Database', 'DatabasePermission', 'AccessRequest',
           'DatabaseAssignment', 'AudioFile', 'Segment', 'DistanceMatrix', 'Coordinate', 'HistoryEntry']


class NumpyArrayField(models.TextField):
    """
    A class that faciliates storing and retrieving numpy array in database.
    The undelying value in database is a base64 string
    """

    def __init__(self, *args, **kwargs):
        super(NumpyArrayField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        if isinstance(value, NumpyArrayField):
            return value

        if value is None:
            return value

        return base64_to_array(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return base64_to_array(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        if not isinstance(value, np.ndarray):
            raise TypeError('value must be a numpy array')
        return array_to_base64(value)


class AudioTrack(SimpleModel):
    """
    A track is a whole raw audio recording containing many songs.
    """

    name = models.CharField(max_length=255, unique=True)
    date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.name


class Species(SimpleModel):
    genus = models.CharField(max_length=32)
    species = models.CharField(max_length=32)

    class Meta:
        unique_together = ['species', 'genus']

    def __str__(self):
        return '{} {}'.format(self.genus, self.species)


class Individual(SimpleModel):
    """
    Represents a bird.
    """

    name = models.CharField(max_length=255)
    gender = models.CharField(max_length=16, null=True, blank=True)
    species = models.ForeignKey(Species, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ['name', 'species']


class Database(SimpleModel):
    """
    This works as a separator between different sets of audio files that are not related.
    E.g. a database of bellbirds and a database of dolphin sounds...
    """

    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class DatabasePermission(MagicChoices):
    VIEW = 100
    ANNOTATE = 200
    IMPORT_DATA = 300
    COPY_FILES = 400
    ADD_FILES = 500
    MODIFY_SEGMENTS = 600
    DELETE_FILES = 700
    ASSIGN_USER = 800


class DatabaseAssignment(SimpleModel):
    """
    Grant user access to database with this
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    permission = models.IntegerField(choices=DatabasePermission.as_choices())

    def __str__(self):
        return 'Database {} assigned to user {} with {} permission'.format(
            self.database.name, self.user.username, self.get_permission_display()
        )

    class Meta:
        unique_together = ('user', 'database', 'permission')
        ordering = ('user', 'database', 'permission')

    def can_view(self):
        return self.user.is_superuser or self.permission >= DatabasePermission.VIEW

    def can_annotate(self):
        return self.user.is_superuser or self.permission >= DatabasePermission.ANNOTATE

    def can_copy_files(self):
        return self.user.is_superuser or self.permission >= DatabasePermission.COPY_FILES

    def can_add_files(self):
        return self.user.is_superuser or self.permission >= DatabasePermission.ADD_FILES

    def can_modify_segments(self):
        return self.user.is_superuser or self.permission >= DatabasePermission.MODIFY_SEGMENTS

    def can_delete_files(self):
        return self.user.is_superuser or self.permission >= DatabasePermission.DELETE_FILES

    def can_assign_user(self):
        return self.user.is_superuser or self.permission >= DatabasePermission.ASSIGN_USER


class AudioFile(SimpleModel):
    """
    Represent a song
    """

    fs = models.IntegerField()
    length = models.IntegerField()
    name = models.CharField(max_length=255)
    track = models.ForeignKey(AudioTrack, null=True, blank=True, on_delete=models.SET_NULL)
    individual = models.ForeignKey(Individual, null=True, blank=True, on_delete=models.SET_NULL)
    quality = models.CharField(max_length=255, null=True, blank=True)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    start = models.IntegerField(null=True, blank=True)
    end = models.IntegerField(null=True, blank=True)

    # To facilitate copying database - when an AudioFile object is copied, another object is created
    # with the same name but different database, and reference this object as its original
    original = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ['name', 'database']

    def __str__(self):
        return self.name

    def is_original(self):
        """
        An AudioFile object is original if it doesn't reference any one
        :return: True if it is original
        """
        return self.original is None

    @classmethod
    def set_individual(cls, objs, name, extras={}):
        individual, _ = Individual.objects.get_or_create(name=name)
        AudioFile.objects.filter(id__in=objs).update(individual=individual)

    @classmethod
    def set_name(cls, objs, name, extras={}):
        if len(objs) != 1:
            raise CustomAssertionError('Can\'t set the same name to more than 1 song.')
        obj = objs[0]

        unique_name = name
        is_unique = not AudioFile.objects.filter(name=unique_name).exists()
        postfix = 0
        while not is_unique:
            postfix += 1
            unique_name = '{}({}).wav'.format(name, postfix)
            is_unique = not AudioFile.objects.filter(name=unique_name).exists()

        new_name_wav = wav_path(unique_name)
        new_name_compressed = audio_path(unique_name, settings.AUDIO_COMPRESSED_FORMAT)

        old_name_wav = wav_path(obj.name)
        old_name_compressed = audio_path(obj.name, settings.AUDIO_COMPRESSED_FORMAT)

        os.rename(old_name_wav, new_name_wav)
        os.rename(old_name_compressed, new_name_compressed)

        obj.name = name
        obj.save()


class Segment(SimpleModel):
    """
    A segment of a song
    """

    # Time ID - unique for each combination of (song name, start and end). Recalculate if end/begin changes
    tid = models.IntegerField()

    start_time_ms = models.IntegerField()
    end_time_ms = models.IntegerField()

    audio_file = models.ForeignKey(AudioFile, on_delete=models.CASCADE)

    # Some measurements
    mean_ff = models.FloatField(null=True)
    min_ff = models.FloatField(null=True)
    max_ff = models.FloatField(null=True)

    def __str__(self):
        return '{} - {}:{}'.format(self.audio_file.name, self.start_time_ms, self.end_time_ms)

    class Meta:
        ordering = ('audio_file', 'start_time_ms')


options.DEFAULT_NAMES += 'attrs',


class PicklePersistedModel(SimpleModel):
    """
    Abstract base for models that need to persist its attributes not in the database but in a pickle file
    Any attributes can be added to the model by declaring `attrs = ('attribute1', 'attribute2',...) in class Meta
    """

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(PicklePersistedModel, self).__init__(*args, **kwargs)

        # Load the persisted data on to the model from its pickle file
        self.load()

    def save(self, *args, **kwargs):
        """
        Save the object and then use its ID to store a pickle file contaning all the attrs as declared
        Pickle file will be stored in user_data/pickle/<class name>/
        :param args:
        :param kwargs:
        :return: None
        """
        super(PicklePersistedModel, self).save(*args, **kwargs)

        fpath = pickle_path(self.id, self.__class__.__name__)
        ensure_parent_folder_exists(fpath)

        mdict = {}
        for attr in self._meta.attrs:
            mdict[attr] = getattr(self, attr)

        with open(fpath, 'wb') as f:
            pickle.dump(mdict, f, pickle.HIGHEST_PROTOCOL)

    def load(self):
        """
        Load the persisted data on to the model from its pickle file
        Not to be called when the model is being constructed
        :return: None
        """
        if self.id:
            fpath = pickle_path(self.id, self.__class__.__name__)
            if os.path.isfile(fpath):
                with open(fpath, 'rb') as f:
                    mdict = pickle.load(f)
                for attr in self._meta.attrs:
                    # _attr = '_{}'.format(attr)
                    setattr(self, attr, mdict[attr])
                self._loaded = True
            else:
                warning('Can\'t restore data for {} #{}. File {} not found'
                        .format(self.__class__.__name__, self.id, fpath))

    def __str__(self):
        retval = ['{} #{}: '.format(self.__class__.__name__, self.id)]
        for attr in self._meta.attrs:
            retval.append('{}: {}'.format(attr, getattr(self, attr, None)))

        return ', '.join(retval)


class AlgorithmicModelMixin(models.Model):
    """
    This is an abstract for models that can be distinguished by the attribute algorithm
    """

    algorithm = models.CharField(max_length=255)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def __str__(self):
        standard_str = super(AlgorithmicModelMixin, self).__str__()
        extras = 'Database: {} algorithm: {}'.format(self.database.name, self.algorithm)
        return '{}, {}'.format(standard_str, extras)


class IdOrderedModel(PicklePersistedModel):
    """
    This is an abstract for models that have a unique list of IDs as its attribute.
      To facilitate querying, we store a checksum of the concatenated list as a unique field in the database
      The checksum is calculated automatically upon saving
    """

    chksum = models.CharField(max_length=24)

    class Meta:
        abstract = True

    @classmethod
    def calc_chksum(cls, ids):
        ids_str = ''.join(map(str, ids))
        return hashlib.md5(ids_str.encode('ascii')).hexdigest()[:24]

    def save(self, *args, **kwargs):
        self.chksum = IdOrderedModel.calc_chksum(self.ids)
        super(IdOrderedModel, self).save(*args, **kwargs)


class DistanceMatrix(AlgorithmicModelMixin, IdOrderedModel):
    """
    To store the upper triangle (triu) of a distance matrix
    """

    class Meta:
        unique_together = ('chksum', 'algorithm', 'database')
        attrs = ('ids', 'triu')


class Coordinate(AlgorithmicModelMixin, IdOrderedModel):
    """
    To store a list of coordinates together with the clustered tree and the sorted natural order of the elements
    """

    class Meta:
        unique_together = ('chksum', 'algorithm', 'database')
        attrs = ('ids', 'coordinates', 'tree', 'order')


class HistoryEntry(SimpleModel):
    """
    Represent a snapshot of the current user's workspace.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    version = models.IntegerField(default=1)
    note = models.TextField(null=True, blank=True)
    time = models.DateTimeField()
    filename = models.CharField(max_length=255)
    database = models.ForeignKey(Database, on_delete=models.SET_NULL, null=True, blank=False)
    type = models.CharField(max_length=32, default='labels')

    class Meta:
        ordering = ['-time', 'user', 'database']

    def save(self, *args, **kwargs):
        """
        Deduce the filename from username and timestamp - so this field always have a uniform format
        :param args:
        :param kwargs:
        :return:
        """
        if not self.filename:
            self.filename = '{}-{}.zip'.format(self.user.username, self.time.strftime('%Y-%m-%d_%H-%M-%S_%Z'))
        super(HistoryEntry, self).save(*args, **kwargs)


class AccessRequest(SimpleModel):
    """
    Record a database access request from user so that a database admin can response
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    permission = models.IntegerField(choices=DatabasePermission.as_choices(), default=DatabasePermission.VIEW)
    resolved = models.BooleanField(default=False)

    class Meta:
        unique_together = ['user', 'database']

    def __str__(self):
        resolved_or_not = '[RESOLVED] ' if self.resolved else ''
        return '{}{} requested {} permission on {}'.format(
            resolved_or_not, self.user.username, self.get_permission_display(), self.database.name
        )


class Feature(SimpleModel):
    name = models.CharField(max_length=255, unique=True)
    is_fixed_length = models.BooleanField()
    is_one_dimensional = models.BooleanField()


class SegmentFeature(SimpleModel):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('segment', 'feature')


@receiver(post_delete, sender=HistoryEntry)
def _history_delete(sender, instance, **kwargs):
    """
    When a HistoryEntry is deleted, also delete its ZIP file
    :param sender:
    :param instance:
    :param kwargs:
    :return:
    """
    filepath = history_path(instance.filename)
    print('Delete {}'.format(filepath))
    if os.path.isfile(filepath):
        os.remove(filepath)
    else:
        warning('File {} doesnot exist.'.format(filepath))


@receiver(post_delete)
def _mymodel_delete(sender, instance, **kwargs):
    """
    When a PicklePersistedModel is deleted, also delete its pickle file
    :param sender:
    :param instance:
    :param kwargs:
    :return:
    """
    if isinstance(instance, PicklePersistedModel):
        filepath = pickle_path(instance.id, instance.__class__.__name__)
        print('Delete {}'.format(filepath))
        if os.path.isfile(filepath):
            os.remove(filepath)
        else:
            warning('File {} doesnot exist.'.format(filepath))
