r"""
Train a LSTM on audio segments.
"""
from collections import Counter

import numpy as np
from django.core.management.base import BaseCommand
from pymlfunc import tictoc

from koe import binstorage
from koe.management.commands.extract_data_for_tensorboard import get_sids_tids, get_binstorage_locations
from koe.model_utils import get_or_error
from koe.models import Database, Feature
from koe.rnn_models import DataProvider
from koe.rnn_train import train
from root.models import ExtraAttrValue, User


def extract_rawdata(f2bs, ids, features):
    # ids = np.array([19078])
    data_by_id = {id: [] for id in ids}

    for feature in features:
        index_filename, value_filename = f2bs[feature]
        with tictoc('{}'.format(feature.name)):
            feature_values = binstorage.retrieve(ids, index_filename, value_filename)
            for id, feature_value in zip(ids, feature_values):
                data_by_id[id].append(feature_value)

    data = []
    for id in ids:
        feature_values = data_by_id[id]
        try:
            feature_values = np.vstack(feature_values).T
        except ValueError:
            print('Encounter error at id={}'.format(id))
            for idx, feature in enumerate(features):
                print('{} - {}'.format(feature.name, feature_values[idx].shape))
        data.append(feature_values)

    return data


def get_labels_by_sids(sids, label_level, annotator, min_occur):
    sid2lbl = {
        x: y.lower() for x, y in ExtraAttrValue.objects
        .filter(attr__name=label_level, owner_id__in=sids, user=annotator)
        .values_list('owner_id', 'value')
    }

    occurs = Counter(sid2lbl.values())

    segment_to_labels = {}
    for segid, label in sid2lbl.items():
        if occurs[label] >= min_occur:
            segment_to_labels[segid] = label

    labels = []
    no_label_ids = []
    for id in sids:
        label = segment_to_labels.get(id, None)
        if label is None:
            no_label_ids.append(id)
        labels.append(label)

    return np.array(labels), np.array(no_label_ids, dtype=np.int32)


def exclude_no_labels(sids, tids, labels, no_label_ids):
    no_label_inds = np.searchsorted(sids, no_label_ids)

    sids_mask = np.full((len(sids),), True, dtype=np.bool)
    sids_mask[no_label_inds] = False

    return sids[sids_mask], tids[sids_mask], labels[sids_mask]


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--database-name', action='store', dest='database_name', required=True, type=str,
                            help='E.g Bellbird, Whale, ..., case insensitive', )

        parser.add_argument('--annotator-name', action='store', dest='annotator_name', default='superuser', type=str,
                            help='Name of the person who owns this database, case insensitive', )

        parser.add_argument('--population', action='store', dest='population_name', required=True, type=str,
                            help='Prefix of song name to identify population - e.g LBI, PKI', )

        parser.add_argument('--label-level', action='store', dest='label_level', default='label', type=str,
                            help='Level of labelling to use', )

        parser.add_argument('--min-occur', action='store', dest='min_occur', default=2, type=int,
                            help='Ignore syllable classes that have less than this number of instances', )

        parser.add_argument('--feature-names', action='store', dest='feature_names', default=None, type=str,
                            help='Comma-separated feature IDs', )

    def handle(self, *args, **options):
        database_name = options['database_name']
        annotator_name = options['annotator_name']
        population_name = options['population_name']
        label_level = options['label_level']
        min_occur = options['min_occur']
        feature_names = options['feature_names']

        if feature_names:
            feature_names = feature_names.split(',')
            features = Feature.objects.filter(name__in=feature_names).order_by('id')
        else:
            features = Feature.objects.all().order_by('id')

        features = features.exclude(is_fixed_length=True)

        database = get_or_error(Database, dict(name__iexact=database_name))
        annotator = get_or_error(User, dict(username__iexact=annotator_name))

        sids, tids = get_sids_tids(database, population_name)
        labels, no_label_ids = get_labels_by_sids(sids, label_level, annotator, min_occur)

        if len(no_label_ids) > 0:
            sids, tids, labels = exclude_no_labels(sids, tids, labels, no_label_ids)

        # features = Feature.objects.filter(name__in=['mfcc', 'zero_crossing_rate']).order_by('id')

        f2bs, fa2bs = get_binstorage_locations(features, [])
        data = extract_rawdata(f2bs, tids, features)

        data_provider = DataProvider(data, labels)
        model_name = '{}_{}_{}_{}_{}-min'.format(database_name, annotator_name, population_name, label_level, min_occur)
        train(data_provider, name=model_name)
