import json
import os

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.generic import TemplateView, FormView

from koe.forms import SongPartitionForm
from koe.model_utils import get_user_databases, get_current_similarity, assert_permission, get_or_error
from koe.models import AudioFile, Database, DatabaseAssignment, DatabasePermission, AccessRequest, AudioTrack
from root.models import User, ExtraAttrValue


def populate_context(obj, context, kwargs, with_similarity=False):
    page_name = obj.__class__.page_name
    user = obj.request.user
    databases, current_database = get_user_databases(user)
    db_assignment = assert_permission(user, current_database, DatabasePermission.VIEW)

    inaccessible_databases = Database.objects.exclude(id__in=databases)

    databases_own = DatabaseAssignment.objects \
        .filter(user=user, permission__gte=DatabasePermission.ASSIGN_USER).values_list('database', flat=True)

    pending_requests = AccessRequest.objects.filter(database__in=databases_own, resolved=False)

    context['databases'] = databases
    context['current_database'] = current_database
    context['current_database_owner_class'] = User.__name__
    context['current_database_owner_id'] = user.id
    context['inaccessible_databases'] = inaccessible_databases
    context['db_assignment'] = db_assignment
    context['pending_requests'] = pending_requests

    from_user = kwargs.get('from_user', user.username)
    from_user = get_or_error(User, dict(username=from_user))

    cls = kwargs.get('class', 'label')
    context['from_user'] = from_user

    context['cls'] = cls
    context['page'] = '/{}/'.format(page_name)
    context['subpage'] = '/{}/{}/'.format(page_name, cls)

    if with_similarity:
        similarities, current_similarity = get_current_similarity(user, current_database)
        context['similarities'] = similarities

        if current_similarity:
            context['current_similarity_owner_class'] = User.__name__
            context['current_similarity'] = current_similarity


class SyllablesView(TemplateView):
    """
    The view to index page
    """

    page_name = 'syllables'
    template_name = 'syllables.html'

    def get_context_data(self, **kwargs):
        context = super(SyllablesView, self).get_context_data(**kwargs)

        populate_context(self, context, kwargs, True)

        return context


class ExemplarsView(TemplateView):
    page_name = 'exemplars'
    template_name = "exemplars.html"

    def get_context_data(self, **kwargs):
        context = super(ExemplarsView, self).get_context_data(**kwargs)

        populate_context(self, context, kwargs)

        return context


class SongsView(TemplateView):
    """
    The view to index page
    """

    page_name = 'songs'
    template_name = 'songs.html'

    def get_context_data(self, **kwargs):
        context = super(SongsView, self).get_context_data(**kwargs)

        populate_context(self, context, kwargs)

        return context


class SequenceMiningView(TemplateView):
    """
    The view to index page
    """

    page_name = 'sequence-mining'
    template_name = 'sequence-mining.html'

    def get_context_data(self, **kwargs):
        context = super(SequenceMiningView, self).get_context_data(**kwargs)

        populate_context(self, context, kwargs)

        return context


class SegmentationView(TemplateView):
    """
    The view of song segmentation page
    """

    template_name = "segmentation.html"

    def get_context_data(self, **kwargs):
        context = super(SegmentationView, self).get_context_data(**kwargs)
        user = self.request.user

        file_id = get_or_error(kwargs, 'file_id')
        audio_file = get_or_error(AudioFile, dict(id=file_id))
        db_assignment = assert_permission(user, audio_file.database, DatabasePermission.VIEW)
        track = audio_file.track
        individual = audio_file.individual
        quality = audio_file.quality
        date = track.date if track else None
        species = individual.species if individual else None

        context['page'] = 'segmentation'
        context['file_id'] = file_id
        context['db_assignment'] = db_assignment
        context['length'] = audio_file.length
        context['fs'] = audio_file.fs

        context['song_info'] = {
            'Length': '{:5.2f} secs'.format(audio_file.length / audio_file.fs),
            'Name': audio_file.name,
            'Species': str(species) if species else 'Unknown',
            'Date': date.strftime(settings.DATE_INPUT_FORMAT) if date else 'Unknown',
            'Quality': quality if quality else 'Unknown',
            'Track': track.name if track else 'Unknown',
            'Individual': individual.name if individual else 'Unknown',
            'Gender': individual.gender if individual else 'Unknown'
        }

        song_extra_attr_values_list = ExtraAttrValue.objects \
            .filter(user=user, attr__klass=AudioFile.__name__, owner_id=audio_file.id) \
            .values_list('attr__name', 'value')

        for attr, value in song_extra_attr_values_list:
            context['song_info']['Song\'s {}'.format(attr)] = value

        return context


class SongPartitionView(FormView):
    """
    The view of song segmentation page
    """

    template_name = "song-partition.html"
    form_class = SongPartitionForm
    page_name = 'song-partition'

    def get_initial(self):
        track_id = self.kwargs.get('track_id', None)
        return dict(track_id=track_id)

    def get_context_data(self, **kwargs):
        context = super(SongPartitionView, self).get_context_data(**kwargs)

        # Note: in FormView, url params exist in self.kwargs, not **kwargs.
        track_id = self.kwargs.get('track_id', None)
        if AudioTrack.objects.filter(id=track_id).exists():
            context['valid'] = True
        context['track_id'] = track_id
        populate_context(self, context, kwargs)

        return context

    def form_invalid(self, form):
        context = self.get_context_data()
        context['form'] = form
        context['valid'] = False
        return render(self.request, 'partials/track-info-form.html', context=context)

    def form_valid(self, form):
        context = self.get_context_data()
        form_data = form.cleaned_data
        track_name = form_data['name']
        track_id = form_data['track_id']
        date = form_data['date']

        has_error = False
        track = None

        if track_id:
            track = AudioTrack.objects.filter(id=track_id).first()
        if track is None:
            track = AudioTrack.objects.filter(name=track_name).first()
            should_not_have_duplicate = True
        else:
            should_not_have_duplicate = False

        if track and should_not_have_duplicate:
            track_is_non_empty = AudioFile.objects.filter(track=track).exists()
            if track_is_non_empty:
                form.add_error('name', 'Track already exists and is not empty')
                has_error = True

        if not has_error:
            if track is None:
                track = AudioTrack(name=track_name)
            else:
                track.name = track_name

            if date:
                track.date = date

            track.save()
            context['track_id'] = track.id
            context['valid'] = True

        context['form'] = form

        rendered = render(self.request, 'partials/track-info-form.html', context=context)
        return HttpResponse(json.dumps(dict(message=rendered.content.decode('utf-8'))))


class TensorvizView(TemplateView):
    template_name = "tensorviz.html"

    def get_context_data(self, **kwargs):
        context = super(TensorvizView, self).get_context_data(**kwargs)
        config = get_or_error(self.request.GET, 'cfg')

        context['config_file'] = os.path.join(settings.MEDIA_URL, 'oss_data', '{}.json'.format(config))
        return context
